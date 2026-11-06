"""tests/integration/test_eval_compare_api.py — Adım 3 McNemar eşli karşılaştırma API'si.

Gerçek FastAPI app + izole SQLite (tmp_root). Gerçek DB'ye dokunulmaz.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from api import db as dbmod

    monkeypatch.setattr(dbmod, "DB", tmp_path / "compare.db")
    con = dbmod.connect()
    # İki model, 3 ortak görev: A 2/3, B 1/3, discordant=1 (A-geçti/B-kaldı)
    rows = [
        ("model-a", "G1", 1, 1),
        ("model-a", "G3", 1, 1),
        ("model-a", "G6", 0, 0),
        ("model-b", "G1", 1, 1),
        ("model-b", "G3", 0, 0),
        ("model-b", "G6", 0, 0),
    ]
    con.executemany(
        "INSERT INTO benchmark_quality(model, gorev, pass1, passN) VALUES(?,?,?,?)",
        rows,
    )
    con.commit()
    con.close()
    from api.main import app

    return TestClient(app)


def test_eval_compare_mcnemar(client):
    res = client.get(
        "/api/eval/compare", params={"model_a": "model-a", "model_b": "model-b"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["model_a"] == "model-a"
    assert data["model_b"] == "model-b"
    assert data["n"] == 3
    assert data["b"] == 1
    assert data["c"] == 0
    assert data["discordant"] == 1
    assert "p_value" in data
    cats = {r["id"]: r["category"] for r in data["tasks"]}
    assert cats == {"G1": "both_pass", "G3": "a_only", "G6": "both_fail"}


def test_eval_compare_model_yoksa_bos_karsilastirma(client):
    res = client.get(
        "/api/eval/compare", params={"model_a": "yok", "model_b": "model-a"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["n"] == 0
    assert data["p_value"] == 1.0
    assert data["tasks"] == []
