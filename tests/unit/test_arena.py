"""tests/unit/test_arena.py — Local Model Arena ve Çift-Kör Karşılaştırma Testleri (P1-3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.arena_elo import calculate_elo_delta
from api.db import connect
from api.main import app

client = TestClient(app)


def test_arena_elo_delta_math() -> None:
    # İki eşit model (1000 vs 1000), A kazanırsa: Sa=1, Ea=0.5 -> delta=32*0.5=16
    delta_a, delta_b = calculate_elo_delta(1000.0, 1000.0, score_a=1.0, k=32.0)
    assert delta_a == 16.0
    assert delta_b == -16.0

    # Berabere biterse: Sa=0.5, Ea=0.5 -> delta=0
    delta_a_draw, delta_b_draw = calculate_elo_delta(
        1000.0, 1000.0, score_a=0.5, k=32.0
    )
    assert delta_a_draw == 0.0
    assert delta_b_draw == 0.0


def test_arena_duel_sequential_execution() -> None:
    payload = {
        "model_a": "qwen3.5:4b",
        "model_b": "gemma4:12b",
        "prompt": "Test prompt",
        "max_tokens": 50,
    }
    res = client.post("/api/arena/duel", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OK"
    assert data["mode"] == "sequential_fair_duel"
    assert data["blind"] is False
    assert "shared_gpu_notice" in data
    assert "results" in data
    assert "model_a" in data["results"]
    assert "model_b" in data["results"]
    assert "winner" in data
    assert data["winner"] in (payload["model_a"], payload["model_b"])
    assert "duel_id" in data


def test_arena_blind_mode_and_voting(monkeypatch, tmp_path) -> None:
    # İzole DB
    test_db = tmp_path / "test_arena.db"
    monkeypatch.setattr("api.db.DB", test_db)

    # DB hazırla
    con = connect()
    con.close()

    model_a_name = "secret-model-alpha"
    model_b_name = "secret-model-beta"

    # 1. Kör düello başlat
    duel_req = {
        "model_a": model_a_name,
        "model_b": model_b_name,
        "prompt": "Kör karşılaştırma testi için prompt.",
        "max_tokens": 40,
        "blind": True,
    }
    res = client.post("/api/arena/duel", json=duel_req)
    assert res.status_code == 200
    duel_data = res.json()

    assert duel_data["status"] == "OK"
    assert duel_data["mode"] == "blind_duel"
    assert duel_data["blind"] is True
    duel_id = duel_data["duel_id"]
    assert duel_id is not None

    # Model isimleri maskelenmiş olmalı
    res_a = duel_data["results"]["model_a"]
    res_b = duel_data["results"]["model_b"]
    assert res_a["model"] == "Model A"
    assert res_b["model"] == "Model B"
    assert model_a_name not in [res_a["model"], res_b["model"]]
    assert model_b_name not in [res_a["model"], res_b["model"]]
    # Response metninde de asla sızıntı olmamalı
    assert model_a_name not in res_a.get("response", "")
    assert model_b_name not in res_a.get("response", "")
    assert model_a_name not in res_b.get("response", "")
    assert model_b_name not in res_b.get("response", "")

    # 2. Oylama yap (Model A'yı seç)
    vote_req = {
        "duel_id": duel_id,
        "choice": "a",
    }
    vote_res = client.post("/api/arena/vote", json=vote_req)
    assert vote_res.status_code == 200
    vote_data = vote_res.json()

    assert vote_data["status"] == "OK"
    revealed = vote_data["data"]["revealed"]
    assert "model_a" in revealed
    assert "model_b" in revealed
    assert {revealed["model_a"], revealed["model_b"]} == {model_a_name, model_b_name}

    winner = vote_data["data"]["winner"]
    assert winner in (model_a_name, model_b_name)

    elo_changes = vote_data["data"]["elo_changes"]
    assert winner in elo_changes
    assert elo_changes[winner]["new_elo"] > 1000.0

    # 3. Aynı düelloya mükerrer oy verilememeli
    dup_res = client.post("/api/arena/vote", json=vote_req)
    assert dup_res.status_code == 400

    # 4. Liderlik tablosunu sorgula
    board_res = client.get("/api/arena/leaderboard")
    assert board_res.status_code == 200
    board_data = board_res.json()
    assert board_data["count"] == 2
    leader = board_data["leaderboard"][0]
    assert leader["model"] == winner
    assert leader["wins"] == 1
    assert leader["elo"] > 1000.0


# ---------------------------------------------------------------------------
# P1-3 kalıntı: harf-duyarsız maskeleme + error alanı sızıntı koruması
# ---------------------------------------------------------------------------
def test_arena_blind_mask_harf_duyarsiz_ve_error_alani(monkeypatch, tmp_path) -> None:
    """Maskeleme harf-duyarsız olmalı; `error` alanı da doğrudan sızıntı assert'ine tabi.

    Eski `str.replace` harf-duyarlıydı → backend hatada ismi büyük harfle yazsa
    ('SECRET-MODEL-ALPHA bulunamadı') sızıntı geçiyordu; `error` alanı için de
    doğrudan assert yoktu (yalnız response taranıyordu).
    """
    monkeypatch.setattr("api.db.DB", tmp_path / "test_arena_mask.db")
    con = connect()
    con.close()

    def sahte_kosu(model: str, prompt: str, max_tokens: int) -> dict:
        # response + error alanlarına harf varyantlarıyla model adını göm
        return {
            "model": model,
            "response": f"Deneme yanıtı: {model} ve {model.upper()} çalışıyor.",
            "error": None,
            "tok_per_sec": 40.0,
            "ttft_ms": 100.0,
            "total_tokens": 20,
        }

    def sahte_kosu_hatli(model: str, prompt: str, max_tokens: int) -> dict:
        # hatada ismi büyük harfle yazar (bazı backend davranışı)
        return {
            "model": model,
            "response": "",
            "error": f"backend hatası: {model.upper()} bulunamadı",
            "tok_per_sec": 0.0,
            "ttft_ms": 9999.0,
            "total_tokens": 0,
        }

    from api.routes import arena as arena_mod

    def secici(model: str, prompt: str, max_tokens: int) -> dict:
        if model == "secret-model-beta":
            return sahte_kosu_hatli(model, prompt, max_tokens)
        return sahte_kosu(model, prompt, max_tokens)

    monkeypatch.setattr(arena_mod, "_run_single_model", secici)

    res = client.post(
        "/api/arena/duel",
        json={
            "model_a": "secret-model-alpha",
            "model_b": "secret-model-beta",
            "prompt": "harf-duyarlılık testi",
            "max_tokens": 40,
            "blind": True,
        },
    )
    assert res.status_code == 200
    data = res.json()

    # Her kanadın kendi adının üç harf varyantı da response+error'da olmamalı
    beklenen_sizinti = {
        "model_a": ["secret-model-alpha", "SECRET-MODEL-ALPHA", "Secret-Model-Alpha"],
        "model_b": ["secret-model-beta", "SECRET-MODEL-BETA", "Secret-Model-Beta"],
    }
    for kanat, varyantlar in beklenen_sizinti.items():
        r = data["results"][kanat]
        for alan in ("response", "error"):
            metin = r.get(alan) or ""
            for v in varyantlar:
                assert v not in metin, f"{kanat}.{alan} sızıntısı: {v!r}"

    # Etiketler yerinde
    assert data["results"]["model_a"]["model"] == "Model A"
    assert data["results"]["model_b"]["model"] == "Model B"
