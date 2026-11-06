"""
Integration testler — api/collector_api.py (port 8790 kontrol API)
==========================================================================
Test piramidi katman 2 (integration): gerçek FastAPI app + gerçek SQLite,
subprocess mock'lanır (gerçek benchmark_collector.py çalışmaz).

AGENTS.md §6: dış bağımlılık (subprocess) mock'lanır, dahili mantık ASLA.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Collector API TestClient."""
    from api.collector_api import app

    return TestClient(app)


@pytest.fixture()
def mock_subprocess(monkeypatch):
    """subprocess.run'i mock'la — gerçek collector çalışmasın.

    AGENTS.md §6: dış bağımlılık mock'lanır. Gerçek benchmark_collector.py
    çalıştırılmaz (network/llmfit CLI gerektirir).
    """

    class FakeProc:
        returncode = 0
        stdout = "[mock] collector completed"
        stderr = ""

    def fake_run(*_args, **_kwargs):
        return FakeProc()

    monkeypatch.setattr("api.collector_api.subprocess.run", fake_run)
    return fake_run


# =============================================================================
# /health endpoint
# =============================================================================
class TestCollectorHealth:
    def test_health_returns_ok_and_runs(self, client):
        """AGENTS.md §6: güçlü onaylama — ok + db + runs alanları."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "db" in data
        assert "runs" in data
        assert isinstance(data["runs"], int)


# =============================================================================
# /api/dashboard/history endpoint
# =============================================================================
class TestCollectorHistory:
    def test_history_returns_list(self, client):
        response = client.get("/api/dashboard/history")

        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_history_items_have_metadata_fields(self, client):
        """History öğeleri run metadata'sı içermeli (id, name, source, vb.)."""
        response = client.get("/api/dashboard/history")
        data = response.json()

        if data["history"]:
            item = data["history"][0]
            # Run metadata alanları (model detayı yok — collector özelliği)
            assert "id" in item


# =============================================================================
# /api/dashboard/summary endpoint
# =============================================================================
class TestCollectorSummary:
    def test_summary_source_is_collector_api(self, client):
        """Collector summary'si source='collector-api' döner (dashboard ana API değil)."""
        response = client.get("/api/dashboard/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "collector-api"
        assert "history" in data
        assert "latest" in data
        # latest.models bilerek boş (dashboard ana API'den çekiliyor)
        assert data["latest"]["models"] == []


# =============================================================================
# /api/collector/run endpoint (subprocess mock'lu)
# =============================================================================
class TestCollectorRun:
    """POST /api/collector/run — benchmark_collector.py tetikleme."""

    def test_run_returns_collector_run_result(self, client, mock_subprocess):
        """Mock'lu subprocess sonucu CollectorRunResult shape'i döner."""
        response = client.post("/api/collector/run")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True  # returncode=0 → ok
        assert "stdout" in data
        assert "stderr" in data
        assert "runs" in data
        assert isinstance(data["runs"], int)
        assert "[mock]" in data["stdout"]

    def test_run_failed_subprocess_returns_ok_false(self, client, monkeypatch):
        """subprocess başarısız (returncode=1) → ok=False."""

        class FakeFailProc:
            returncode = 1
            stdout = ""
            stderr = "collector error"

        monkeypatch.setattr(
            "api.collector_api.subprocess.run",
            lambda *_a, **_kw: FakeFailProc(),
        )

        response = client.post("/api/collector/run")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "collector error" in data["stderr"]
