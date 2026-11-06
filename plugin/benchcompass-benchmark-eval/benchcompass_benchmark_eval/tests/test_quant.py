"""B1: Çoklu quant karşılaştırma testleri (network yok — saf fonksiyonlar)."""

import pytest

from benchcompass_benchmark_eval import harness, runner


@pytest.mark.parametrize(
    "name,expected",
    [
        ("qwen3:8b-q4_K_M", "q4_K_M"),
        ("qwen3:8b-q8_0", "q8_0"),
        ("qwen3:8b-Q4_K_M", "Q4_K_M"),
        ("llama3:8b-fp16", "fp16"),
        ("llama3:8b-bf16", "bf16"),
        ("qwen3:8b", None),
        ("mistral:7b-iq4_xs", "iq4_xs"),
    ],
)
def test_model_quant(name, expected):
    assert harness.model_quant(name) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("qwen3:8b-q4_K_M", "qwen3:8b"),
        ("qwen3:8b-q8_0", "qwen3:8b"),
        ("llama3:8b-fp16", "llama3:8b"),
        ("qwen3:8b", "qwen3:8b"),
    ],
)
def test_model_family(name, expected):
    assert harness.model_family(name) == expected


def _sample(model, tps, score):
    return {
        "model": model,
        "speed": {"gen_tps": tps, "prefill_tps": tps * 10, "ttft_ms": 100},
        "quality": {"score": score},
    }


def test_quant_comparison_groups_same_family():
    results = [
        _sample("qwen3:8b-q4_K_M", 55.0, 82.0),
        _sample("qwen3:8b-q8_0", 45.0, 90.0),
        _sample("gemma4:12b", 40.0, 88.0),  # quant yok -> dahil edilmez
    ]
    groups = runner.quant_comparison(results)

    assert len(groups) == 1
    g = groups[0]
    assert g["family"] == "qwen3:8b"
    assert len(g["entries"]) == 2
    quants = {e["quant"] for e in g["entries"]}
    assert quants == {"q4_K_M", "q8_0"}


def test_quant_comparison_single_quant_excluded():
    results = [_sample("qwen3:8b-q4_K_M", 55.0, 82.0), _sample("llama3:8b", 40.0, 80.0)]
    assert runner.quant_comparison(results) == []
