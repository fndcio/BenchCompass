"""Unit & Integration tests for api/routes/control_center.py — Control Center endpoints.

Tests all 7 aggregation endpoints:
- GET /api/cc/status
- GET /api/cc/flags
- GET /api/cc/versions
- GET /api/cc/recent
- GET /api/cc/diagnostics
- GET /api/cc/docs
- GET /api/cc/db-info
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_cc_status_endpoint():
    """GET /api/cc/status returns health, services, database, and hardware information."""
    resp = client.get("/api/cc/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "health" in data
    assert "services" in data
    assert "dashboard" in data["services"]
    assert data["services"]["dashboard"]["online"] is True
    assert "database" in data
    assert "hardware" in data
    assert "version" in data


def test_cc_flags_endpoint():
    """GET /api/cc/flags returns an aggregated list of flags and severity counts."""
    resp = client.get("/api/cc/flags")
    assert resp.status_code == 200
    data = resp.json()
    assert "flags" in data
    assert "counts" in data
    assert "total" in data
    assert isinstance(data["flags"], list)
    assert isinstance(data["counts"], dict)
    assert "critical" in data["counts"]
    assert "high" in data["counts"]


def test_cc_versions_endpoint():
    """GET /api/cc/versions returns version consistency status across files."""
    resp = client.get("/api/cc/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "versions" in data
    assert "application" in data["versions"]
    assert "frontend" in data["versions"]
    assert "authoritative_version" in data
    assert data["authoritative_version"] is not None


def test_cc_recent_endpoint():
    """GET /api/cc/recent returns a list of recent activity events."""
    resp = client.get("/api/cc/recent?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)


def test_cc_diagnostics_endpoint():
    """GET /api/cc/diagnostics returns runtime diagnostics."""
    resp = client.get("/api/cc/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert "os" in data
    assert "python" in data
    assert "database" in data
    assert "sqlite_version" in data["database"]


def test_cc_docs_endpoint():
    """GET /api/cc/docs returns list of documents found in the project."""
    resp = client.get("/api/cc/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    assert "total" in data
    assert data["total"] > 0
    names = [doc["name"] for doc in data["documents"]]
    assert "README.md" in names
    assert "DEVELOPMENT.md" in names and "AGENTS.md" not in names


def test_cc_db_info_endpoint():
    """GET /api/cc/db-info returns database stats and integrity status."""
    resp = client.get("/api/cc/db-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "path" in data
    assert "exists" in data
    assert "size_mb" in data
    assert "tables" in data
