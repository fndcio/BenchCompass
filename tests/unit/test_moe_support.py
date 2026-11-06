"""Unit tests for MoE (Mixture-of-Experts) architecture detection (Sprint 08)."""

from api.notes_parser import parse_moe_info


def test_parse_moe_info_mixtral_8x7b():
    """Mixtral 8x7B detection returns is_moe=True, active=13B, total=47B."""
    res = parse_moe_info("Mixtral-8x7B-Instruct-v0.1", "8x7b moe model")
    assert res["is_moe"] is True
    assert res["active_params_b"] == 13.0
    assert res["total_params_b"] == 47.0


def test_parse_moe_info_mixtral_8x22b():
    """Mixtral 8x22B detection returns is_moe=True, active=39B, total=141B."""
    res = parse_moe_info("Mixtral-8x22B-v0.1", "")
    assert res["is_moe"] is True
    assert res["active_params_b"] == 39.0
    assert res["total_params_b"] == 141.0


def test_parse_moe_info_dense_model():
    """Standard dense model (e.g. Qwen2.5-32B) returns is_moe=False."""
    res = parse_moe_info("Qwen2.5-32B-Instruct", "dense coding model")
    assert res["is_moe"] is False
    assert res["active_params_b"] is None
    assert res["total_params_b"] is None
