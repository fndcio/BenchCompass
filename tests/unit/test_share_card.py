"""tests/unit/test_share_card.py — Sosyal Medya Paylaşım Kartı Üreticisi Birim Testi."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.share_card import generate_share_card_svg

client = TestClient(app)


def test_generate_share_card_svg_content() -> None:
    svg = generate_share_card_svg(
        model="Qwen-3.8B-Uncensored",
        tps=72.4,
        ttft_ms=110.0,
        tier="Tam Uyumlu",
        gpu="RTX 5070 Ti",
    )
    assert "<svg" in svg
    assert 'width="1200"' in svg
    assert 'height="630"' in svg
    assert "Qwen-3.8B-Uncensored" in svg
    assert "72.4" in svg
    assert "RTX 5070 Ti" in svg
    # Gizlilik doğrulaması: PII veya özel yol sızıntısı yok
    assert "developer" not in svg
    assert "ai_workspace" not in svg


def test_share_card_ttft_estimated_badge() -> None:
    """T2 şeffaflık: tahmin TTFT kartta "(tahmini)" olarak görünmeli."""
    svg = generate_share_card_svg(
        model="Qwen-3.8B", tps=80.0, ttft_ms=110.0, ttft_method="estimated"
    )
    assert "(tahmini)" in svg
    svg_meas = generate_share_card_svg(
        model="Qwen-3.8B", tps=80.0, ttft_ms=110.0, ttft_method="measured"
    )
    assert "(tahmini)" not in svg_meas


def test_share_card_itl_gostersin() -> None:
    """Adım 2: streaming kartta ITL (p50) satırı gösterilmeli."""
    svg = generate_share_card_svg(
        model="Qwen-3.8B",
        tps=80.0,
        ttft_ms=110.0,
        ttft_method="streaming",
        itl_ms=12.5,
    )
    assert "ITL: 12.5 ms" in svg
    svg_no = generate_share_card_svg(model="Qwen-3.8B", tps=80.0, ttft_ms=110.0)
    assert "ITL:" not in svg_no


def test_share_card_http_endpoint() -> None:
    res = client.get("/api/share-card/svg", params={"model": "Bonsai-8B", "tps": 45.0})
    assert res.status_code == 200
    assert "image/svg+xml" in res.headers.get("content-type", "")
    assert "<svg" in res.text
    assert "Bonsai-8B" in res.text


def test_share_card_with_normalized_score() -> None:
    svg = generate_share_card_svg(
        model="Qwen-3.8B",
        tps=80.0,
        score=114.5,
    )
    assert "SINIF SKORU:" in svg
    assert "%114.5" in svg


def test_normalized_score_endpoint() -> None:
    res = client.get(
        "/api/score/normalized", params={"model": "Qwen-3.8B", "tps": 50.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert "model" in data
    assert "measured_tps" in data
    assert "ref_tps" in data
    assert "score" in data
