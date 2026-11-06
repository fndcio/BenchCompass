"""
Unit tests — api/fit_scores.py (Sprint 21 use_case skorları + baseline)
==========================================================================
Model adı → aile eşleşmesi (en uzun alt-dize kazanır), use_case skorları,
frontier baseline karşılaştırması. İzole veri kullanılır (AGENTS.md §6).
"""

from __future__ import annotations

import json

import pytest

from api import fit_scores


@pytest.fixture()
def sample_usecase(tmp_path):
    """İzole use_case_benchmarks.json."""
    data = {
        "families": [
            {
                "match": ["qwen3.5-coder", "qwen3-coder", "qwen2.5-coder"],
                "scores": {"coding": 90, "reasoning": 78, "chat": 72},
            },
            {
                "match": ["deepseek-r1", "deepseek-r2"],
                "scores": {"coding": 84, "reasoning": 93, "chat": 76},
            },
            {
                "match": ["mistral"],
                "scores": {"coding": 68, "reasoning": 70, "chat": 76},
            },
        ]
    }
    path = tmp_path / "use_case_benchmarks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def sample_baselines(tmp_path):
    """İzole baselines.json."""
    data = {
        "baselines": [
            {
                "model": "claude-sonnet-4-5",
                "provider": "anthropic",
                "roles": {
                    "coding": {"quality": 9.5, "speed": 80.0, "composite": 9.6},
                    "chat": {"quality": 9.0, "speed": 82.0, "composite": 9.2},
                },
                "overall": {"quality": 9.2, "speed": 78.0, "composite": 9.3},
            },
            {
                "model": "gpt-4o",
                "provider": "openai",
                "roles": {
                    "coding": {"quality": 9.0, "speed": 85.0, "composite": 9.3},
                    "chat": {"quality": 8.8, "speed": 88.0, "composite": 9.0},
                },
                "overall": {"quality": 8.8, "speed": 83.0, "composite": 9.0},
            },
        ]
    }
    path = tmp_path / "baselines.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def fs(sample_usecase, sample_baselines):
    """sample verileri üzerinden FitScores."""
    return fit_scores.FitScores(
        usecase_path=sample_usecase, baseline_path=sample_baselines
    )


# ---------------------------------------------------------------------------
# Yükleme
# ---------------------------------------------------------------------------
def test_load_parses_families(fs):
    assert len(fs.families) == 3
    assert fs.baselines is not None


def test_load_missing_files(tmp_path):
    """Dosyalar yoksa boş veri (çökmez)."""
    f = fit_scores.FitScores(
        usecase_path=tmp_path / "yok.json", baseline_path=tmp_path / "yok2.json"
    )
    assert f.families == []
    assert f.baselines == {}


# ---------------------------------------------------------------------------
# Aile eşleşmesi — en uzun alt-dize kazanır
# ---------------------------------------------------------------------------
def test_family_match_longest_substring_wins(fs):
    """'qwen3.5-coder' hem qwen3.5-coder hem qwen3 ile eşleşir → en uzun kazanır."""
    match = fs.family_for("Qwen/Qwen3.5-Coder-7B")
    assert match is not None
    assert match["scores"]["coding"] == 90  # qwen3.5-coder (daha spesifik)


def test_family_match_simple(fs):
    """'deepseek-r1' → deepseek-r1 ailesi (reasoning 93)."""
    match = fs.family_for("DeepSeek-R1-Distill-14B")
    assert match is not None
    assert match["scores"]["reasoning"] == 93


def test_family_match_case_insensitive(fs):
    """Büyük/küçük harf duyarsız eşleşir."""
    assert fs.family_for("mistral-7b") is not None


def test_family_no_match(fs):
    """Eşleşme yoksa None (fallback dışarıda yönetilir)."""
    assert fs.family_for("bilinmeyen-model-x") is None


# ---------------------------------------------------------------------------
# Use-case skoru
# ---------------------------------------------------------------------------
def test_use_case_score(fs):
    """Aile + use_case skorunu döndürür."""
    score = fs.use_case_score("qwen3-coder", "coding")
    assert score == 90


def test_use_case_score_unknown_returns_none(fs):
    """Bilinmeyen aile/use_case → None."""
    assert fs.use_case_score("bilinmeyen", "coding") is None
    assert fs.use_case_score("qwen3-coder", "bilinmeyen-rol") is None


# ---------------------------------------------------------------------------
# Baseline karşılaştırma
# ---------------------------------------------------------------------------
def test_baseline_for_role(fs):
    """Model + rol baseline skorunu döndürür."""
    b = fs.baseline_for_role("claude-sonnet-4-5", "coding")
    assert b is not None
    assert b["composite"] == pytest.approx(9.6)


def test_baseline_for_role_unknown(fs):
    """Bilinmeyen model/rol → None."""
    assert fs.baseline_for_role("claude-sonnet-4-5", "vision") is None
    assert fs.baseline_for_role("olmayan", "coding") is None


def test_top_baseline_for_role(fs):
    """Bir rol için en yüksek composite'li baseline modeli döndürür."""
    top = fs.top_baseline_for_role("coding")
    assert top is not None
    assert top["model"] == "claude-sonnet-4-5"


def test_top_baseline_role_missing(fs):
    """Rol hiçbir modelde yoksa None."""
    assert fs.top_baseline_for_role("olmaz-boyle-rol") is None
