"""tests/integration/test_concurrent_api.py — Adım 4 eşzamanlılık API'si.

Gerçek FastAPI app + izole SQLite. openai_generate monkeypatch'lenir
(ağ yok); paralel mantık gerçek (ThreadPoolExecutor).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from api import db as dbmod

    monkeypatch.setattr(dbmod, "DB", tmp_path / "concurrent.db")

    def fake_generate(*args, **kwargs) -> dict:
        return {"tps": 40.0, "ttft_ms": 90.0, "itl_ms": 10.0, "total_duration_s": 1.0}

    monkeypatch.setattr(
        "api.routes.ollama.run_concurrent_stress", _real_stress(fake_generate)
    )
    from api.main import app

    return TestClient(app)


def _real_stress(fake):
    from api import concurrent_bench

    def runner(*args, **kwargs):
        return concurrent_bench.run_concurrent_stress(
            kwargs["model"],
            kwargs["base_url"],
            kwargs["prompt"],
            kwargs["max_tokens"],
            kwargs["levels"],
            generate_fn=fake,
        )

    return runner


def test_concurrent_benchmark_yazar_ve_doner(client, tmp_path):
    res = client.post(
        "/api/benchmark/concurrent",
        json={"model": "m1", "backend": "lmstudio", "levels": [1, 2]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["results"]) == 2
    assert [r["concurrency"] for r in data["results"]] == [1, 2]

    hist = client.get("/api/benchmark/concurrent")
    assert hist.status_code == 200
    assert len(hist.json()["results"]) >= 2


def test_concurrent_benchmark_ollama_durust_hata(client):
    res = client.post(
        "/api/benchmark/concurrent",
        json={"model": "m", "backend": "ollama", "levels": [1]},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is False
