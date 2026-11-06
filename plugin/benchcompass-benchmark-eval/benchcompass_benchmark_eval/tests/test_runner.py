"""Runner testleri — mock Ollama ile değerlendirme akışı, network yok."""

import pytest

from benchcompass_benchmark_eval import config, harness, runner


@pytest.fixture
def tasks():
    return [
        {
            "id": "ar1",
            "type": "num",
            "prompt": "What is 17 times 23?",
            "expected": "391",
        },
        {
            "id": "tr7",
            "type": "word",
            "prompt": "Turkiyenin baskenti neresi?",
            "expected": "ankara",
        },
    ]


def test_evaluate_model_with_mocks(monkeypatch, tasks):
    monkeypatch.setattr(
        harness,
        "measure_speed",
        lambda model: {
            "gen_tps": 60.0,
            "prefill_tps": 600.0,
            "ttft_ms": 150.0,
            "total_ms": 1000.0,
            "eval_count": 60,
            "load_ms": 100.0,
            "model": model,
        },
    )
    monkeypatch.setattr(
        harness,
        "generate",
        lambda model, prompt, num_predict, temperature, think: (
            "391" if "17 times 23" in prompt else "Ankara"
        ),
    )

    res = runner.evaluate_model(
        "m1", tasks, speed_runs=2, do_speed=True, do_quality=True
    )
    assert res["speed"]["gen_tps"] == 60.0
    assert res["quality"]["score"] == 100.0
    assert res["quality"]["passed"] == 2
    assert "ci_low" in res["quality"]
    assert "ci_high" in res["quality"]


def test_speed_error_does_not_crash(monkeypatch, tasks):
    def boom(model):
        raise RuntimeError("ollama yok")

    monkeypatch.setattr(harness, "measure_speed", boom)
    res = runner.evaluate_model(
        "m1", tasks, speed_runs=1, do_speed=True, do_quality=False
    )
    assert "error" in res["speed"]


def test_quality_error_tallied_as_fail(monkeypatch, tasks):
    def boom(model, prompt, num_predict, temperature, think):
        raise RuntimeError("üretim hatası")

    monkeypatch.setattr(harness, "generate", boom)
    res = runner.evaluate_model(
        "m1", tasks, speed_runs=1, do_speed=False, do_quality=True
    )
    assert res["quality"]["passed"] == 0
    assert res["quality"]["failed"] == 2


def test_save_results_and_sqlite(tmp_path, monkeypatch, tasks):
    run = runner.run_eval(["m1"], tasks, speed_runs=1, do_speed=False, do_quality=False)
    out = runner.save_results(run, tmp_path / "r.json")
    assert out.exists()

    db = tmp_path / "bench.db"
    import sqlite3

    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE benchmarks (id INTEGER PRIMARY KEY, model TEXT, provider TEXT, measured_tps REAL, ttft_ms REAL, total_tokens INTEGER, wall_clock_s REAL, shared INTEGER, error TEXT, created_at TEXT, source TEXT)"
    )
    con.commit()
    con.close()

    monkeypatch.setattr(config, "find_parent_sqlite", lambda: db)
    run2 = {
        "models": [
            {
                "model": "m1",
                "speed": {
                    "gen_tps": 55.0,
                    "ttft_ms": 100.0,
                    "eval_count": 55,
                    "total_ms": 2000.0,
                },
            }
        ]
    }
    res = runner.write_sqlite(run2)
    assert res["inserted"] == 1

    con = sqlite3.connect(db)
    row = con.execute("SELECT model, source, measured_tps FROM benchmarks").fetchone()
    con.close()
    assert row == ("m1", "plugin-eval", 55.0)


def test_hash_tasks_deterministic(tasks):
    sha1 = runner.hash_tasks(tasks)
    sha2 = runner.hash_tasks(tasks)
    assert sha1 == sha2
    assert len(sha1) == 12


def test_run_eval_has_statistical_fields(tasks):
    run = runner.run_eval(
        ["m1"], tasks, speed_runs=1, do_speed=False, do_quality=False, seed=99
    )
    assert run["seed"] == 99
    assert run["n_runs"] == 1
    assert "task_sha" in run


# ---------------------------------------------------------------------------
# P0-4 — seed gerçekten hesaplamaya bağlı (görev sırası) + N≥3
# ---------------------------------------------------------------------------
def _six_tasks(tasks):
    """Determinizm testi için 6 görev (2 görevlik fixture'ı genişletir)."""
    return [{**tasks[i % 2], "id": f"t{i}"} for i in range(6)]


def test_same_seed_same_task_order(tasks):
    """Aynı seed → aynı görev sırası (tekrarlanabilir koşu kanıtı)."""
    ts = _six_tasks(tasks)
    r1 = runner.run_eval(["m1"], ts, do_speed=False, do_quality=False, seed=42)
    r2 = runner.run_eval(["m1"], ts, do_speed=False, do_quality=False, seed=42)
    assert r1["task_order"] == r2["task_order"]
    # task_sha kanonik (özgün) sırayla hesaplanır — seed'ten bağımsız
    assert r1["task_sha"] == r2["task_sha"]


def test_different_seed_different_task_order(tasks):
    """Farklı seed → farklı görev sırası (seed dekoratif değil, etkin)."""
    ts = _six_tasks(tasks)
    r1 = runner.run_eval(["m1"], ts, do_speed=False, do_quality=False, seed=42)
    r3 = runner.run_eval(["m1"], ts, do_speed=False, do_quality=False, seed=7)
    assert r1["task_order"] != r3["task_order"]
    assert r1["task_sha"] == r3["task_sha"]


def test_default_speed_runs_is_three(tasks):
    """P0-4: varsayılan hız tekrar sayısı N≥3."""
    assert config.DEFAULTS["speed_runs"] >= 3
    run = runner.run_eval(["m1"], tasks, do_speed=False, do_quality=False)
    assert run["n_runs"] == config.DEFAULTS["speed_runs"]


# ---------------------------------------------------------------------------
# Adım 3 — McNemar pairwise (ADR-0015)
# ---------------------------------------------------------------------------
def test_pairwise_comparison_mcnemar():
    """İki modelin detaylarından pairwise McNemar + drill-down."""
    results = [
        {
            "model": "a-model",
            "quality": {
                "details": [
                    {"id": "t1", "pass": True},
                    {"id": "t2", "pass": True},
                    {"id": "t3", "pass": False},
                ]
            },
        },
        {
            "model": "b-model",
            "quality": {
                "details": [
                    {"id": "t1", "pass": True},
                    {"id": "t2", "pass": False},
                    {"id": "t3", "pass": False},
                ]
            },
        },
    ]
    pairs = runner.pairwise_comparison(results)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["model_a"] == "a-model"
    assert pair["model_b"] == "b-model"
    assert pair["n"] == 3
    assert pair["b"] == 1
    assert pair["c"] == 0
    assert "p_value" in pair
    assert len(pair["tasks"]) == 3


def test_run_eval_terminal_pairwise_alan(tasks):
    """run_eval çıktısında top-level pairwise alanı var (boş olgularda [])."""
    run = runner.run_eval(["m1"], tasks, do_speed=False, do_quality=False)
    assert "pairwise" in run
    assert run["pairwise"] == []
