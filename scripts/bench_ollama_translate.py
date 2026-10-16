"""Benchmark de traduccion en->es con el backend Ollama (LLM local).

Traduce por orden N capitulos de ``output/<slug>/raw/`` sin tocar la cache real
``translated/`` y guarda las traducciones + estadisticas (tiempos, GPU,
reintentos) en ``output/scripts/<slug>_<timestamp>/``.

Uso:
    uv run python scripts/bench_ollama_translate.py \
        --novel divine-emperor-of-death --start 1 --count 5 --source en --target es

No es un test unitario: requiere ``ollama serve`` con el modelo descargado y,
opcionalmente, ``nvidia-smi`` para las metricas de GPU.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from novel_cli.core import config
from novel_cli.core.scraper.fetcher import Pacer
from novel_cli.core.services.download import format_chapter, load_chapter
from novel_cli.core.services.translate import OllamaTranslator, translate_chapter

TRANSLATE_LOGGER = "novel_cli.core.services.translate"


class WarningCounter(logging.Handler):
    """Cuenta los WARNING del logger de traduccion (reintentos/fallback)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1
        self.messages.append(record.getMessage())


def gpu_snapshot() -> dict[str, float] | None:
    """Una muestra de GPU via nvidia-smi; None si no esta disponible."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    first = result.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 4:
        return None

    def _num(value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
            return None

    return {
        "temp_c": _num(parts[0]),
        "util_pct": _num(parts[1]),
        "vram_mb": _num(parts[2]),
        "power_w": _num(parts[3]),
    }


class GpuSampler:
    """Muestrea la GPU en un hilo hasta que se detiene."""

    def __init__(self, interval: float) -> None:
        self.interval = max(0.2, interval)
        self.samples: list[dict[str, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            snap = gpu_snapshot()
            if snap is not None:
                self.samples.append(snap)
            self._stop.wait(self.interval)


def _values(samples: list[dict[str, float]], key: str) -> list[float]:
    return [s[key] for s in samples if s.get(key) is not None]


def _gpu_summary(samples: list[dict[str, float]]) -> dict[str, object]:
    def _stat(key: str) -> dict[str, float | None]:
        vals = _values(samples, key)
        if not vals:
            return {"max": None, "avg": None}
        return {"max": max(vals), "avg": round(statistics.fmean(vals), 2)}

    return {
        "samples": len(samples),
        "temp_c": _stat("temp_c"),
        "util_pct": _stat("util_pct"),
        "vram_mb": _stat("vram_mb"),
        "power_w": _stat("power_w"),
    }


def resolve_slug(output_root: Path, novel: str | None) -> str:
    if novel:
        return novel
    for path in sorted(output_root.iterdir()):
        raw = path / "raw"
        if raw.is_dir() and any(raw.glob("*.md")):
            return path.name
    raise SystemExit(f"no se encontro ninguna novela con raw/ en {output_root}")


def select_chapters(raw_dir: Path, start: int, count: int) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in raw_dir.glob("*.md"):
        try:
            num = int(path.stem)
        except ValueError:
            continue
        if num >= start:
            found.append((num, path))
    found.sort(key=lambda item: item[0])
    selected = found[:count]
    if not selected:
        raise SystemExit(f"no hay capitulos >= {start} en {raw_dir}")
    return selected


async def run(args: argparse.Namespace) -> dict[str, object]:
    output_root = Path(args.output_root).expanduser()
    slug = resolve_slug(output_root, args.novel)
    raw_dir = output_root / slug / "raw"
    chapters = select_chapters(raw_dir, args.start, args.count)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (
        Path(args.out_dir).expanduser()
        if args.out_dir
        else output_root / "scripts" / f"{slug}_{timestamp}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    counter = WarningCounter()
    translate_logger = logging.getLogger(TRANSLATE_LOGGER)
    translate_logger.addHandler(counter)

    sampler = GpuSampler(args.gpu_interval)
    sampler.start()

    translator = OllamaTranslator(model=args.model, pacer=Pacer(0))
    records: list[dict[str, object]] = []
    previous_end: float | None = None
    started_at = datetime.now()
    wall_start = time.monotonic()

    print(f"Modelo: {args.model} | novel: {slug} | {args.source} -> {args.target}")
    print(f"Salida: {out_dir.resolve()}")
    print(f"Capitulos: {', '.join(str(num) for num, _ in chapters)}\n")

    try:
        for num, path in chapters:
            if previous_end is not None:
                gap = time.monotonic() - previous_end
            else:
                gap = None

            chapter = load_chapter(path, num, url="")
            warnings_before = counter.count
            t0 = time.monotonic()
            translated = await translate_chapter(
                chapter, translator, target=args.target, source=args.source
            )
            t1 = time.monotonic()

            content = format_chapter(translated, translated.paragraphs)
            (out_dir / f"{num:04d}.md").write_text(content, encoding="utf-8")

            words = sum(len(p.split()) for p in chapter.paragraphs)
            chars = sum(len(p) for p in chapter.paragraphs)
            seconds = t1 - t0
            aligned = len(translated.paragraphs) == len(chapter.paragraphs)
            empties = sum(1 for p in translated.paragraphs if not p.strip())
            record = {
                "num": num,
                "paragraphs": len(chapter.paragraphs),
                "words": words,
                "chars": chars,
                "seconds": round(seconds, 2),
                "words_per_sec": round(words / seconds, 1) if seconds else None,
                "gap_seconds": round(gap, 2) if gap is not None else None,
                "aligned_1to1": aligned,
                "empty_paragraphs": empties,
                "warnings": counter.count - warnings_before,
                "gpu_after": gpu_snapshot(),
            }
            records.append(record)
            previous_end = t1
            print(
                f"cap {num:04d}: {len(chapter.paragraphs)} parr | {words} pal | "
                f"{seconds:6.1f}s | {record['words_per_sec']} pal/s | "
                f"1:1 {'OK' if aligned else 'NO'} | warns {record['warnings']}"
            )
    finally:
        await translator.aclose()
        sampler.stop()
        translate_logger.removeHandler(counter)

    wall_seconds = time.monotonic() - wall_start
    translate_seconds = [r["seconds"] for r in records]
    warm = translate_seconds[1:] if len(translate_seconds) > 1 else translate_seconds
    gaps = [r["gap_seconds"] for r in records if r["gap_seconds"] is not None]
    total_words = sum(r["words"] for r in records)

    summary: dict[str, object] = {
        "model": args.model,
        "backend": "ollama",
        "novel": slug,
        "source": args.source,
        "target": args.target,
        "started_at": started_at.isoformat(timespec="seconds"),
        "timestamp": timestamp,
        "output_dir": str(out_dir),
        "chapters": records,
        "totals": {
            "count": len(records),
            "wall_seconds": round(wall_seconds, 2),
            "translate_seconds": round(sum(translate_seconds), 2),
            "avg_seconds": round(statistics.fmean(translate_seconds), 2),
            "min_seconds": round(min(translate_seconds), 2),
            "max_seconds": round(max(translate_seconds), 2),
            "first_chapter_cold_seconds": round(translate_seconds[0], 2),
            "warm_avg_seconds": round(statistics.fmean(warm), 2),
            "total_words": total_words,
            "words_per_sec": round(total_words / sum(translate_seconds), 1),
            "avg_gap_seconds": round(statistics.fmean(gaps), 2) if gaps else None,
        },
        "gpu": _gpu_summary(sampler.samples),
        "warnings_total": counter.count,
    }

    (out_dir / "stats.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "stats.md").write_text(render_markdown(summary), encoding="utf-8")
    print("\n" + render_markdown(summary))
    return summary


def render_markdown(summary: dict[str, object]) -> str:
    chapters = summary["chapters"]
    totals = summary["totals"]
    gpu = summary["gpu"]
    assert isinstance(chapters, list) and isinstance(totals, dict) and isinstance(gpu, dict)

    lines = [
        f"# Benchmark Ollama — {summary['novel']} ({summary['source']}->{summary['target']})",
        "",
        f"- Modelo: `{summary['model']}`",
        f"- Inicio: {summary['started_at']}",
        f"- Salida: `{summary['output_dir']}`",
        "",
        "## Por capitulo",
        "",
        "| Cap | Parr | Palabras | Tiempo (s) | Pal/s | Gap (s) | 1:1 | Vacios | Warns |",
        "|---:|---:|---:|---:|---:|---:|:--:|:--:|---:|",
    ]
    for r in chapters:
        lines.append(
            f"| {r['num']:04d} | {r['paragraphs']} | {r['words']} | {r['seconds']} | "
            f"{r['words_per_sec']} | {r['gap_seconds']} | "
            f"{'OK' if r['aligned_1to1'] else 'NO'} | {r['empty_paragraphs']} | {r['warnings']} |"
        )

    temp = gpu["temp_c"]
    util = gpu["util_pct"]
    vram = gpu["vram_mb"]
    power = gpu["power_w"]
    lines += [
        "",
        "## Resumen",
        "",
        f"- Capitulos: {totals['count']}",
        f"- Tiempo total (wall): {totals['wall_seconds']} s",
        f"- Tiempo traduciendo (suma): {totals['translate_seconds']} s",
        f"- Media por capitulo: {totals['avg_seconds']} s "
        f"(min {totals['min_seconds']} / max {totals['max_seconds']})",
        f"- Primer capitulo (frio): {totals['first_chapter_cold_seconds']} s",
        f"- Media en caliente: {totals['warm_avg_seconds']} s",
        f"- Palabras totales: {totals['total_words']} ({totals['words_per_sec']} pal/s)",
        f"- Gap medio entre capitulos: {totals['avg_gap_seconds']} s",
        f"- Warnings (reintentos/fallback): {summary['warnings_total']}",
        "",
        "## GPU",
        "",
        f"- Muestras: {gpu['samples']}",
        f"- Temperatura: max {temp['max']} C / media {temp['avg']} C",
        f"- Utilizacion: max {util['max']} % / media {util['avg']} %",
        f"- VRAM: max {vram['max']} MB",
        f"- Potencia: max {power['max']} W / media {power['avg']} W",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default="output")
    parser.add_argument("--novel", default=None, help="slug (default: primera con raw/)")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--source", default="en")
    parser.add_argument("--target", default="es")
    parser.add_argument("--model", default=config.OLLAMA_MODEL)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--gpu-interval", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
