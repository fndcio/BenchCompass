"""B5: SQLite geçmiş/zaman serisi + community pano testleri (network yok)."""

import sqlite3

from benchcompass_benchmark_eval import history
from benchcompass_benchmark_eval.scripts.generate_md import _match_community


def _make_db(tmp_path):
    db = tmp_path / "bench.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE benchmarks (id INTEGER PRIMARY KEY, model TEXT, provider TEXT,"
        " measured_tps REAL, ttft_ms REAL, total_tokens INTEGER, wall_clock_s REAL,"
        " shared INTEGER, error TEXT, created_at TEXT, source TEXT)"
    )
    rows = [
        ("m1", 40.0, "2026-08-01 10:00:00", "real"),
        ("m1", 44.0, "2026-08-02 10:00:00", "real"),
        ("m1", 47.0, "2026-08-03 10:00:00", "plugin-eval"),
        ("m2", 55.0, "2026-08-01 10:00:00", "real"),
    ]
    for model, tps, created, src in rows:
        con.execute(
            "INSERT INTO benchmarks(model, provider, measured_tps, created_at, source)"
            " VALUES(?,?,?,?,?)",
            (model, "ollama", tps, created, src),
        )
    con.commit()
    con.close()
    return db


def test_load_history_parses_series(tmp_path):
    db = _make_db(tmp_path)
    series = history.load_history(str(db))

    assert set(series.keys()) == {"m1", "m2"}
    assert [r["tps"] for r in series["m1"]] == [40.0, 44.0, 47.0]
    assert series["m1"][0]["created_at"] == "2026-08-01 10:00:00"
    assert series["m1"][0]["source"] == "real"


def test_load_history_missing_db(tmp_path):
    assert history.load_history(str(tmp_path / "yok.db")) == {}


def test_summarize_history_trends(tmp_path):
    db = _make_db(tmp_path)
    summ = history.summarize_history(history.load_history(str(db)))

    assert summ["m1"]["measurements"] == 3
    assert summ["m1"]["last_tps"] == 47.0
    assert summ["m1"]["trend"] == "yükseliyor"
    assert summ["m2"]["trend"] == "sabit"


def test_match_community():
    rows = [
        {
            "model": {"displayName": "Qwen3 8B Instruct", "hfId": "Qwen/Qwen3-8B"},
            "tokSOut": 55.0,
        },
        {
            "model": {"displayName": "Llama 3 8B", "hfId": "meta-llama/Llama-3-8B"},
            "tokSOut": 60.0,
        },
        {
            "model": {"displayName": "Gemma 2 9B", "hfId": "google/gemma-2-9b"},
            "tokSOut": 50.0,
        },
    ]
    matches = _match_community("qwen3:8b", rows)
    assert len(matches) == 1
    assert matches[0]["tokSOut"] == 55.0

    assert (
        _match_community("llama3:8b", rows)
        and _match_community("llama3:8b", rows)[0]["tokSOut"] == 60.0
    )
    assert _match_community("gemma4:12b", rows) == []


def test_generate_md_includes_history_and_community(monkeypatch, tmp_path):
    from benchcompass_benchmark_eval import config, llmfit_data
    from benchcompass_benchmark_eval.scripts import generate_md

    # Regresyon: bu test bir zamanlar `config.REPORTS_DIR`'i izole etmiyordu ve
    # üretilen MD, git'te takipli `reports/index.md`'nin üzerine yazılıyordu.
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out")
    monkeypatch.setattr(
        "benchcompass_benchmark_eval.history.load_history",
        lambda: {"m1": [{"tps": 47.0}]},
    )
    monkeypatch.setattr(
        llmfit_data,
        "resolve",
        lambda *a, **k: llmfit_data.LlmfitData(
            mode="snapshot",
            source_path="x",
            benchmark_cache={
                "presets": {
                    "RTX 4070 Ti (12 GB)": {
                        "rows": [
                            {
                                "model": {"displayName": "Qwen3 8B"},
                                "tokSOut": 55.0,
                            }
                        ]
                    }
                }
            },
        ),
    )
    run = {
        "generated_at": "2026-08-04T00:00:00",
        "hardware": {},
        "conditions": {},
        "task_ids": [],
        "tasks": [],
        "models": [
            {
                "model": "qwen3:8b",
                "speed": {"gen_tps": 50.0, "prefill_tps": 500.0, "ttft_ms": 100},
                "quality": {"score": 80.0, "passed": 4, "total": 5},
            }
        ],
    }
    inp = tmp_path / "r.json"
    inp.write_text(__import__("json").dumps(run, ensure_ascii=False), encoding="utf-8")
    md = generate_md.generate_md(inp).read_text(encoding="utf-8")

    assert "Geçmiş / Zaman Serisi" in md
    assert "Community Karşılaştırma Panosu" in md
    assert "yükseliyor" not in md  # sadece trend satırları history'den gelir
