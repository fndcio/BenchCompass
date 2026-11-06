"""B2: Context stres testi (needle-in-haystack) — network yok, mock Ollama."""

import json

import pytest

from benchcompass_benchmark_eval import harness, runner
from benchcompass_benchmark_eval.scripts import run_benchmark


@pytest.mark.parametrize(
    "answer,needle,expected",
    [
        ("The code is 7GOLDEN42.", "7GOLDEN42", True),
        ("the secret code is 7golden42", "7GOLDEN42", True),
        ("I do not know.", "7GOLDEN42", False),
    ],
)
def test_recall_passes(answer, needle, expected):
    assert harness._recall_passes(answer, needle) is expected


def test_context_stress_builds_prompt_and_parses(monkeypatch):
    sent: dict = {}

    def fake_post(url, payload, timeout):
        sent["payload"] = payload
        fake = {
            "model": "qwen3:8b",
            "prompt_eval_count": 32000,
            "prompt_eval_duration": 1600000000,
            "eval_count": 8,
            "eval_duration": 400000000,
            "response": "7GOLDEN42",
        }
        return json.dumps(fake).encode("utf-8")

    monkeypatch.setattr(harness, "_post", fake_post)

    res = harness.context_stress("qwen3:8b", 32000, "7GOLDEN42", "What is the code?")

    # Num_ctx istenen uzunluğun 2 katı olmalı (kırpma olmasın)
    assert sent["payload"]["options"]["num_ctx"] == 64000
    assert "NEEDLE: 7GOLDEN42" in sent["payload"]["prompt"]
    assert res["prefill_tps"] == 20000.0  # 32000 / 1.6s
    assert res["gen_tps"] == 20.0  # 8 / 0.4s
    assert res["recall"] is True
    assert res["ctx_tokens"] == 32000


def test_context_stress_error_graceful(monkeypatch):
    def boom(url, payload, timeout):
        raise harness.OllamaError("Ollama erişilemiyor")

    monkeypatch.setattr(harness, "_post", boom)
    res = harness.context_stress("qwen3:8b", 32000, "X", "Q")
    assert "error" in res


def test_parse_ctx_lengths():
    assert run_benchmark._parse_ctx_lengths("32k,64k,128k") == [32000, 64000, 128000]
    assert run_benchmark._parse_ctx_lengths("8000") == [8000]


def test_context_stress_test_per_model(monkeypatch):
    def fake_stress(model, ctx, needle, question):
        return {
            "ctx_tokens": ctx,
            "prefill_tps": 100.0,
            "recall": True,
            "model": model,
        }

    monkeypatch.setattr(harness, "context_stress", fake_stress)
    res = runner.context_stress_test(["m1", "m2"], [32000, 64000])

    assert set(res.keys()) == {"m1", "m2"}
    assert len(res["m1"]) == 2
    assert res["m1"][0]["recall"] is True


def test_run_eval_includes_context_stress(monkeypatch):
    monkeypatch.setattr(
        harness,
        "context_stress",
        lambda model, ctx, needle, question: {
            "ctx_tokens": ctx,
            "prefill_tps": 50.0,
            "recall": True,
        },
    )
    run = runner.run_eval(
        ["m1"],
        [{"id": "t1", "type": "word", "prompt": "p", "expected": "yes"}],
        speed_runs=1,
        do_speed=False,
        do_quality=False,
        ctx_lengths=[32000],
    )
    assert "context_stress" in run
    assert "m1" in run["context_stress"]
