"""Unit tests de la web (FastAPI TestClient, sin red).

Se mocks run_pipeline en web.jobs para no tocar la red ni el pipeline real.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from novel_cli.core.models.state import Manifest
from novel_cli.web.app import create_app
from novel_cli.web.jobs import Job


async def _fake_pipeline(**kwargs: Any) -> Manifest:
    return Manifest(slug="novela", title="Novela")


def _client(monkeypatch, tmp_path):
    async def fake(**kwargs: Any) -> Manifest:
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr("novel_cli.web.jobs.run_pipeline", fake)
    app = create_app(output_dir=tmp_path)
    return TestClient(app)


def test_index_served(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/")
    assert res.status_code == 200
    assert "novel-cli web" in res.text


def test_static_css_served(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/static/css/app.css")
    assert res.status_code == 200
    assert "--brand" in res.text


def test_config_no_auth(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.json()["auth_required"] is False


def test_config_auth_required(monkeypatch, tmp_path):
    import os

    os.environ["NOVEL_WEB_TOKEN"] = "sekret"
    try:
        client2 = TestClient(create_app(output_dir=tmp_path))
        assert client2.get("/api/config").json()["auth_required"] is True
        assert client2.get("/api/novels").status_code == 401
        assert (
            client2.get("/api/novels", headers={"X-Auth-Token": "sekret"}).status_code
            == 200
        )
    finally:
        os.environ.pop("NOVEL_WEB_TOKEN", None)


def test_create_job_invalid_url(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post("/api/jobs", json={"url": "not-a-url"})
    assert res.status_code == 400


def test_create_job_invalid_volume(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/jobs", json={"url": "https://example.com", "volume_size": 75}
    )
    assert res.status_code == 400


def test_create_job_runs_to_done(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post("/api/jobs", json={"url": "https://example.com/novel"})
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    async def wait():
        for _ in range(50):
            jres = client.get(f"/api/jobs/{job_id}")
            if jres.json()["state"] in ("done", "error"):
                return jres.json()
            await asyncio.sleep(0.01)
        return jres.json()

    data = asyncio.run(wait())
    assert data["state"] == "done"
    assert data["result"]["slug"] == "novela"


def test_list_jobs_empty(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/api/jobs").json() == []


def test_list_jobs_shows_active_and_done(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    manager = client.app.state.manager
    manager._jobs["aaa"] = Job(
        id="aaa", url="https://example.com/one", output_dir=tmp_path,
        state="running", slug="one",
    )
    manager._jobs["bbb"] = Job(
        id="bbb", url="https://example.com/two", output_dir=tmp_path,
        state="done", slug="two",
    )

    jobs = client.get("/api/jobs").json()
    by_id = {j["id"]: j for j in jobs}
    assert by_id["aaa"]["state"] == "running"
    assert by_id["aaa"]["slug"] == "one"
    assert by_id["bbb"]["state"] == "done"


def test_list_novels_empty(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/api/novels").json() == []


def test_list_novels_with_manifest(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    Manifest(
        slug="novela",
        title="Novela",
        chapters_downloaded=10,
        chapters_empty=2,
        chapters_empty_nums=[3, 7],
    ).save(slug_dir)

    client = _client(monkeypatch, tmp_path)
    novels = client.get("/api/novels").json()
    assert len(novels) == 1
    assert novels[0]["slug"] == "novela"
    assert novels[0]["chapters_downloaded"] == 10
    assert novels[0]["chapters_empty"] == 2
    assert novels[0]["chapters_empty_nums"] == [3, 7]


def test_epub_404_when_missing(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/novels/novela/epub/missing.epub")
    assert res.status_code == 404


def test_epub_download(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    epub = slug_dir / "Novela 1-50.epub"
    epub.write_bytes(b"PK\x03\x04 fake epub")
    Manifest(slug="novela", title="Novela").save(slug_dir)

    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/novels/novela/epub/Novela 1-50.epub")
    assert res.status_code == 200
    assert res.content == b"PK\x03\x04 fake epub"


def test_sync_novel_not_found(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/api/novels/inexistente/sync").status_code == 404


def test_sync_novel_missing_url(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    Manifest(slug="novela", title="Novela", source_url="").save(slug_dir)
    client = _client(monkeypatch, tmp_path)
    assert client.post("/api/novels/novela/sync").status_code == 400


def test_sync_novel_creates_job(monkeypatch, tmp_path):
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir()
    Manifest(
        slug="novela",
        title="Novela",
        source_url="https://example.com/novel",
        translated=True,
        volume_size=100,
    ).save(slug_dir)

    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr("novel_cli.web.jobs.run_pipeline", fake)
    client = TestClient(create_app(output_dir=tmp_path))

    res = client.post("/api/novels/novela/sync")
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    assert job_id

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["url"] == "https://example.com/novel"
    assert captured["translate"] is True
    assert captured["volume_size"] == 100
    assert captured["download_all"] is False
    assert captured["force"] is False


def test_job_translate_concurrency_propagated(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr("novel_cli.web.jobs.run_pipeline", fake)
    client = TestClient(create_app(output_dir=tmp_path))

    res = client.post(
        "/api/jobs",
        json={"url": "https://example.com/novel", "translate": True, "translate_concurrency": 8},
    )
    assert res.status_code == 200
    assert captured["translate_concurrency"] == 8


def test_job_translate_concurrency_zero_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/jobs",
        json={"url": "https://example.com/novel", "translate_concurrency": 0},
    )
    assert res.status_code == 400
