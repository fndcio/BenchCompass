"""api/routes/telemetry.py — Canlı GPU telemetri route'u (Sprint 44).

nvidia-smi'den tek atımlık okuma yapar; ``scripts/vram_sentinel.py``'nin
gözlem tarafını (sıcaklık/güç/VRAM) panele taşır. Sentinel'in karantina
işlevine DOKUNMAZ — widget yalnızca gözlemler, süreç yönetimi yapmaz.

Eşikler donanım VRAM'inden türetilir (tek kaynak ilkesi): warn=%92, crit=%96 —
``scripts/vram_sentinel.py`` sabitlerinin (12 GB'da 11.2/11.7 GB) oransal
karşılığı; donanım değişince eşikler otomatik uyum sağlar.
nvidia-smi yüklü değilse/hata verirse ``{available: false}`` döner (graceful
degradation — bench_data.py deseni); UI widget'ı kendini gizler.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import energy as energy_mod
from ..routes.shared import BASE

# Sprint 52 (K1): t/s tek kaynak — matrix.measured_tps_map (yalnız source='real';
# benchkit suite ortalaması serving ölçümüyle karışmaz). Liste ve detay endpoint'i
# aynı id-bazlı sıralamayı paylaşır.
from .matrix import measured_tps_map

# P1-6 (2026-11-05): NVML hassas örnekleme — pynvml OPSİYONEL ekstra
# (`pip install .[nvml]`); kuruluysa NVML yolu, değilse nvidia-smi fallback.
# Local-First korunur: zorunlu bağımlılık YOK.
try:
    import pynvml as _pynvml  # type: ignore[import-not-found]

    _NVML: Any = _pynvml
except ImportError:
    _NVML = None

router = APIRouter()

ENERGY_PRICING_FILE = BASE / "config" / "energy_pricing.json"

# Alan seti vram_sentinel.get_gpu_metrics ile aynı (MB / °C / W / %).
_NVIDIA_SMI_ARGS = [
    "nvidia-smi",
    "--query-gpu=memory.total,memory.used,memory.free,"
    "temperature.gpu,power.draw,utilization.gpu",
    "--format=csv,noheader,nounits",
]
_SMI_TIMEOUT_SEC = 2
WARN_PCT = 0.92
CRIT_PCT = 0.96
TEMP_WARN_C = 75
TEMP_CRIT_C = 82


def _threshold_payload() -> dict[str, Any]:
    """Telemetri eşik alanları — frontend'in tek kaynağı backend'dir (Y17/DRY).

    Frontend (``web/modules/gpu-telemetry.js``) bu değerleri kullanır; yalnızca
    alan eksikse kendi fallback sabitine düşer. VRAM eşikleri vram_sentinel
    sabitlerinin oransal karşılığıdır; sıcaklık eşikleri burada tek tanımlıdır.
    """
    return {
        "warn_pct": round(WARN_PCT * 100),
        "crit_pct": round(CRIT_PCT * 100),
        "temp_warn_c": TEMP_WARN_C,
        "temp_crit_c": TEMP_CRIT_C,
    }


def _num_or_none(raw: str) -> float | None:
    """csv hücresini sayıya çevirir; 'N/A'/boş/dönüştürülemez ise None."""
    if raw in ("N/A", "[N/A]", "", "-"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_nvidia_smi_line(line: str) -> dict[str, Any] | None:
    """nvidia-smi csv satırını metrik dict'e çevirir; bozuksa None.

    Alan sırası: memory.total, memory.used, memory.free, temperature.gpu,
    power.draw, utilization.gpu. Virgülden az alan veya tamamen sayısız
    satır None döndürür (caller available=false yoluna gider).
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 6:
        return None
    vram_total = _num_or_none(parts[0])
    vram_used = _num_or_none(parts[1])
    vram_free = _num_or_none(parts[2])
    temp = _num_or_none(parts[3])
    power = _num_or_none(parts[4])
    util = _num_or_none(parts[5])
    if vram_total is None and vram_used is None and temp is None:
        return None
    return {
        "vram_total_mb": int(vram_total) if vram_total is not None else None,
        "vram_used_mb": int(vram_used) if vram_used is not None else None,
        "vram_free_mb": int(vram_free) if vram_free is not None else None,
        "temp_c": temp,
        "power_w": power,
        "util_pct": util,
    }


def _level_for(used_mb: float | None, total_mb: float | None) -> str:
    """VRAM doluluğuna göre ok/warn/crit seviyesi (sentinel oranı türetilmiş)."""
    if used_mb is None or not total_mb:
        return "ok"
    if used_mb >= total_mb * CRIT_PCT:
        return "crit"
    if used_mb >= total_mb * WARN_PCT:
        return "warn"
    return "ok"


def _nvml_metrics() -> dict[str, Any] | None:
    """pynvml ile GPU metrikleri; pynvml yoksa/hata verirse None (fallback).

    NVML bayt cinsinden döner → MB'a çevrilir (nvidia-smi csv alanlarıyla aynı
    şema: vram_total_mb/vram_used_mb/vram_free_mb/temp_c/power_w/util_pct).
    """
    if _NVML is None:
        return None
    try:
        _NVML.nvmlInit()
        handle = _NVML.nvmlDeviceGetHandleByIndex(0)
        mem = _NVML.nvmlDeviceGetMemoryInfo(handle)
        util = _NVML.nvmlDeviceGetUtilizationRates(handle)
        temp = _NVML.nvmlDeviceGetTemperature(handle, _NVML.NVML_TEMPERATURE_GPU)
        power_mw = _NVML.nvmlDeviceGetPowerUsage(handle)
        _NVML.nvmlShutdown()
        total_mb = int(mem.total / (1024 * 1024))
        used_mb = int(mem.used / (1024 * 1024))
        return {
            "vram_total_mb": total_mb,
            "vram_used_mb": used_mb,
            "vram_free_mb": total_mb - used_mb,
            "temp_c": float(temp),
            "power_w": round(power_mw / 1000.0, 1),
            "util_pct": float(util.gpu),
        }
    except Exception:  # noqa: BLE001 — NVML her hatada nvidia-smi yoluna düşer
        return None


# --- NPU telemetrisi (Sprint 51) ---------------------------------------------
# AMD Ryzen AI XDNA cihazı Windows PnP katmanında "ComputeAccelerator" sınıfında
# görünür ("NPU Compute Accelerator Device"). Bu makinede standart bir PDH
# kullanım sayacı yok ("No valid counters") — utilization dürüstçe null kalır,
# cihaz varlığı raporlanır. Sayaç bulunursa alan doldurulur.

_PS_NPU_CMD = [
    "powershell",
    "-NoProfile",
    "-Command",
    "Get-PnpDevice -Class ComputeAccelerator -Status OK "
    "| Select-Object -ExpandProperty FriendlyName",
]
_PS_TIMEOUT_SEC = 8


def parse_npu_devices(stdout: str) -> list[str]:
    """PowerShell FriendlyName çıktısını cihaz listesine çevirir (saf fonksiyon)."""
    return [ln.strip() for ln in stdout.splitlines() if ln.strip()]


@router.get("/api/telemetry/npu")
def npu_telemetry() -> dict[str, Any]:
    """NPU cihaz varlığı; sayaç yoksa utilization=null ile dürüst rapor."""
    ts = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            _PS_NPU_CMD,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PS_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "available": False,
            "error": "powershell yok veya timeout",
            "utilization_pct": None,
            "ts": ts,
        }
    if proc.returncode != 0:
        return {
            "available": False,
            "error": f"powershell exit={proc.returncode}",
            "utilization_pct": None,
            "ts": ts,
        }
    devices = parse_npu_devices(proc.stdout)
    if not devices:
        return {
            "available": False,
            "devices": [],
            "utilization_pct": None,
            "ts": ts,
        }
    return {
        "available": True,
        "devices": devices,
        # Windows PDH'de yaygın NPU kullanım sayacı yok — bulunursa doldurulacak
        "utilization_pct": None,
        "note": "Cihaz mevcut; standart Windows kullanım sayacı bulunamadı (dürüst boşluk).",
        "ts": ts,
    }


@router.get("/api/telemetry/gpu")
def gpu_telemetry() -> dict[str, Any]:
    """Anlık GPU metrikleri; pynvml varsa NVML yolu, yoksa nvidia-smi fallback.

    Yanıta `source` alanı eklenir: 'nvml' | 'nvidia-smi' — hangi örnekleme
    yolunun döndüğü dürüstçe raporlanır (Y24 ruhu).
    """
    ts = datetime.now(timezone.utc).isoformat()

    # P1-6: NVML yolu önce denenir (opsiyonel pynvml extra)
    nvml = _nvml_metrics()
    if nvml is not None:
        used = nvml["vram_used_mb"]
        total = nvml["vram_total_mb"]
        used_pct = round(used / total * 100, 1) if used is not None and total else None
        return {
            "available": True,
            "source": "nvml",
            **nvml,
            "used_pct": used_pct,
            "level": _level_for(used, total),
            **_threshold_payload(),
            "ts": ts,
        }

    try:
        proc = subprocess.run(
            _NVIDIA_SMI_ARGS,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_SMI_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "error": "nvidia-smi yok veya timeout", "ts": ts}
    if proc.returncode != 0:
        return {
            "available": False,
            "error": f"nvidia-smi exit={proc.returncode}",
            "ts": ts,
        }
    first_line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    metrics = parse_nvidia_smi_line(first_line)
    if metrics is None:
        return {
            "available": False,
            "error": "nvidia-smi çıktısı çözümlenemedi",
            "ts": ts,
        }
    used = metrics["vram_used_mb"]
    total = metrics["vram_total_mb"]
    used_pct = round(used / total * 100, 1) if used is not None and total else None
    return {
        "available": True,
        "source": "nvidia-smi",
        **metrics,
        "used_pct": used_pct,
        "level": _level_for(used, total),
        **_threshold_payload(),
        "ts": ts,
    }


# Sprint 52 (K8): anlık watt ancak GPU gerçekten yük altındaysa "live" sayılır —
# idle gücüyle hesap yanlış iyimser tok/J üretir.
_LIVE_POWER_MIN_UTIL_PCT = 20.0


def _latest_measured_tps(model_name: str) -> float | None:
    """Modelin en yeni gerçek (source='real') ölçüm t/s — tek kaynak üzerinden."""
    entry = measured_tps_map().get(model_name)
    return entry["tps"] if entry else None


@router.get("/api/telemetry/energy")
def energy_models() -> dict[str, Any]:
    """Enerji hesabı yapılabilir modeller (gerçek ölçüm t/s'i olanlar)."""
    tps_map = measured_tps_map()
    models = [
        {"model": m, "measured_tps": v["tps"], "last_at": v["last_at"]}
        for m, v in tps_map.items()
    ]
    models.sort(key=lambda r: r["last_at"] or "", reverse=True)
    return {"models": models[:100]}


@router.get("/api/telemetry/energy/{model_name}")
def energy_estimate(model_name: str) -> dict[str, Any]:
    """Modelin enerji/maliyet raporu: tok/J + aylık ₺ + bulut karşılaştırması.

    tps benchmarks tablosundan (yalnız gerçek serving ölçümü), watt canlı
    telemetriden gelir — ama yalnızca GPU yük altındaysa (util ≥ %20); aksi
    halde idle gücü yanıltıcı iyimserlik üretir ve config'teki varsayılan yük
    watt'ı ``"assumed"`` etiketiyle kullanılır.
    """
    tps = _latest_measured_tps(model_name)
    if tps is None:
        raise HTTPException(
            404,
            f"'{model_name}' için ölçülmüş benchmark yok — önce benchmark çalıştırın",
        )
    live = gpu_telemetry()
    util = live.get("util_pct") if live.get("available") else None
    if (
        live.get("available")
        and live.get("power_w")
        and (util is not None and float(util) >= _LIVE_POWER_MIN_UTIL_PCT)
    ):
        power_w = float(live["power_w"])
        power_source = "live"
    else:
        pricing = energy_mod.load_pricing(ENERGY_PRICING_FILE)
        power_w = float(pricing["assumed_gpu_w"])
        power_source = "assumed"
    pricing = energy_mod.load_pricing(ENERGY_PRICING_FILE)
    est = energy_mod.estimate_energy(tps, power_w, pricing)
    return {
        "model": model_name,
        "measured_tps": tps,
        "power_w": power_w,
        "power_source": power_source,
        **est,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
