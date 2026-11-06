"""tests/unit/test_ollama_pull.py — Ollama Model İndirme (Pull) Route Testleri."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from api.main import app
from api import ollama_client

client = TestClient(app)


def test_ollama_pull_endpoint_starts_task(monkeypatch) -> None:
    """POST /api/ollama/pull task başlatır ve task_uuid döner."""

    def fake_pull(model_name: str, on_progress=None, timeout=1800):
        if on_progress:
            on_progress(
                {"status": "downloading", "completed": 200, "total": 1000, "pct": 20.0}
            )
        return {"ok": True, "model": model_name, "status": "success"}

    monkeypatch.setattr(ollama_client, "pull_model", fake_pull)

    res = client.post("/api/ollama/pull", json={"model": "qwen2.5:0.5b"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["model"] == "qwen2.5:0.5b"
    assert "task_uuid" in data

    task_uuid = data["task_uuid"]

    # Görevin bitmesini bekle
    deadline = time.monotonic() + 2.0
    task_data = None
    while time.monotonic() < deadline:
        t_res = client.get(f"/api/tasks/{task_uuid}")
        assert t_res.status_code == 200
        task_data = t_res.json()
        if task_data.get("status") in ("completed", "failed"):
            break
        time.sleep(0.02)

    assert task_data is not None
    assert task_data["status"] == "completed"
    assert task_data["type"] == "ollama_pull"


def test_ollama_pull_endpoint_error_handling(monkeypatch) -> None:
    """Model indirme hatası task'a failed olarak yansır."""

    def fake_pull_fail(model_name: str, on_progress=None, timeout=1800):
        raise ollama_client.OllamaError("model bulunamadı: 404")

    monkeypatch.setattr(ollama_client, "pull_model", fake_pull_fail)

    res = client.post("/api/ollama/pull", json={"model": "nonexistent:model"})
    assert res.status_code == 200
    data = res.json()
    task_uuid = data["task_uuid"]

    deadline = time.monotonic() + 2.0
    task_data = None
    while time.monotonic() < deadline:
        t_res = client.get(f"/api/tasks/{task_uuid}")
        task_data = t_res.json()
        if task_data.get("status") in ("completed", "failed"):
            break
        time.sleep(0.02)

    assert task_data is not None
    assert task_data["status"] == "failed"
    assert "model bulunamadı" in task_data["error"]
