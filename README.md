# novel-cli

CLI tool para descargar novelas web desde NovelFire.net y generar archivos EPUB, con traducción automática vía Ollama (LLM local).

## Stack

- **Python 3.14** — lenguaje
- **Playwright (Firefox)** — scraping headless
- **Ollama** — traducción con LLM local
- **Peewee / SQLite** — persistencia
- **Hatchling / uv** — build y dependencias

## Features

- Scraping de novelas desde NovelFire.net
- Traducción automática inglés → español vía Ollama
- Almacenamiento en SQLite con migraciones
- Medición de tiempo de ejecución

## Roadmap

- [ ] CLI con argumentos (url, idioma, formato de salida)
- [ ] Generación de EPUB
- [ ] Soporte para múltiples fuentes
- [ ] Tests automatizados
- [ ] Modo interactivo / progreso

## Quickstart

```bash
# Clonar e instalar dependencias
uv sync

# Configurar variables de entorno
cp .env.sample .env
# Editar .env con el modelo de Ollama deseado

# Ejecutar
novel_cli
```
