"""tests/integration/test_redteam_api.py — Adım 6 red-team API'si.

Gerçek FastAPI app. Network yok. Gerçek DB'ye dokunulmaz ( endpoints
benchmark_quality kullanmaz ).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from api import db as dbmod

    monkeypatch.setattr(dbmod, "DB", tmp_path / "redteam.db")
    con = dbmod.connect()
    con.close()
    from api.main import app

    return TestClient(app)


def test_redteam_plan_lists_six_tasks(client):
    res = client.get("/api/eval/redteam-plan")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["tasks"]) == 6
    assert any(t["id"] == "rt_dan" for t in data["tasks"])
    # İç desenler API'ye sızmamalı
    assert "_harmful" not in str(data)


def test_redteam_grade_refusal_passes(client):
    res = client.post(
        "/api/eval/redteam/grade",
        json={"task_id": "rt_dan", "response": "Sorry, I cannot help."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["pass"] is True
    assert data["reason"] == "reddetti"


def test_redteam_grade_unknown_task_422(client):
    res = client.post(
        "/api/eval/redteam/grade",
        json={"task_id": "yok", "response": "x"},
    )
    assert res.status_code == 422
