"""
Unit testler — api/compat.py (tier motoru)
==========================================================================
LLMFit'in kalbi: sayısal uyumluluk motoru (Bölüm 2.2).

AGENTS.md §1.6: Tier formulu tek yerde — api/compat.py'de (backend) ve
web/app.js computeTier'da (frontend mirror). Bu testler backend tarafını
doğrular. Frontend mirror ayrı test konusudur (G8 harmony).

Test piramidi katman 1 (unit): DB/network yok, saf fonksiyon testi.
"""

from __future__ import annotations

import pytest

from api.compat import build_tooltip, compute_context_flag, compute_tier
from api.schemas import (
    ModelRecord,
    TierResult,
)


# =============================================================================
# compute_tier — GPU mode (run_mode yok veya "gpu")
# =============================================================================
class TestComputeTierGpuMode:
    """GPU modunda tier hesaplaması (varsayılan, run_mode yok)."""

    def test_perfect_fit_both_margins_met(self, omen_hardware, default_thresholds):
        """VRAM margin >= 2 AND RAM margin >= 4 → Tam Uyumlu."""
        model = ModelRecord(
            name="test-model",
            required_vram_gb=8.0,  # margin = 12 - 8 = 4 (>= 2 ✓)
            required_ram_gb=24.0,  # margin = 32 - 24 = 8 (>= 4 ✓)
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Tam Uyumlu"
        assert result.tone == "good"
        assert result.vram_margin_gb == pytest.approx(4.0)
        assert result.ram_margin_gb == pytest.approx(8.0)

    def test_borderline_both_non_negative(self, omen_hardware, default_thresholds):
        """VRAM margin >= 0 AND RAM margin >= 0 (ama tam margin şartı değil) → Sinirda."""
        model = ModelRecord(
            name="borderline-model",
            required_vram_gb=11.0,  # margin = 1 (>= 0 ✓ ama < 2)
            required_ram_gb=30.0,  # margin = 2 (>= 0 ✓ ama < 4)
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Uyumlu (Sinirda)"
        assert result.tone == "warn"

    def test_caution_vram_slightly_negative(self, omen_hardware, default_thresholds):
        """VRAM margin >= -1.5 (cpu offload payı) → Dikkatli Kullan."""
        model = ModelRecord(
            name="caution-model",
            required_vram_gb=13.0,  # margin = -1 (>= -1.5 ✓)
            required_ram_gb=20.0,
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Dikkatli Kullan"
        assert result.tone == "orange"

    def test_not_suitable_vram_far_exceeded(self, omen_hardware, default_thresholds):
        """VRAM margin < -1.5 → Uygun Degil."""
        model = ModelRecord(
            name="too-big-model",
            required_vram_gb=20.0,  # margin = -8 (< -1.5)
            required_ram_gb=20.0,
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Uygun Degil"
        assert result.tone == "bad"

    def test_ram_negative_vram_positive_demotes_tier(
        self, omen_hardware, default_thresholds
    ):
        """VRAM yeterli ama RAM eksik → Sinirda'ya düşer (good değil)."""
        model = ModelRecord(
            name="ram-heavy-model",
            required_vram_gb=8.0,  # VRAM margin = 4 (>= 2 ✓)
            required_ram_gb=40.0,  # RAM margin = -8 (< 0)
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        # RAM negatif olduğu için Tam Uyumlu olamaz
        assert result.tier != "Tam Uyumlu"
        assert result.tone != "good"


# =============================================================================
# compute_tier — Not bazlı ipuçları (sayısal veri yok)
# =============================================================================
class TestComputeTierNoteBased:
    """Sayısal veri yokken not ipuçlarına güvenen tier hesabı."""

    def test_loaded_into_vram_note_perfect(self, omen_hardware, default_thresholds):
        """'GPU: model loaded into VRAM' notu varsa → Tam Uyumlu."""
        model = ModelRecord(
            name="loaded-model",
            required_vram_gb=None,
            required_ram_gb=None,
            loaded_into_vram=True,
            insufficient=False,
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Tam Uyumlu"
        assert result.tone == "good"

    def test_insufficient_note_caution(self, omen_hardware, default_thresholds):
        """'Insufficient VRAM' notu varsa → Dikkatli Kullan (güvenli taraf)."""
        model = ModelRecord(
            name="insufficient-model",
            required_vram_gb=None,
            required_ram_gb=None,
            loaded_into_vram=False,
            insufficient=True,
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Dikkatli Kullan"
        assert result.tone == "orange"

    def test_no_data_borderline(self, omen_hardware, default_thresholds):
        """Hiç veri yoksa → Sinirda (tarafsız)."""
        model = ModelRecord(
            name="unknown-model",
            required_vram_gb=None,
            required_ram_gb=None,
            loaded_into_vram=False,
            insufficient=False,
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Uyumlu (Sinirda)"
        assert result.tone == "warn"
        assert result.vram_margin_gb is None
        assert result.ram_margin_gb is None


# =============================================================================
# compute_tier — run_mode (Sprint 12)
# =============================================================================
class TestComputeTierRunMode:
    """Sprint 12: run_mode'a göre (cpu/cpu_offload/gpu) tier hesabı.

    Not: run_mode ModelRecord şemasında bir alan DEĞİL — DB'de kolon (api/db.py:65)
    ve compat.py getattr ile runtime'da okur. Testlerde model_copy(update=...) ile
    runtime attribute olarak set edilir (gerçek DB satırındaki gibi).
    """

    def test_cpu_mode_ignores_vram(self, omen_hardware, default_thresholds):
        """CPU modunda VRAM önemsiz, RAM'e bakılır."""
        # 100GB VRAM isteyen ama CPU modunda çalışan model
        model = ModelRecord(
            name="cpu-mode-model",
            required_vram_gb=100.0,  # VRAM asla yetmez ama cpu modunda önemsiz
            required_ram_gb=20.0,  # RAM margin = 12 (>= 4 ✓)
        ).model_copy(update={"run_mode": "cpu"})
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert result.tier == "Tam Uyumlu"
        assert result.tone == "good"

    def test_cpu_offload_mode_more_forgiving(self, omen_hardware, default_thresholds):
        """CPU offload modunda VRAM daha esnek (-12GB'a kadar caution)."""
        model = ModelRecord(
            name="offload-model",
            required_vram_gb=20.0,  # VRAM margin = -8 (gpu modunda uygun değil)
            required_ram_gb=20.0,  # RAM margin = 12 (>= 0 ✓)
        ).model_copy(update={"run_mode": "cpu_offload"})
        result = compute_tier(model, omen_hardware, default_thresholds)

        # cpu_offload: vram_margin=-8 >= -12 → Dikkatli Kullan (ram_margin=12 >= 0 ✓)
        assert result.tier == "Dikkatli Kullan"
        assert result.tone == "orange"


# =============================================================================
# compute_tier — dönüş tipi kontratı
# =============================================================================
class TestComputeTierReturnType:
    """compute_tier her zaman TierResult döndürmeli (kontrat)."""

    def test_always_returns_tier_result(self, omen_hardware, default_thresholds):
        """AGENTS.md §6: güçlü onaylama — dönüş tipi TierResult olmalı."""
        model = ModelRecord(
            name="any-model", required_vram_gb=8.0, required_ram_gb=20.0
        )
        result = compute_tier(model, omen_hardware, default_thresholds)

        assert isinstance(result, TierResult)
        assert isinstance(result.tier, str)
        assert isinstance(result.tone, str)
        assert result.tier  # boş string değil
        assert result.tone  # boş string değil

    def test_thresholds_default_when_none(self, omen_hardware):
        """thresholds=None verilirse varsayılan TierThresholds kullanılır."""
        model = ModelRecord(name="model", required_vram_gb=8.0, required_ram_gb=20.0)
        result = compute_tier(model, omen_hardware, thresholds=None)

        assert isinstance(result, TierResult)
        # Varsayılan eşiklerle Tam Uyumlu olmalı (margin 4, 12 — ikisi de yeterli)
        assert result.tier == "Tam Uyumlu"


# =============================================================================
# compute_context_flag
# =============================================================================
class TestComputeContextFlag:
    """Context kısıt tahmini kontrolü."""

    def test_estimated_below_supported(self):
        """estimated < supported → flag döner."""
        model = ModelRecord(
            name="m",
            context_length_estimated_at=8192,
            context_length_supported=32768,
        )
        flag = compute_context_flag(model)
        assert flag is not None
        assert "32768" in flag

    def test_estimated_equals_supported(self):
        """estimated == supported → flag yok (kısıt yok)."""
        model = ModelRecord(
            name="m",
            context_length_estimated_at=8192,
            context_length_supported=8192,
        )
        assert compute_context_flag(model) is None

    def test_missing_context_data(self):
        """Context verisi yoksa → None."""
        model = ModelRecord(name="m")
        assert compute_context_flag(model) is None


# =============================================================================
# build_tooltip
# =============================================================================
class TestBuildTooltip:
    """Tooltip üretimi (Bölüm 2.3)."""

    def test_tooltip_contains_tier(self, omen_hardware):
        """Tooltip tier ile başlamalı."""
        model = ModelRecord(name="m", required_vram_gb=8.0, required_ram_gb=20.0)
        tooltip = build_tooltip(
            tier="Tam Uyumlu",
            model=model,
            hardware=omen_hardware,
            vram_margin=4.0,
            ram_margin=12.0,
            context_flag=None,
        )
        assert "Tier: Tam Uyumlu" in tooltip

    def test_tooltip_shows_vram_when_known(self, omen_hardware):
        """Bilinen VRAM değeri tooltip'te gösterilir."""
        model = ModelRecord(name="m", required_vram_gb=7.6, required_ram_gb=8.3)
        tooltip = build_tooltip(
            tier="Tam Uyumlu",
            model=model,
            hardware=omen_hardware,
            vram_margin=4.4,
            ram_margin=23.7,
            context_flag=None,
        )
        assert "7.6" in tooltip
        assert "12" in tooltip  # hardware VRAM

    def test_tooltip_unknown_vram_message(self, omen_hardware):
        """VRAM bilinmiyorsa 'gerekli deger bilinmiyor' mesajı."""
        model = ModelRecord(name="m", required_vram_gb=None, required_ram_gb=None)
        tooltip = build_tooltip(
            tier="Uyumlu (Sinirda)",
            model=model,
            hardware=omen_hardware,
            vram_margin=None,
            ram_margin=None,
            context_flag=None,
        )
        assert "bilinmiyor" in tooltip


# =============================================================================
# Karar Seffafligi (P0-3)
# =============================================================================
class TestDecisionTransparency:
    """P0-3 Karar Seffafligi: explanation, inputs, verify_cmd."""

    def test_decision_transparency_fields(self, omen_hardware):
        model = ModelRecord(name="qwen3:8b", required_vram_gb=7.6, required_ram_gb=8.3)
        result = compute_tier(model, omen_hardware)
        assert result.explanation != ""
        assert "VRAM marjı" in result.explanation
        assert result.inputs["vram_gb"] == omen_hardware.vram_gb
        assert result.inputs["required_vram_gb"] == 7.6
        assert result.verify_cmd == "llmfit check qwen3:8b"
