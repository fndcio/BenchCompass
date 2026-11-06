"""tests/unit/test_concurrent_bench.py — Adım 4 eşzamanlılık stres birim testleri."""

from __future__ import annotations

import pytest

from api.concurrent_bench import _percentile, run_concurrent_stress, run_one_level


def _fake_gen(latency_s: float = 0.0):
    import time as _time

    def gen(*args, **kwargs) -> dict:
        if latency_s:
            _time.sleep(latency_s)
        return {"tps": 50.0, "ttft_ms": 80.0, "itl_ms": 12.0}

    return gen


def test_percentile_basic() -> None:
    assert _percentile([], 50) == 0.0
    assert _percentile([5.0], 95) == 5.0
    ordered = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(ordered, 50) == 3.0
    assert _percentile(ordered, 100) == 5.0
    assert _percentile(ordered, 0) == 1.0


def test_run_one_level_basarili() -> None:
    res = run_one_level("m", "http://x", "prompt", 10, 4, _fake_gen())
    assert res["concurrency"] == 4
    assert res["success"] == 4
    assert res["errors"] == 0
    assert res["latency_p50_ms"] >= 0
    assert res["throughput_tps"] == 200.0  # 4 x 50


def test_run_one_level_hepsi_hata() -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("sunucu yok")

    with pytest.raises(RuntimeError, match="başarısız"):
        run_one_level("m", "http://x", "p", 10, 3, boom)


def test_run_concurrent_stress_kuyruk_etkisi() -> None:
    # N=1 baz, N=4 aynı gecikme → kuyruk 0% (sahte paralel üretim yok, ortalama benzer)
    res = run_concurrent_stress(
        "m", "http://x", "p", 10, [1, 4], generate_fn=_fake_gen()
    )
    assert [r["concurrency"] for r in res] == [1, 4]
    assert res[0]["queue_effect_pct"] == 0.0
    # N=4 p95, N=1 p95'e göre ± küçük (aynı sleep) — sayısal, 0 veya küçük alt
    assert "queue_effect_pct" in res[1]
