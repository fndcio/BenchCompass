"""api/routes/discovery.py — Zero-Config Yerel Model Keşfi & SQLite Önbelleği.

C:\\AI_Models altındaki modelleri struct/mmap ile hafif tarar;
SQLite tabanlı mtime/size önbelleği tutarak I/O darboğazını önler
(ADR-0012, Ortakheyet konsensüsü).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .. import db as dbmod
from ..gguf_parser import read_gguf_metadata
from ..system_info import get_hardware_specs

logger = logging.getLogger(__name__)
router = APIRouter()

# Güvenli taranabilir kök dizinler whitelist'i (DeepSeek güvenlik kuralı)
ALLOWED_SCAN_ROOTS = [
    Path(r"C:\AI_Models"),
    Path(r"C:\AI_Models\GGUF"),
    Path("models").resolve(),
    Path("data").resolve(),
]

# Tarama kökü modül sabitidir — testler monkeypatch ile izole tmp'ye yönlendirir
# (Y18 ruhu: test gerçek kullanıcı model dizinine dokunmaz).
BASE_SCAN_DIR = Path(r"C:\AI_Models\GGUF")


def _is_path_allowed(path: Path) -> bool:
    """Yolun whitelist altındaki güvenli köklerden birinde olduğunu doğrular."""
    try:
        resolved = path.resolve()
        for root in ALLOWED_SCAN_ROOTS:
            if root.exists():
                try:
                    resolved.relative_to(root.resolve())
                    return True
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001
        return False
    return False


def _fit_level(vram_needed: float, user_vram: float) -> str:
    """VRAM gereksinimine göre uyum bantı (saf — dosyasız test edilebilir).

    PERFECT: gereksinim donanım VRAM'ine sığar; WARNING: %15 cache payı
    dahil %25'e kadar taşar; TOO_LARGE: ötesi.
    """
    if vram_needed <= user_vram:
        return "PERFECT"
    if vram_needed <= user_vram * 1.25:
        return "WARNING"
    return "TOO_LARGE"


def scan_and_sync_local_models(force_rescan: bool = False) -> list[dict[str, Any]]:
    """Yerel GGUF modellerini tarar, SQLite cache ile senkronlar ve döndürür."""
    con = dbmod.connect()
    hw = get_hardware_specs()
    user_vram = float(hw.get("vram_gb", 12.0))

    if force_rescan:
        con.execute("DELETE FROM local_models_cache")
        con.commit()

    # Mevcut cache kayıtları
    cached_rows = con.execute("SELECT * FROM local_models_cache").fetchall()
    cache_map = {row["file_path"]: dict(row) for row in cached_rows}

    found_files: list[Path] = []
    if BASE_SCAN_DIR.exists():
        found_files = list(BASE_SCAN_DIR.rglob("*.gguf"))

    current_paths: set[str] = set()
    result: list[dict[str, Any]] = []

    for file_path in found_files:
        p_str = str(file_path.resolve())
        current_paths.add(p_str)

        try:
            st = file_path.stat()
            file_mtime = st.st_mtime
            file_size = st.st_size
            file_size_gb = round(file_size / (1024**3), 2)
        except Exception:  # noqa: BLE001
            continue

        # Önbellek kontrolü (mtime + size eşleşmesi)
        cached = cache_map.get(p_str)
        if (
            cached
            and abs(cached["mtime"] - file_mtime) < 1e-4
            and cached["size_bytes"] == file_size
        ):
            result.append(cached)
            continue

        # Yeni veya değişmiş dosya — hafif header parse
        meta = read_gguf_metadata(file_path)
        if meta.get("error"):
            continue

        # VRAM gereksinimi: Dosya boyutu + %15 KV cache / runtime overhead
        vram_needed = round(file_size_gb * 1.15, 2)
        fit_level = _fit_level(vram_needed, user_vram)

        con.execute(
            """
            INSERT OR REPLACE INTO local_models_cache(
                file_path, file_name, size_bytes, size_gb, mtime,
                architecture, quant_type, context_length, general_name,
                tensor_count, vram_required_gb, fit_level, last_scanned
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p_str,
                file_path.name,
                file_size,
                file_size_gb,
                file_mtime,
                meta.get("architecture", "unknown"),
                meta.get("quant_type", "UNKNOWN"),
                meta.get("context_length", 4096),
                meta.get("general_name", file_path.stem),
                meta.get("tensor_count", 0),
                vram_needed,
                fit_level,
                datetime.now().isoformat(),
            ),
        )

        record = {
            "file_path": p_str,
            "file_name": file_path.name,
            "size_bytes": file_size,
            "size_gb": file_size_gb,
            "mtime": file_mtime,
            "architecture": meta.get("architecture", "unknown"),
            "quant_type": meta.get("quant_type", "UNKNOWN"),
            "context_length": meta.get("context_length", 4096),
            "general_name": meta.get("general_name", file_path.stem),
            "tensor_count": meta.get("tensor_count", 0),
            "vram_required_gb": vram_needed,
            "fit_level": fit_level,
        }
        result.append(record)

    # Silinmiş dosyaları önbellekten temizle
    deleted_paths = set(cache_map.keys()) - current_paths
    if deleted_paths:
        for dpath in deleted_paths:
            con.execute("DELETE FROM local_models_cache WHERE file_path = ?", (dpath,))

    con.commit()
    con.close()

    result.sort(key=lambda x: x.get("size_gb", 0), reverse=True)
    return result


@router.get("/api/models/local-fs")
def get_local_models() -> dict[str, Any]:
    """C:\\AI_Models altındaki GGUF modellerini önbellek destekli döner."""
    models = scan_and_sync_local_models(force_rescan=False)
    hw = get_hardware_specs()
    return {
        "status": "OK",
        "total_models": len(models),
        "hardware": hw,
        "models": models,
    }


@router.post("/api/models/local-fs/rescan")
def rescan_local_models() -> dict[str, Any]:
    """Önbelleği temizleyip dosya sisteminden tam yeniden tarama yapar."""
    models = scan_and_sync_local_models(force_rescan=True)
    return {
        "status": "OK",
        "message": "Model önbelleği başarıyla yenilendi.",
        "total_models": len(models),
        "models": models,
    }
