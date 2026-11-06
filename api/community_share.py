"""api/community_share.py — Opt-In Topluluk Paylaşımı ve PII Sanitizasyon Protokolü (P1-4).

§16 Telemetri & Privacy Protokolü uyumlu:
- Varsayılan olarak kapalıdır (opt_in: false).
- PII (kullanıcı adı, yerel dosya yolları, tam GPU modeli) tamamen filtrelenir.
- Donanım modeli genelleştirilmiş GPU sınıfına (Tier) dönüştürülür.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "share_config.json"

GPU_TIER_KEYWORDS: list[tuple[str, str]] = [
    ("5090", "Enthusiast GPU (24GB+)"),
    ("4090", "Enthusiast GPU (24GB+)"),
    ("5080", "High-End GPU (16GB)"),
    ("4080", "High-End GPU (16GB)"),
    ("5070", "High-End GPU (12GB)"),
    ("4070", "High-End GPU (12GB)"),
    ("3090", "Enthusiast GPU (24GB)"),
    ("3080", "High-End GPU (10-12GB)"),
    ("4060", "Mid-Range GPU (8-16GB)"),
    ("3060", "Mid-Range GPU (12GB)"),
    ("3050", "Entry GPU (8GB)"),
    ("m4", "Apple Silicon Unified Memory (M4)"),
    ("m3", "Apple Silicon Unified Memory (M3)"),
    ("m2", "Apple Silicon Unified Memory (M2)"),
    ("m1", "Apple Silicon Unified Memory (M1)"),
]


def load_share_config() -> dict[str, Any]:
    """config/share_config.json dosyasını yükler."""
    if not CONFIG_PATH.is_file():
        return {
            "opt_in": False,
            "share_endpoint": "https://github.com/BenchCompass/benchcompass-community/issues/new",
            "include_fields": [
                "model_family",
                "quant",
                "gpu_tier",
                "tps_normalized",
                "score",
            ],
            "exclude_fields": ["gpu_name", "system_path", "username"],
        }
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def anonymize_gpu(raw_gpu_name: str | None) -> str:
    """Tam GPU adını PII içermeyen genel donanım sınıfına (Tier) dönüştürür."""
    if not raw_gpu_name:
        return "Unknown Hardware Tier"
    raw_lower = raw_gpu_name.lower()
    for kw, tier in GPU_TIER_KEYWORDS:
        if kw in raw_lower:
            return tier
    if "nvidia" in raw_lower or "rtx" in raw_lower:
        return "Generic NVIDIA GPU"
    if "amd" in raw_lower or "radeon" in raw_lower:
        return "Generic AMD GPU"
    if "apple" in raw_lower:
        return "Apple Silicon Unified Memory"
    return "Generic CPU / System RAM"


def sanitize_payload(
    model: str,
    measured_tps: float,
    raw_gpu: str = "",
    provider: str = "ollama",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Kullanıcı verilerini PII'dan arındırılmış anonim paylaşım sözlüğüne dönüştürür."""
    extra = extra or {}
    gpu_tier = anonymize_gpu(raw_gpu)

    # Model adından quant ve aile çıkarımı
    model_clean = re.sub(
        r"^[A-Za-z]:[\\/].*", "local_model", model
    )  # Dosya yolu sızıntısını önle
    model_parts = model_clean.split(":")
    model_family = model_parts[0]
    quant = model_parts[1] if len(model_parts) > 1 else "unknown"

    sanitized = {
        "model_family": model_family,
        "quant": quant,
        "gpu_tier": gpu_tier,
        "measured_tps": round(measured_tps, 1),
        "provider": provider,
        "score_normalized": extra.get("score"),
        "anon_tag": "benchcompass-v0.28",
    }
    return sanitized


def build_github_issue_url(
    sanitized: dict[str, Any],
    repo_issues_url: str | None = None,
) -> str:
    """Anonim veriyi içeren GitHub Issue ön-doldurma bağlantısını üretir."""
    endpoint = (
        repo_issues_url
        or "https://github.com/BenchCompass/benchcompass-community/issues/new"
    )
    title = f"[Benchmark] {sanitized['model_family']} ({sanitized['quant']}) on {sanitized['gpu_tier']}"
    body = (
        "### BenchCompass Anonim Topluluk Benchmark Paylaşımı\n\n"
        "```json\n"
        f"{json.dumps(sanitized, indent=2, ensure_ascii=False)}\n"
        "```\n\n"
        "> Bu veri BenchCompass yerel istemcisi tarafından PII filtrelemesi yapılarak üretilmiştir."
    )
    params = urllib.parse.urlencode({"title": title, "body": body})
    return f"{endpoint}?{params}"
