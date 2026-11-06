"""Unit tests for Ollama & LLMFit CLI resilience and status endpoints (Sprint 06)."""

from fastapi.testclient import TestClient

from api.main import app
from api.ollama_client import OllamaError

client = TestClient(app)


def test_ollama_status_endpoint(monkeypatch):
    """GET /api/ollama/status returns online/offline status cleanly."""

    def mock_list():
        return [{"name": "qwen3:8b", "size_gb": 4.5}]

    monkeypatch.setattr("api.ollama_client.list_models", mock_list)
    res = client.get("/api/ollama/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["status"] == "online"
    assert data["installed_count"] == 1


def test_ollama_status_offline(monkeypatch):
    """GET /api/ollama/status when Ollama service is unreachable."""

    def mock_fail():
        raise OllamaError("Ollama API'ye erisilemiyor")

    monkeypatch.setattr("api.ollama_client.list_models", mock_fail)
    res = client.get("/api/ollama/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert data["status"] == "offline"
    assert data["installed_count"] == 0
    assert "erisilemiyor" in data["error"]


def test_llmfit_status_endpoint(monkeypatch):
    """GET /api/benchcompass/status returns binary existence status cleanly."""
    monkeypatch.setattr("api.benchcompass_proxy.find_llmfit", lambda: "/usr/bin/llmfit")
    res = client.get("/api/benchcompass/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["installed"] is True
    assert data["path"] == "/usr/bin/llmfit"


def test_llmfit_status_missing(monkeypatch):
    """GET /api/benchcompass/status when llmfit CLI is not installed."""
    monkeypatch.setattr("api.benchcompass_proxy.find_llmfit", lambda: None)
    res = client.get("/api/benchcompass/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["installed"] is False
    assert data["path"] is None


def test_ollama_models_graceful_error(monkeypatch):
    """GET /api/ollama/models returns 200 OK with error payload when offline."""

    def mock_fail():
        raise OllamaError("Ollama API offline")

    monkeypatch.setattr("api.ollama_client.list_models", mock_fail)
    res = client.get("/api/ollama/models")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert data["models"] == []
    assert "offline" in data["error"].lower() or "ollama" in data["error"].lower()


def test_ollama_benchmark_missing_cli(monkeypatch):
    """POST /api/ollama/benchmark: llmfit yok + community yoksa dürüst hata (ok=False).

    Sprint 27: endpoint benchcompass_proxy.llmfit_bench (gerçek ölçüm) → community →
    dürüst hata sırasını izler; rastgele tahmin üretilmez.
    """
    from api import benchcompass_proxy

    def mock_bench_fail(*args, **kwargs):
        raise benchcompass_proxy.LlmfitError(
            "llmfit CLI bulunamadi", command=["llmfit", "bench"]
        )

    monkeypatch.setattr("api.benchcompass_proxy.llmfit_bench", mock_bench_fail)
    monkeypatch.setattr(
        "api.routes.shared._real_benchmark", lambda model, provider="auto": None
    )
    res = client.post("/api/ollama/benchmark", json={"model": "qwen3:8b", "runs": 1})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert "llmfit" in data["error"]
