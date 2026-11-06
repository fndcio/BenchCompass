"""
Unit testler — api/notes_parser.py
==========================================================================
Notes metninden regex ile yapısal alan çıkarma (VRAM, RAM, context, quant, speed).

AGENTS.md §6: saf fonksiyon testi (DB/network yok). parse_notes ASLA fırlatma
yapmaz (resilience) — bozuk girdi güvenli şekilde ele alınır.
"""

from __future__ import annotations

import pytest

from api.notes_parser import (
    _flatten_notes,
    enrich_model,
    extract_param_count,
    parse_notes,
)


# =============================================================================
# _flatten_notes — tip dönüşümü
# =============================================================================
class TestFlattenNotes:
    """notes alanını düz metne çevirme."""

    def test_none_returns_empty(self):
        assert _flatten_notes(None) == ""

    def test_str_passthrough(self):
        assert _flatten_notes("Need 7.6 GB VRAM") == "Need 7.6 GB VRAM"

    def test_list_to_json(self):
        result = _flatten_notes(["a", "b"])
        assert "a" in result
        assert "b" in result

    def test_dict_to_json(self):
        result = _flatten_notes({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_int_to_str(self):
        assert _flatten_notes(42) == "42"


# =============================================================================
# parse_notes — VRAM/RAM çıkarma
# =============================================================================
class TestParseNotesVramRam:
    """'Need X GB VRAM or Y GB system RAM' deseninden değer çıkarma."""

    def test_full_vram_ram_pattern(self):
        notes = "Need 7.6 GB VRAM or 8.3 GB system RAM"
        result = parse_notes(notes)
        assert result["required_vram_gb"] == pytest.approx(7.6)
        assert result["required_ram_gb"] == pytest.approx(8.3)

    def test_no_vram_ram_returns_none(self):
        result = parse_notes("Just some random notes without specs")
        assert result["required_vram_gb"] is None
        assert result["required_ram_gb"] is None

    def test_empty_notes(self):
        result = parse_notes("")
        assert result["required_vram_gb"] is None
        assert result["required_ram_gb"] is None

    def test_none_notes_never_raises(self):
        """AGENTS.md resilience: parse_notes ASLA fırlatma yapmaz."""
        result = parse_notes(None)
        assert result["required_vram_gb"] is None
        assert isinstance(result, dict)


# =============================================================================
# parse_notes — context length
# =============================================================================
class TestParseNotesContext:
    """Context cap ve supported limit çıkarma."""

    def test_capped_and_supported(self):
        notes = "Context capped at 8192 tokens for estimation (supports up to 32768)"
        result = parse_notes(notes)
        assert result["context_length_estimated_at"] == 8192
        assert result["context_length_supported"] == 32768

    def test_estimated_only(self):
        notes = "Context capped at 4096 tokens"
        result = parse_notes(notes)
        assert result["context_length_estimated_at"] == 4096
        assert result["context_length_supported"] is None

    def test_supported_only(self):
        notes = "Model supports up to 16384 tokens"
        result = parse_notes(notes)
        assert result["context_length_supported"] == 16384


# =============================================================================
# parse_notes — quantization & speed
# =============================================================================
class TestParseNotesQuantSpeed:
    def test_quant_from_hardware(self):
        notes = "Best quantization for hardware: Q8_0"
        result = parse_notes(notes)
        assert result["quantization"] == "Q8_0"

    def test_speed_extraction(self):
        notes = "Baseline estimated speed: 66.7 tok/s"
        result = parse_notes(notes)
        assert result["estimated_speed_tok_s"] == pytest.approx(66.7)

    def test_quant_from_model_name_when_notes_empty(self):
        """notes'ta quant yoksa model adından çıkarılır."""
        result = parse_notes("", model_name="Qwen2.5-14B-Instruct-AWQ")
        assert result["quantization"] == "AWQ"

    def test_quant_from_model_name_q4(self):
        result = parse_notes("", model_name="model-Q4_K_M")
        assert result["quantization"] is not None
        assert "Q4" in result["quantization"]


# =============================================================================
# parse_notes — loaded_into_vram / insufficient ipuçları
# =============================================================================
class TestParseNotesHints:
    def test_loaded_into_vram_flag(self):
        result = parse_notes("GPU: model loaded into VRAM successfully")
        assert result["loaded_into_vram"] is True
        assert result["insufficient"] is False

    def test_insufficient_flag(self):
        result = parse_notes("Insufficient VRAM for this model")
        assert result["insufficient"] is True
        assert result["loaded_into_vram"] is False

    def test_no_flags(self):
        result = parse_notes("Plain notes about the model")
        assert result["loaded_into_vram"] is False
        assert result["insufficient"] is False


# =============================================================================
# parse_notes — tam zengin notes (entegrasyon)
# =============================================================================
class TestParseNotesRichExample:
    def test_full_rich_notes(self):
        """Gerçek llmfit çıktısına benzer zengin notes."""
        notes = (
            "Need 7.6 GB VRAM or 8.3 GB system RAM. "
            "Context capped at 8192 tokens for estimation (supports up to 32768). "
            "Best quantization for hardware: Q6_K. "
            "Baseline estimated speed: 45.2 tok/s."
        )
        result = parse_notes(notes, model_name="test-model")
        assert result["required_vram_gb"] == pytest.approx(7.6)
        assert result["required_ram_gb"] == pytest.approx(8.3)
        assert result["context_length_estimated_at"] == 8192
        assert result["context_length_supported"] == 32768
        assert result["quantization"] == "Q6_K"
        assert result["estimated_speed_tok_s"] == pytest.approx(45.2)

    def test_never_raises_on_garbage(self):
        """AGENTS.md resilience: hiçbir girdi exception fırlatmamalı."""
        for garbage in [None, "", "???", 12345, [], {}, {"x": object()}]:
            result = parse_notes(garbage)
            assert isinstance(result, dict)


# =============================================================================
# extract_param_count
# =============================================================================
class TestExtractParamCount:
    """Model adından parametre sayısı (milyar) çıkarma."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Qwen/Qwen2.5-Coder-14B-Instruct", 14.0),
            ("meta-llama/Llama-3.2-11B-Vision", 11.0),
            ("Qwen/Qwen2.5-7B", 7.0),
            ("model-0.5B-small", 0.5),
            ("model-70B-large", 70.0),
        ],
    )
    def test_known_param_sizes(self, name, expected):
        assert extract_param_count(name) == pytest.approx(expected)

    def test_no_param_returns_none(self):
        assert extract_param_count("model-without-param-size") is None

    def test_none_returns_none(self):
        assert extract_param_count(None) is None

    def test_empty_returns_none(self):
        assert extract_param_count("") is None


# =============================================================================
# enrich_model
# =============================================================================
class TestEnrichModel:
    """parse_notes + extract_param_count birleşimi."""

    def test_enrich_combines_both(self):
        notes = "Need 5.0 GB VRAM or 6.0 GB system RAM"
        result = enrich_model("Qwen2.5-7B-Instruct", notes)
        assert result["required_vram_gb"] == pytest.approx(5.0)
        assert result["required_ram_gb"] == pytest.approx(6.0)
        assert result["param_count_b"] == pytest.approx(7.0)

    def test_enrich_empty_notes_still_extracts_param(self):
        result = enrich_model("Llama-3.2-11B", "")
        assert result["param_count_b"] == pytest.approx(11.0)
        assert result["required_vram_gb"] is None

    def test_enrich_returns_all_keys(self):
        result = enrich_model("test", "notes")
        expected_keys = {
            "required_vram_gb",
            "required_ram_gb",
            "context_length_supported",
            "context_length_estimated_at",
            "quantization",
            "param_count_b",
            "estimated_speed_tok_s",
            "loaded_into_vram",
            "insufficient",
        }
        assert expected_keys.issubset(result.keys())
