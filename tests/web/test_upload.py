"""Unit tests del upload de PDFs en la web (sin red, sin conversión real).

Se mocks run_pdf_pipeline/retranslate_pdf en web.jobs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from novel_cli.core.models.state import Manifest
from novel_cli.web.app import create_app


def _client(monkeypatch, tmp_path):
    async def fake(**kwargs: Any) -> Manifest:
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr("novel_cli.web.jobs.run_pdf_pipeline", fake)
    app = create_app(output_dir=tmp_path)
    return TestClient(app)


def _wait_done(client, job_id: str) -> dict[str, Any]:
    async def wait():
        for _ in range(50):
            data = client.get(f"/api/jobs/{job_id}").json()
            if data["state"] in ("done", "error"):
                return data
            await asyncio.sleep(0.01)
        return data

    return asyncio.run(wait())


def test_upload_rejects_non_pdf(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/upload",
        files={"file": ("nota.txt", b"hola", "text/plain")},
    )
    assert res.status_code == 400
    assert "pdf" in res.json()["detail"]


def test_upload_rejects_invalid_source(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/upload",
        files={"file": ("n.pdf", b"%PDF", "application/pdf")},
        data={"source_language": "xx"},
    )
    assert res.status_code == 400


def test_upload_rejects_invalid_target(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/upload",
        files={"file": ("n.pdf", b"%PDF", "application/pdf")},
        data={"source_language": "en", "translate": "true", "target_language": "xx"},
    )
    assert res.status_code == 400


def test_upload_rejects_oversize(monkeypatch, tmp_path):
    monkeypatch.setattr("novel_cli.web.routes.config.UPLOAD_MAX_MB", 0)
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/upload",
        files={"file": ("n.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert res.status_code == 400
    assert "maximo" in res.json()["detail"]


def test_upload_creates_pdf_job(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    fake_manifest = Manifest(
        slug="novela", title="Novela", source_pdf="source.pdf", language_code="en"
    )

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return fake_manifest

    monkeypatch.setattr("novel_cli.web.jobs.run_pdf_pipeline", fake)
    client = TestClient(create_app(output_dir=tmp_path))

    res = client.post(
        "/api/upload",
        files={"file": ("mi-novela.pdf", b"%PDF-fake", "application/pdf")},
        data={"source_language": "en", "volume_size": "50"},
    )
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    data = _wait_done(client, job_id)
    assert data["state"] == "done"
    assert data["slug"] == "novela"
    assert data["url"] == "mi-novela.pdf"
    assert captured["source_language"] == "en"
    assert captured["volume_size"] == 50
    assert captured["translate"] is False
    # el archivo quedó en staging y se limpia tras el job
    assert not (tmp_path / ".uploads" / job_id).exists()


def test_upload_with_translate_passes_target(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr("novel_cli.web.jobs.run_pdf_pipeline", fake)
    client = TestClient(create_app(output_dir=tmp_path))

    res = client.post(
        "/api/upload",
        files={"file": ("n.pdf", b"%PDF", "application/pdf")},
        data={
            "source_language": "en",
            "translate": "true",
            "target_language": "es",
            "volume_size": "100",
        },
    )
    assert res.status_code == 200
    assert captured["translate"] is True
    assert captured["target_language"] == "es"


def test_retranslate_pdf_uses_slug(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    Manifest(
        slug="novela",
        title="Novela",
        source_pdf="source.pdf",
        language_code="en",
        translated=True,
    ).save(slug_dir)

    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr("novel_cli.web.jobs.retranslate_pdf", fake)
    client = TestClient(create_app(output_dir=tmp_path))

    res = client.post("/api/novels/novela/retranslate")
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    data = _wait_done(client, job_id)
    assert data["state"] == "done"
    assert captured["slug_dir"].name == "novela"
    assert captured["target_language"] == "es"


def test_sync_disabled_for_pdf(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    Manifest(
        slug="novela", title="Novela", source_pdf="source.pdf"
    ).save(slug_dir)
    client = _client(monkeypatch, tmp_path)
    assert client.post("/api/novels/novela/sync").status_code == 400


def test_payload_exposes_source_pdf(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    Manifest(
        slug="novela", title="Novela", source_pdf="source.pdf"
    ).save(slug_dir)
    client = _client(monkeypatch, tmp_path)
    novels = client.get("/api/novels").json()
    assert novels[0]["source_pdf"] == "source.pdf"


def test_config_exposes_upload(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    data = client.get("/api/config").json()
    assert data["upload_enabled"] is True
    assert data["upload_max_mb"] == 100
    assert "es" in data["source_languages"]