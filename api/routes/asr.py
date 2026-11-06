"""api/routes/asr.py — ASR (Whisper) teşhis endpoint'leri (Sprint 56, Özellik 5).

control_center.py'den ayrıldı (0.28.0-rc.2 denetim kapanışı): dosya başına
500+ satır kuralı (Y7) yüzünden ASR bölümü kendi route modülüne taşındı;
routes/ altındaki dosya-başına-router desenine uyar (ollama.py, telemetry.py).

Endpoint'ler:
    GET /api/asr/status     — ASR runtime + ffmpeg + model taraması
    GET /api/telemetry/asr  — aynı yanıt (alias)
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
from itertools import islice
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .shared import BASE

router = APIRouter()
logger = logging.getLogger("llmfit.dashboard")

# Tarama sınırları (denetim kapanışı): sınırsız rglob büyük HuggingFace
# önbelleğinde /api/asr/status'u bloklıyordu.
_SCAN_MAX_FILES = 5000
_SCAN_MAX_RESULTS = 100


def _detect_asr_runtime() -> tuple[str, bool, bool]:
    """ASR çalışma motorunu ve ffmpeg varlığını tespit eder.

    Sıra (dürüst etiketleme — denetim düzeltmesi): whisper.cpp ikilisi →
    openai-whisper CLI'sı → faster-whisper (python) → openai-whisper (python)
    → transformers+torch (python). ``shutil.which("whisper")`` pip
    openai-whisper'ın CLI entry-point'idir; "whisper-cli" DEĞİLDİR.
    """
    has_ffmpeg = shutil.which("ffmpeg") is not None

    if shutil.which("whisper-cli") is not None:
        return "whisper.cpp (whisper-cli)", True, has_ffmpeg
    if shutil.which("whisper") is not None:
        return "openai-whisper (cli)", True, has_ffmpeg
    if importlib.util.find_spec("faster_whisper") is not None:
        return "faster-whisper (python)", True, has_ffmpeg
    if importlib.util.find_spec("whisper") is not None:
        return "openai-whisper (python)", True, has_ffmpeg
    if (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
    ):
        return "transformers/pytorch (python)", True, has_ffmpeg
    return "none", False, has_ffmpeg


def _asr_search_dirs() -> list[Path]:
    """Taranacak model dizinleri: repo models/, whisper cache, HF hub, Ollama.

    Ollama deposu (denetim kapanışı): ``OLLAMA_MODELS`` ortam değişkeni
    tanımlıysa o önceliklidir; yoksa ``~/.ollama/models`` varsayılandır.
    """
    dirs = [
        BASE / "models",
        Path.home() / ".cache" / "whisper",
        Path.home() / ".cache" / "huggingface" / "hub",
    ]
    env_dir = os.environ.get("OLLAMA_MODELS")
    dirs.append(Path(env_dir) if env_dir else Path.home() / ".ollama" / "models")
    return dirs


def _scan_asr_models() -> tuple[list[dict[str, Any]], bool, str | None]:
    """Diskteki potansiyel Whisper/ASR model dosyalarını sınırlı tarar.

    Returns:
        (detected_models, truncated, scan_error) — tarama hatası yutulmaz,
        yanıta ``scan_error`` olarak taşınır ve loglanır (Y3/Y5).
    """
    detected: list[dict[str, Any]] = []
    truncated = False
    scan_error: str | None = None
    home = str(Path.home())

    for sdir in _asr_search_dirs():
        if not sdir.exists():
            continue
        try:
            for f in islice(sdir.rglob("*"), _SCAN_MAX_FILES):
                if not f.is_file():
                    continue
                if not any(w in f.name.lower() for w in ("whisper", "asr")):
                    continue
                if len(detected) >= _SCAN_MAX_RESULTS:
                    truncated = True
                    break
                size_mb = round(f.stat().st_size / (1024**2), 2)
                raw_path = (
                    str(f.relative_to(BASE)) if f.is_relative_to(BASE) else str(f)
                )
                rel_path = raw_path.replace(home, "~")
                detected.append(
                    {
                        "name": f.name,
                        "path": rel_path,
                        "size_mb": size_mb,
                        "format": f.suffix.lstrip(".").lower() or "bin",
                    }
                )
        except Exception as e:  # noqa: BLE001 — hata yutulmaz, yanıta taşınır
            logger.warning("ASR model taraması hatası (%s): %s", sdir, e)
            scan_error = f"{sdir}: {e}"

    return detected, truncated, scan_error


@router.get("/api/asr/status")
@router.get("/api/telemetry/asr")
def asr_status() -> dict[str, Any]:
    """ASR (Whisper) ses modelleri ve çalışma ortamı teşhis paneli (Özellik 5)."""
    runtime_engine, runtime_available, has_ffmpeg = _detect_asr_runtime()

    missing_prerequisites: list[str] = []
    if not runtime_available:
        missing_prerequisites.append(
            "ASR motoru (faster-whisper, openai-whisper, whisper-cli veya transformers+torch)"
        )
    if not has_ffmpeg:
        missing_prerequisites.append("ffmpeg (ses akış dönüşümü ve ön işleme için)")

    detected_models, truncated, scan_error = _scan_asr_models()
    total_size_mb = sum(m["size_mb"] for m in detected_models)

    if truncated:
        logger.info(
            "ASR model taraması sonuç sınırına ulaştı (ilk %s)", _SCAN_MAX_RESULTS
        )

    return {
        "ok": True,
        "runtime_available": runtime_available,
        "runtime_engine": runtime_engine,
        "ffmpeg_available": has_ffmpeg,
        "missing_prerequisites": missing_prerequisites,
        "detected_models": detected_models,
        "candidate_count": len(detected_models),
        "total_size_mb": round(total_size_mb, 2),
        "truncated": truncated,
        "scan_error": scan_error,
        "recommendation": (
            "ASR ses modellerini çalıştırmak için 'pip install faster-whisper' kurun "
            "ve ffmpeg ikilisini sistem PATH'ine ekleyin."
            if missing_prerequisites
            else "ASR çalışma ortamı hazır."
        ),
    }
