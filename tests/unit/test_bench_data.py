"""
Unit tests — api/bench_data.py (Sprint 20 gerçek community benchmark verisi)
==========================================================================
benchmark_cache.json + community/*.json gerçek ölçümleri. Donanım eşleştirme
mantığı: birebir GPU adı → yakın alt-dize → boş (fallback). İzole veri kullanılır.
"""

from __future__ import annotations

import json

import pytest

from api import bench_data


@pytest.fixture()
def sample_cache(tmp_path):
    """İzole benchmark_cache.json — donanım bazlı gerçek ölçümler."""
    data = {
        "scraped_at": "2026-08-01",
        "presets": {
            "RTX 5070": {
                "total": 2,
                "rows": [
                    {
                        "model": {"hfId": "Qwen/Qwen3-7B", "displayName": "Qwen3-7B"},
                        "tokSOut": 102.5,
                        "tokSTotal": 105.0,
                        "ttftMs": 120.0,
                        "hardware": {"gpuName": "RTX 5070", "vramGb": 12},
                        "engine": {"quantization": "Q4_K_M"},
                    },
                    {
                        "model": {
                            "hfId": "meta-llama/Llama-3.2-1B",
                            "displayName": "Llama-3.2-1B",
                        },
                        "tokSOut": 465.98,
                        "tokSTotal": 470.0,
                        "ttftMs": 80.0,
                        "hardware": {"gpuName": "RTX 5070", "vramGb": 12},
                        "engine": {"quantization": "Q4_K_M"},
                    },
                ],
            },
            "RTX 5080": {
                "total": 1,
                "rows": [
                    {
                        "model": {
                            "hfId": "Qwen/Qwen3.5-9B",
                            "displayName": "Qwen3.5-9B",
                        },
                        "tokSOut": 79.6,
                        "tokSTotal": 80.0,
                        "ttftMs": 81.5,
                        "hardware": {"gpuName": "RTX 5080", "vramGb": 16},
                        "engine": {"quantization": "Q4_0"},
                    }
                ],
            },
        },
    }
    path = tmp_path / "benchmark_cache.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def bench(sample_cache):
    """sample_cache üzerinden BenchData."""
    return bench_data.BenchData(sample_cache)


# ---------------------------------------------------------------------------
# Yükleme
# ---------------------------------------------------------------------------
def test_load_parses_presets(bench):
    """presets anahtarları (donanım grupları) okunur."""
    assert "RTX 5070" in bench.presets
    assert bench.total_rows >= 3


def test_load_missing_file(tmp_path):
    """Dosya yoksa boş veri (çökmez)."""
    b = bench_data.BenchData(tmp_path / "yok.json")
    assert b.presets == {}
    assert b.total_rows == 0


# ---------------------------------------------------------------------------
# Donanım eşleştirme
# ---------------------------------------------------------------------------
def test_match_exact_gpu(bench):
    """GPU adı birebir eşleşirse o preset kullanılır."""
    rows = bench.lookup_gpu("RTX 5070")
    assert len(rows) == 2


def test_match_case_insensitive(bench):
    """GPU adı büyük/küçük harf duyarsız eşleşir."""
    rows = bench.lookup_gpu("rtx 5070")
    assert len(rows) == 2


def test_match_substring_fallback(bench):
    """Birebir yoksa alt-dize eşleşmesi dener (örn. 'RTX 5070 Laptop')."""
    rows = bench.lookup_gpu("NVIDIA GeForce RTX 5070 Laptop")
    assert len(rows) == 2  # 'RTX 5070' alt-dizesi eşleşir


def test_match_no_gpu_returns_empty(bench):
    """Eşleşme yoksa boş liste (fallback dışarıda yönetilir)."""
    assert bench.lookup_gpu("GTX 1080") == []


# ---------------------------------------------------------------------------
# Model hızı bulma
# ---------------------------------------------------------------------------
def test_get_speed_for_model(bench):
    """Donanım + model eşleşirse gerçek avg tok/s döner."""
    speed = bench.get_speed_for_model("Qwen/Qwen3-7B", gpu_name="RTX 5070")
    assert speed is not None
    assert speed["measured_tps"] == pytest.approx(102.5)
    assert speed["ttft_ms"] == pytest.approx(120.0)
    assert speed["source"] == "community"


def test_get_speed_model_not_found(bench):
    """Model bulunamazsa None (tahmine düşer)."""
    assert bench.get_speed_for_model("olmayan-model", gpu_name="RTX 5070") is None


def test_get_speed_uses_substring_gpu(bench):
    """Donanım alt-dize ile eşleşirse de model hızı bulunur."""
    speed = bench.get_speed_for_model("Llama-3.2-1B", gpu_name="GeForce RTX 5070 Ti")
    assert speed is not None
    assert speed["measured_tps"] == pytest.approx(465.98)


def test_lookup_returns_quantized_rows(bench):
    """Aynı model farklı quant'ta birden çok satır varsa tümü döner."""
    rows = bench.lookup_model("Qwen", gpu_name="RTX 5070")
    assert len(rows) >= 1


def test_speed_map_for_gpu_prefers_highest(bench):
    """speed_map aynı modelin en yüksek tokSOut'unu seçer (N+1 yok)."""
    smap = bench.speed_map_for_gpu("RTX 5070")
    assert "qwen/qwen3-7b" in smap
    assert smap["qwen/qwen3-7b"]["measured_tps"] == 102.5
    assert smap["qwen/qwen3-7b"]["source"] == "community"


def test_speed_map_for_gpu_no_match(bench):
    """Eşleşmeyen donanımda boş harita."""
    assert bench.speed_map_for_gpu("GTX 1080") == {}


def test_get_reference_tps(sample_cache):
    bd = bench_data.BenchData(sample_cache)
    # GPU ile eşleşen
    ref = bd.get_reference_tps("Qwen3-7B", "RTX 5070")
    assert ref == 102.5
    # GPU olmadan genel model ortalaması
    ref_any = bd.get_reference_tps("Qwen3-7B")
    assert ref_any is not None
    assert ref_any > 0
