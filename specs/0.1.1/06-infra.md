# 06 — Infra: LibreTranslate CPU (podman) y CUDA (docker)

- Estado: implementado · Versión spec: 0.1.1

## Propósito

Levantar el motor de traducción local en CPU (podman rootless) o acelerado por GPU NVIDIA (docker), sin rate-limit y con modelos persistentes.

## Contexto / Problema

- LibreTranslate limita a ~200 req/día/IP por defecto → 429 en re-traducciones largas.
- La GPU disponible (RTX 3060) no se usaba.
- En docker, el `/etc/resolv.conf` del host solo apunta al MagicDNS de Tailscale (`100.100.100.100`), inalcanzable desde el contenedor → falla la descarga de modelos (`gaierror`).

## Cambio propuesto

- `docker-compose.yaml` (CPU, podman): añade `LT_API_KEYS=local` (con key se omite el rate-limit). Se lanza con `podman compose up -d`.
- `docker-compose.cuda.yaml` (nuevo, GPU): imagen `libretranslate/libretranslate:latest-cuda`, reserva de GPU (`driver: nvidia`, `capabilities: [gpu]`), `LT_LOAD_ONLY=en,es`, `LT_API_KEYS=local`, volumen `libretranslate_cuda_models` para los modelos, y `dns: 8.8.8.8/1.1.1.1` (fix del MagicDNS). Se lanza con `sudo docker compose -f docker-compose.cuda.yaml up -d`.
- `.env`: `NOVEL_TRANSLATE_BACKEND=libre`, `NOVEL_TRANSLATE_URL=http://127.0.0.1:5000`, `NOVEL_TRANSLATE_API_KEY=local`.

## Decisión técnica

CPU y CUDA comparten el puerto 5000 → **no pueden correr a la vez** (detener uno antes del otro). Ambos usan la misma key, por lo que la app no cambia de config al alternar.

## Archivos afectados

`docker-compose.yaml`, `docker-compose.cuda.yaml`, `.env` (gitignored), `docs/uso.md`.

## Tests

`docker compose -f docker-compose.cuda.yaml config` renderiza con la reserva de GPU.

## Criterios de aceptación

- El contenedor CUDA arranca, descarga los modelos (DNS ok) y `nvidia-smi` lo ve dentro.
- Una re-traducción larga no muere por 429.