"""Unit tests for Multi-Runtime Provider selection and configuration (Sprint 09)."""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_get_provider_runtimes():
    """GET /api/provider/runtimes returns supported runtimes."""
    res = client.get("/api/provider/runtimes")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "runtimes" in data
    runtimes = [r["id"] for r in data["runtimes"]]
    assert "ollama" in runtimes
    assert "lmstudio" in runtimes
    assert "llamacpp" in runtimes
    assert "mlx" in runtimes


def test_get_provider_config():
    """GET /api/provider returns active provider configuration."""
    res = client.get("/api/provider")
    assert res.status_code == 200
    data = res.json()
    assert "active_provider" in data


def test_update_provider_config(tmp_root, monkeypatch):
    """PUT /api/provider updates active provider configuration."""
    res = client.put("/api/provider", json={"active_provider": "lmstudio"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["provider"]["active_provider"] == "lmstudio"
