"""tests/unit/test_community_share.py — Topluluk Paylaşımı ve PII Sanitizasyon Testleri (P1-4)."""

from __future__ import annotations

import pytest

from api.cli import main
from api.community_share import (
    anonymize_gpu,
    build_github_issue_url,
    load_share_config,
    sanitize_payload,
)


def test_load_share_config() -> None:
    cfg = load_share_config()
    assert cfg["opt_in"] is False
    assert "exclude_fields" in cfg
    assert "gpu_name" in cfg["exclude_fields"]
    assert "username" in cfg["exclude_fields"]


def test_anonymize_gpu() -> None:
    # RTX 5070 Ti -> High-End GPU
    assert "High-End GPU" in anonymize_gpu("NVIDIA GeForce RTX 5070 Ti")
    # RTX 4090 -> Enthusiast GPU
    assert "Enthusiast GPU" in anonymize_gpu("GeForce RTX 4090 D")
    # Apple M3 -> Apple Silicon
    assert "Apple Silicon" in anonymize_gpu("Apple M3 Max")
    # None -> Unknown
    assert anonymize_gpu(None) == "Unknown Hardware Tier"


def test_sanitize_payload_no_pii() -> None:
    raw_path_model = "C:\\Users\\developer\\Desktop\\models\\qwen3:8b"
    raw_gpu = "NVIDIA GeForce RTX 5070 Ti 16GB (SN: 12345ABC)"

    sanitized = sanitize_payload(
        model=raw_path_model,
        measured_tps=48.2,
        raw_gpu=raw_gpu,
        provider="ollama",
    )

    # PII kesinlikle olmamalı
    payload_str = str(sanitized)
    assert "developer" not in payload_str
    assert "SN: 12345ABC" not in payload_str
    assert "Desktop" not in payload_str

    # Genelleştirilmiş alanlar olmalı
    assert sanitized["gpu_tier"] == "High-End GPU (12GB)"
    assert sanitized["measured_tps"] == 48.2
    assert sanitized["anon_tag"] == "benchcompass-v0.28"


def test_build_github_issue_url() -> None:
    data = {
        "model_family": "qwen3",
        "quant": "8b",
        "gpu_tier": "High-End GPU (12GB)",
        "measured_tps": 45.0,
    }
    url = build_github_issue_url(data)
    assert "github.com" in url
    assert "High-End+GPU" in url or "High-End%20GPU" in url
    assert "qwen3" in url


def test_cli_share_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    import sys

    sys.argv = ["benchcompass", "share", "--dry-run", "--model", "qwen3:8b"]
    main()
    captured = capsys.readouterr()
    assert "PII Filtrelendi" in captured.out
    assert "DRY-RUN" in captured.out
    assert "anonimleştirildi" in captured.out
    assert "developer" not in captured.out
