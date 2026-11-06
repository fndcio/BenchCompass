"""Integration testler: api/routes/matrix.py — Sprint 46 karar matrisi.

DB'ye seed run/model + sahte FitScores ile rol türetme ve sıralama doğrulanır.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes import matrix as matrix_mod

client = TestClient(app)


class _FakeFit:
    """Sahte fit verisi — iki rol, iki aile."""

    families = [
        {"match": ["qwen3"], "scores": {"reasoning": 80, "coding": 90}},
        {"match": ["llama"], "scores": {"reasoning": 70, "chat": 85}},
    ]
    baselines = {
        "gpt-frontier": {
            "provider": "openai",
            "roles": {"reasoning": {"quality": 95, "speed": 60, "composite": 82.0}},
        }
    }

    def use_case_score(self, model_name: str, use_case: str):
        for fam in self.families:
            for m in fam.get("match", []):
                if m in model_name.lower():
                    return fam.get("scores", {}).get(use_case)
        return None

    def top_baseline_for_role(self, role: str):
        bl = self.baselines["gpt-frontier"]["roles"].get(role)
        if not bl:
            return None
        return {"model": "gpt-frontier", "provider": "openai", **bl}


def _seed_run_with_models():
    from api import db as dbmod

    con = dbmod.connect()
    try:
        cur = con.execute(
            "INSERT INTO benchmark_runs (name, source, use_case) VALUES ('t', 'cli', 'all')"
        )
        run_id = cur.lastrowid
        con.execute(
            "INSERT INTO benchmark_models (run_id, name, provider, required_vram_gb, "
            "required_ram_gb, run_mode) VALUES (?, 'qwen3:8b', 'ollama', 6.0, 10.0, 'GPU')",
            (run_id,),
        )
        con.execute(
            "INSERT INTO benchmark_models (run_id, name, provider, required_vram_gb) "
            "VALUES (?, 'llama3:8b', 'ollama', 5.5)",
            (run_id,),
        )
        con.execute(
            "INSERT INTO benchmarks (model, provider, measured_tps, source) "
            "VALUES ('qwen3:8b', 'ollama', 41.2, 'real')"
        )
        con.commit()
    finally:
        con.close()


def test_matrix_roles_data_driven(monkeypatch):
    """Roller skor anahtarlarından görülme sırasıyla türetilir."""
    roles = matrix_mod.roles_from_fit(_FakeFit())
    assert roles == ["reasoning", "coding", "chat"]


def test_matrix_endpoint_ranking(monkeypatch):
    _seed_run_with_models()
    monkeypatch.setattr(matrix_mod, "get_fit", lambda: _FakeFit())
    d = client.get("/api/matrix").json()

    by_role = {r["role"]: r for r in d["roles"]}
    assert "reasoning" in by_role and "coding" in by_role and "chat" in by_role
    assert d["model_count"] == 2

    # reasoning: qwen3 (80) > llama3 (70)
    names = [c["name"] for c in by_role["reasoning"]["candidates"]]
    assert names[0] == "qwen3:8b"

    # coding: yalnız qwen3 aday
    coding_names = [c["name"] for c in by_role["coding"]["candidates"]]
    assert coding_names == ["qwen3:8b"]

    # chat: yalnız llama3
    chat_names = [c["name"] for c in by_role["chat"]["candidates"]]
    assert chat_names == ["llama3:8b"]

    # frontier baseline yalnız reasoning rolünde var
    assert by_role["reasoning"]["frontier_baseline"]["model"] == "gpt-frontier"
    assert by_role["chat"]["frontier_baseline"] is None


def test_matrix_candidate_carries_tier_fields(monkeypatch):
    """Aday satırı computeTier kontratı alanlarını taşır (frontend mirror)."""
    _seed_run_with_models()
    monkeypatch.setattr(matrix_mod, "get_fit", lambda: _FakeFit())
    d = client.get("/api/matrix").json()
    cand = next(
        c for r in d["roles"] for c in r["candidates"] if c["name"] == "qwen3:8b"
    )
    assert cand["required_vram_gb"] == 6.0
    assert cand["required_ram_gb"] == 10.0
    assert cand["run_mode"] == "GPU"
    assert cand["measured_tps"] == 41.2
    assert cand["score"] == 80


def test_matrix_empty_db(monkeypatch):
    monkeypatch.setattr(matrix_mod, "get_fit", lambda: _FakeFit())
    d = client.get("/api/matrix").json()
    assert d["model_count"] == 0
    assert all(r["candidates"] == [] for r in d["roles"])


def test_matrix_top_per_role_clamped(monkeypatch):
    _seed_run_with_models()
    monkeypatch.setattr(matrix_mod, "get_fit", lambda: _FakeFit())
    d = client.get("/api/matrix?top_per_role=99").json()
    for r in d["roles"]:
        assert len(r["candidates"]) <= 10  # üst sınır


# --- Görev Profili Önerisi (Sprint 47) ----------------------------------------


def test_weighted_profile_score_math():
    """Ağırlıklı ortalama: skorları bilinen değerlerle doğrula."""
    scores = {"reasoning": 80, "coding": 90, "chat": None}
    # 60/40 karışım: (80×60 + 90×40) / 100 = 84
    assert (
        matrix_mod.weighted_profile_score(scores, {"reasoning": 60, "coding": 40})
        == 84.0
    )
    # None skoru olan rol katkı vermez: yalnız coding → 90
    assert matrix_mod.weighted_profile_score(scores, {"coding": 30, "chat": 70}) == 90.0


def test_weighted_profile_score_edges():
    scores = {"reasoning": 80}
    assert matrix_mod.weighted_profile_score(scores, {}) is None  # ağırlık yok
    assert (
        matrix_mod.weighted_profile_score(scores, {"reasoning": 0}) is None
    )  # sıfır ağırlık
    assert matrix_mod.weighted_profile_score({}, {"reasoning": 50}) is None  # skor yok
    assert matrix_mod.weighted_profile_score(scores, {"yok": 50}) is None  # eşleşmez


def test_recommend_profile_endpoint(monkeypatch):
    _seed_run_with_models()
    monkeypatch.setattr(matrix_mod, "get_fit", lambda: _FakeFit())
    r = client.post(
        "/api/matrix/recommend", json={"weights": {"reasoning": 60, "coding": 40}}
    )
    assert r.status_code == 200
    d = r.json()
    # qwen3: (80×60 + 90×40)/100 = 84; llama3: sadece reasoning 70 → 70
    recs = d["recommendations"]
    assert recs[0]["name"] == "qwen3:8b"
    assert recs[0]["weighted_score"] == 84.0
    assert recs[1]["name"] == "llama3:8b"
    assert recs[1]["weighted_score"] == 70.0
    # tanınmayan rol anahtarları elenir
    assert "yok" not in d["weights_used"]


def test_recommend_profile_all_zero(monkeypatch):
    _seed_run_with_models()
    monkeypatch.setattr(matrix_mod, "get_fit", lambda: _FakeFit())
    d = client.post("/api/matrix/recommend", json={"weights": {"reasoning": 0}}).json()
    assert d["recommendations"] == []  # ağırlık toplamı 0 → dürüst boş sonuç
