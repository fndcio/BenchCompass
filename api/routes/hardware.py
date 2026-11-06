"""api/routes/hardware.py — Donanım + Provider + Migrate route'ları (Sprint 31 Y7).

`api/main.py`'den taşındı: hardware GET/PUT + autodetect, provider GET/PUT/runtimes,
migrate. Davranış birebir korunur. Test uyumu: `shared.X` üzerinden erişim.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from .. import db as dbmod
from ..schemas import (
    HardwareConfig,
    HardwareUpdate,
    MigrateResult,
)
from . import shared

router = APIRouter()


@router.get("/api/hardware", response_model=HardwareConfig)
def hardware_get():
    """config/hardware_profile.json'u dondurur."""
    if not shared.HARDWARE_FILE.exists():
        raise HTTPException(404, "config/hardware_profile.json bulunamadi")
    return json.loads(shared.HARDWARE_FILE.read_text(encoding="utf-8"))


@router.put("/api/hardware", response_model=HardwareConfig)
def hardware_put(update: HardwareUpdate):
    """config/hardware_profile.json'u kismi gunceller (Sprint 6 Ayarlar sekmesi icin)."""
    if not shared.HARDWARE_FILE.exists():
        raise HTTPException(404, "config/hardware_profile.json bulunamadi")
    current = HardwareConfig(
        **json.loads(shared.HARDWARE_FILE.read_text(encoding="utf-8"))
    )
    if update.active_profile is not None:
        current.active_profile = update.active_profile
    if update.profiles is not None:
        current.profiles = update.profiles
    if update.tier_thresholds is not None:
        current.tier_thresholds = update.tier_thresholds
    shared.HARDWARE_FILE.write_text(
        json.dumps(current.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return current


@router.post("/api/hardware/autodetect")
def hardware_autodetect():
    """llmfit system'den gercek donanim bilgisini cekip aktif profile yazar.

    Sprint 7 onerisi 1: 'llmfit system bilgisini kullanip Ayarlar'daki donanim
    profilini otomatik senkronize et'.
    """
    try:
        sys_data = shared.benchcompass_proxy.llmfit_system(use_cache=False)
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)

    if not shared.HARDWARE_FILE.exists():
        raise HTTPException(404, "config/hardware_profile.json bulunamadi")

    current = HardwareConfig(
        **json.loads(shared.HARDWARE_FILE.read_text(encoding="utf-8"))
    )
    detected = shared.benchcompass_proxy.normalize_system_info(sys_data)

    # Aktif profili guncelle
    profile_id = current.active_profile
    idx = next((i for i, p in enumerate(current.profiles) if p.id == profile_id), 0)
    profile = current.profiles[idx]
    updated_profile = profile.model_copy(
        update={
            "device_name": detected["device_name"] or profile.device_name,
            "cpu": detected["cpu"] or profile.cpu,
            "gpu": detected["gpu"] or profile.gpu,
            "vram_gb": detected["vram_gb"]
            if detected["vram_gb"] > 0
            else profile.vram_gb,
            "ram_gb": detected["ram_gb"] if detected["ram_gb"] > 0 else profile.ram_gb,
            "os": detected["os"] or profile.os,
        }
    )
    current.profiles[idx] = updated_profile

    shared.HARDWARE_FILE.write_text(
        json.dumps(current.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "detected": detected,
        "profile": updated_profile.model_dump(),
    }


@router.post("/api/migrate", response_model=MigrateResult)
def migrate(force_backfill: bool = True):
    """Eksik sutunlari ALTER TABLE ile ekler (zaten varsa atlar) ve
    notes'tan backfill yapar."""
    con = dbmod.connect()  # connect() migrate() cagirir zaten
    try:
        added: list[
            str
        ] = []  # connect() zaten migrate yapti; burada ekstra bir sey kalmadi
        backfilled = 0
        if force_backfill:
            backfilled = dbmod.backfill_from_notes(con)
        return MigrateResult(ok=True, added_columns=added, backfilled_rows=backfilled)
    finally:
        con.close()


# --- Provider yapilandirmasi ---


@router.get("/api/provider")
def provider_get():
    """Aktif LLM saglayici yapilandirmasi."""
    return shared._get_provider_config()


@router.put("/api/provider")
def provider_put(cfg: dict):
    """Saglayici yapilandirmasini gunceller."""
    current = shared._get_provider_config()
    current.update(cfg)
    if "active_provider" in cfg:
        current["provider"] = cfg["active_provider"]
    shared._save_provider_config(current)
    return {"ok": True, "provider": current, "config": current}


@router.get("/api/provider/runtimes")
def provider_runtimes():
    """Desteklenen tum yerel LLM calisma zamanlarini listeler."""
    return {
        "ok": True,
        "runtimes": [
            {
                "id": "ollama",
                "name": "Ollama",
                "description": "Otomatik GPU offloading & REST API",
                "default_port": 11434,
            },
            {
                "id": "lmstudio",
                "name": "LM Studio",
                "description": "Yerel OpenAI-uyumlu sunucu",
                "default_port": 1234,
            },
            {
                "id": "llamacpp",
                "name": "llama.cpp",
                "description": "Yuksek performansli C++ inference motoru",
                "default_port": 8080,
            },
            {
                "id": "mlx",
                "name": "MLX (Apple Silicon)",
                "description": "macOS Apple Silicon optimize inference motoru",
                "default_port": 8080,
            },
        ],
    }


@router.get("/api/compat/simulate")
def compat_simulate(
    param_count_b: float = 8.0,
    quant: str = "Q4_K_M",
    context_length: int = 4096,
    vram_gb: float | None = None,
    ram_gb: float | None = None,
    gpu_count: int = 1,
    interconnect: str = "single",
):
    """Model indirilmeden önce donanım sığma ve hız bütçe simülasyonunu döner.

    Adım 5: `gpu_count` + `interconnect` (config/interconnect.json) çoklu GPU
    toplam VRAM'i ve etkin bant darlığını simüle eder.
    """
    from ..compat import simulate_hardware_fit

    return simulate_hardware_fit(
        param_count_b=param_count_b,
        quant=quant,
        context_length=context_length,
        user_vram_gb=vram_gb,
        user_ram_gb=ram_gb,
        gpu_count=gpu_count,
        interconnect=interconnect,
    )
