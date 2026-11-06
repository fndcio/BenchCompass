"""CI mock sözleşme testi (P1-7).

conftest'teki `MOCK_SPEED_RESULT`, runner'ın `harness.measure_speed`'ten beklediği
sözleşmeyle uyumlu OLMALIDIR. Eski mock `tps`/`output_tokens` anahtarları döndürüyordu;
runner `s.get("gen_tps")` ile filtrelediği için mock sonuçları sessizce eleniyordu —
testler yeşil kalıyor, CI'da hız verisi anlamını yitiriyordu (Y24 dersi: dış sözleşmeyi
varsayma, gerçek tüketiciyle doğrula).

Bu test mock'u gerçek runner akışından geçirir: `evaluate_model(do_speed=True)`
mock'lu `measure_speed` sonucunu kabul etmeli ve `gen_tps` değerini taşımalıdır.
"""

import importlib.util
from pathlib import Path

from benchcompass_benchmark_eval import harness, runner


def _load_conftest():
    """conftest.py'yi modül olarak yükler (tests/ bir paket değil)."""
    path = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location("bc_eval_conftest", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mock_schema_matches_runner_contract(monkeypatch):
    """CI mock'u runner.evaluate_model tarafından kabul edilmeli (gen_tps taşınmalı)."""
    conf = _load_conftest()
    monkeypatch.setattr(
        harness, "measure_speed", lambda *a, **kw: dict(conf.MOCK_SPEED_RESULT)
    )
    res = runner.evaluate_model(
        "mock-model", tasks=[], speed_runs=1, do_speed=True, do_quality=False
    )
    assert res["speed"] is not None
    assert res["speed"].get("gen_tps") == conf.MOCK_SPEED_RESULT["gen_tps"]


def test_mock_schema_covers_real_measure_speed_keys():
    """Mock, gerçek measure_speed dönüş anahtarlarının tümünü kapsamalı (şema kayması koruması)."""
    conf = _load_conftest()
    real_keys = {
        "gen_tps",
        "prefill_tps",
        "ttft_ms",
        "total_ms",
        "eval_count",
        "prompt_eval_count",
        "load_ms",
        "model",
    }
    assert real_keys <= set(conf.MOCK_SPEED_RESULT), (
        "CI mock şeması gerçek measure_speed sözleşmesinden geride kaldı — "
        "harness.measure_speed dönüş dict'i ile senkronize et"
    )
