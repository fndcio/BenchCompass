"""Rapor üretici testleri — deterministik MD/HTML üretimi, network yok."""

import json

import pytest

from benchcompass_benchmark_eval import config
from benchcompass_benchmark_eval.scripts import generate_html, generate_md


@pytest.fixture
def results(tmp_path):
    tasks = [
        {
            "id": "ar1",
            "type": "num",
            "lang": "en",
            "difficulty": "kolay",
            "category": "aritmetik",
            "prompt": "p",
            "expected": "391",
        },
        {
            "id": "tr7",
            "type": "word",
            "lang": "tr",
            "difficulty": "kolay",
            "category": "bilgi",
            "prompt": "p",
            "expected": "ankara",
        },
    ]
    run = {
        "generated_at": "2026-08-04T00:00:00Z",
        "hardware": {"gpu": "RTX 5070 Ti", "vram_gb": 11.94, "ram_gb": 31.29},
        "conditions": {"temperature": 0.0, "think": False, "speed_runs": 2},
        "task_ids": ["ar1", "tr7"],
        "tasks": tasks,
        "models": [
            {
                "model": "test-model",
                "speed": {"gen_tps": 50.0, "prefill_tps": 500.0, "ttft_ms": 200.0},
                "quality": {
                    "total": 2,
                    "passed": 2,
                    "failed": 0,
                    "score": 100.0,
                    "details": [
                        {"id": "ar1", "type": "num", "pass": True},
                        {"id": "tr7", "type": "word", "pass": True},
                    ],
                },
            },
        ],
    }
    p = tmp_path / "results.json"
    p.write_text(json.dumps(run), encoding="utf-8")
    return p


def test_generate_md(tmp_path, results, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out")
    out = generate_md.generate_md(results)
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert "LLMFit Benchmark Eval" in md
    assert "test-model" in md
    assert "tr7" in md  # TR görev matriste var
    assert "ar1" in md


def test_generate_html(tmp_path, results, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out")
    out = generate_html.generate_html(results)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "LLMFit Benchmark Eval" in html
    assert "chart.js" in html  # hybrid: CDN denemesi var
    assert "fallbackBar" in html  # offline fallback var
    assert "test-model" in html
    assert "__DATA_JSON__" not in html  # placeholder gömülü kalmamalı


def test_md_deterministic(tmp_path, results, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out1")
    a = generate_md.generate_md(results).read_bytes()
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out2")
    b = generate_md.generate_md(results).read_bytes()
    assert a == b


def test_generators_never_touch_tracked_reports(results, tracked_reports_dir):
    """Regresyon: testler git'te takipli `reports/index.md` / `index.html`'i bozmamalı.

    Kök neden: `test_generate_md_includes_history_and_community` REPORTS_DIR'i
    izole etmiyordu ve üretilen MD takipli raporun üzerine yazılıyordu.
    """
    assert not config.REPORTS_DIR.resolve().is_relative_to(
        config.PACKAGE_DIR.resolve()
    ), "REPORTS_DIR izolasyonu yok — test depodaki raporu ezer"

    md_target = tracked_reports_dir / "index.md"
    html_target = tracked_reports_dir / "index.html"
    md_before = md_target.read_bytes()
    html_before = html_target.read_bytes()

    md_out = generate_md.generate_md(results)
    html_out = generate_html.generate_html(results)

    assert md_target.read_bytes() == md_before
    assert html_target.read_bytes() == html_before
    assert md_out.resolve() != md_target.resolve()
    assert html_out.resolve() != html_target.resolve()


def test_md_standard_task_bridge_from_config(tmp_path, results, monkeypatch):
    """P0-5: köprü bölümü config.STANDARD_TASK_MAP'ten üretilir (hardcoded değil).

    Sentinel kanıtı: haritaya eklenen yeni giriş raporda belirmeli —
    rapor config'i gerçekten okuyor olmalı (DRY/Y24).
    """
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out")
    sentinel_map = {"zz_sentinel_suite": "ZZBench-Standard"}
    monkeypatch.setattr(config, "STANDARD_TASK_MAP", sentinel_map)

    md = generate_md.generate_md(results).read_text(encoding="utf-8")

    assert "- **zz_sentinel_suite**: ZZBench-Standard" in md
    # Gerçek haritadan bir giriş sentinel ile birlikte DEĞİL — rapor yalnız
    # config'in güncel içeriğini yansıtır
    assert "- **b1_instruction**: IFEval" not in md


def test_md_standard_task_bridge_matches_current_map(tmp_path, results, monkeypatch):
    """Köprü bölümü, mevcut config.STANDARD_TASK_MAP'in TAM içeriğini taşımalı."""
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "out")
    md = generate_md.generate_md(results).read_text(encoding="utf-8")
    for key, value in config.STANDARD_TASK_MAP.items():
        assert f"- **{key}**: {value}" in md
