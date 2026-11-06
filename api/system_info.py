"""api/system_info.py — Dinamik Donanım ve VRAM Algılama Modülü.

Hardcoded donanım profilleri yerine sistemdeki gerçek GPU/VRAM ve CPU/RAM
kaynaklarını canlı sorgular (ADR-0012, Ortakheyet konsensüsü).
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
HARDWARE_FILE = CONFIG_DIR / "hardware_profile.json"


def detect_gpu_vram() -> dict[str, Any]:
    """nvidia-smi ile GPU adı, toplam VRAM ve boş VRAM değerlerini MB cinsinden çeker."""
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            line = r.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name = parts[0]
                total_mb = float(parts[1])
                free_mb = float(parts[2])
                return {
                    "detected": True,
                    "gpu_name": name,
                    "vram_total_mb": total_mb,
                    "vram_total_gb": round(total_mb / 1024, 2),
                    "vram_free_mb": free_mb,
                    "vram_free_gb": round(free_mb / 1024, 2),
                    "source": "nvidia-smi",
                }
    except Exception as exc:  # noqa: BLE001
        logger.debug("nvidia-smi algilanamadi: %s", exc)

    # Fallback: hardware_profile.json
    fallback_vram = 12.0
    fallback_gpu = "Unknown GPU"
    if HARDWARE_FILE.exists():
        try:
            cfg = json.loads(HARDWARE_FILE.read_text(encoding="utf-8"))
            active_id = cfg.get("active_profile")
            for prof in cfg.get("profiles", []):
                if prof.get("id") == active_id:
                    fallback_vram = float(prof.get("vram_gb", 12.0))
                    fallback_gpu = prof.get("gpu", fallback_gpu)
                    break
        except Exception:  # noqa: BLE001
            pass

    return {
        "detected": False,
        "gpu_name": fallback_gpu,
        "vram_total_mb": fallback_vram * 1024,
        "vram_total_gb": fallback_vram,
        "vram_free_mb": fallback_vram * 1024 * 0.8,
        "vram_free_gb": round(fallback_vram * 0.8, 2),
        "source": "hardware_profile_fallback",
    }


def get_hardware_specs() -> dict[str, Any]:
    """Tüm sistem donanım profilini döner."""
    gpu_info = detect_gpu_vram()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "gpu": gpu_info["gpu_name"],
        "vram_gb": gpu_info["vram_total_gb"],
        "vram_free_gb": gpu_info["vram_free_gb"],
        "vram_detection_source": gpu_info["source"],
    }
