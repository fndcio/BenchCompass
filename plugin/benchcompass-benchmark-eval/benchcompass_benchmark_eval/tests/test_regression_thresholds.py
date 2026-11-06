"""test_regression_thresholds.py — Kalite & Değerlendirme Regresyon Eşik Kapıları (P1-7)."""

from __future__ import annotations

SCORE_THRESHOLDS = {
    "b1_instruction": 0.60,  # Bu eşiğin altına düşerse kalite kapısı kırılır
    "b1_reasoning": 0.50,
    "code_generation": 0.55,
    "context_recall": 0.70,
}


def test_score_thresholds_defined() -> None:
    """Eşiklerin tanımlı ve 0-1 aralığında geçerli olduğunu doğrular."""
    for suite, threshold in SCORE_THRESHOLDS.items():
        assert 0.0 < threshold < 1.0, f"{suite} eşiği geçersiz: {threshold}"


def test_evaluate_threshold_compliance() -> None:
    """Örnek model skorlarının eşik kontrol algoritmasını doğrular."""
    sample_scores = {
        "b1_instruction": 0.75,
        "b1_reasoning": 0.62,
        "code_generation": 0.58,
        "context_recall": 0.85,
    }
    for suite, score in sample_scores.items():
        min_required = SCORE_THRESHOLDS.get(suite, 0.50)
        assert score >= min_required, (
            f"{suite} regresyon tespit edildi: {score} < {min_required}"
        )
