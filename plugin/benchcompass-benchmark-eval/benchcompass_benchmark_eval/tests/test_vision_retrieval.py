"""B4: Vision + RAG/embedding testleri (network yok — mock Ollama)."""

import base64
import json
import zlib

import pytest

from benchcompass_benchmark_eval import harness, runner


# --- PNG üretici ---
def test_synthetic_png_valid():
    png = harness.synthetic_png(64, 64, (255, 0, 0))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # IDAT içeriği çözülünce boyut doğru olmalı (satır başı filtresi + RGB)
    idat = png[png.index(b"IDAT") + 4 :]
    raw = zlib.decompress(idat)
    assert len(raw) == 64 * (1 + 64 * 3)


def test_vision_image_specs_distinct():
    a = harness.vision_image("solid_red")
    b = harness.vision_image("solid_green")
    c = harness.vision_image("solid_blue")
    assert a != b != c
    for img in (a, b, c):
        assert img[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(ValueError):
        harness.vision_image("bilinmeyen")


def test_vision_image_split():
    split = harness.vision_image("split_red_blue")
    assert split[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_vision_sends_base64(monkeypatch):
    sent: dict = {}

    def fake_post(url, payload, timeout):
        sent["payload"] = payload
        return json.dumps({"response": "red"}).encode("utf-8")

    monkeypatch.setattr(harness, "_post", fake_post)
    img = harness.synthetic_png(16, 16, (255, 0, 0))
    out = harness.generate_vision("minicpm-v", "What color?", img)

    assert out == "red"
    assert sent["payload"]["images"][0] == base64.b64encode(img).decode("ascii")


# --- Embedding / cosine ---
def test_cosine_identical_and_orthogonal():
    assert harness.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert harness.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert harness.cosine([], [1]) == 0.0


def test_retrieval_test_top_match(monkeypatch):
    corpus = [
        {"id": "python", "text": "python text"},
        {"id": "sqlite", "text": "sqlite text"},
        {"id": "rust", "text": "rust text"},
        {"id": "ollama", "text": "ollama text"},
    ]
    queries = [
        {"query": "python query", "expected": "python"},
        {"query": "sqlite query", "expected": "sqlite"},
        {"query": "rust query", "expected": "rust"},
    ]
    vectors = {
        "python text": [1, 0, 0],
        "sqlite text": [0, 1, 0],
        "rust text": [0, 0, 1],
        "ollama text": [1, 1, 0],
        "python query": [1, 0.1, 0],
        "sqlite query": [0.1, 1, 0],
        "rust query": [0, 0.1, 1],
    }

    def fake_embed(model, text):
        return vectors.get(text, [0, 0, 0])

    monkeypatch.setattr(harness, "embed", fake_embed)
    res = runner.retrieval_test(["embed-model"], corpus=corpus, queries=queries)

    r = res["embed-model"]
    assert r["passed"] == 3
    assert r["total"] == 3
    assert all(q["pass"] for q in r["queries"])


def test_retrieval_test_error_graceful(monkeypatch):
    def boom(model, text):
        raise harness.OllamaError("embedding modeli değil")

    monkeypatch.setattr(harness, "embed", boom)
    res = runner.retrieval_test(["not-embedding"])
    assert res["not-embedding"]["error"]
    assert res["not-embedding"]["passed"] == 0


# --- Vision görevlerinin evaluate_model akışı ---
def test_evaluate_model_vision_task(monkeypatch):
    sent: dict = {}

    def fake_generate_vision(model, prompt, image_bytes, num_predict=64):
        sent["model"] = model
        sent["has_image"] = bool(image_bytes)
        return "The color is red."

    monkeypatch.setattr(harness, "generate_vision", fake_generate_vision)
    res = runner.evaluate_model(
        "minicpm-v",
        [
            {
                "id": "vs1",
                "type": "vision",
                "image": "solid_red",
                "prompt": "What color?",
                "expected": "red",
                "accept": ["red"],
            }
        ],
        speed_runs=1,
        do_speed=False,
        do_quality=True,
    )
    assert sent["model"] == "minicpm-v"
    assert sent["has_image"] is True
    assert res["quality"]["passed"] == 1
