"""Sayisal uyumluluk motoru — Master Prompt Bolum 2.2'nin birebir kod hali.

Kritik tasarim karari: Tier DB'ye YAZILMAZ. Her render'da (backend tarafinda
compute_tier, frontend tarafinda ayni formul) donanim profili ile yeniden
hesaplanir. Bu sayede kullanici Ayarlar'dan donanimini degistirirse gecmis
snapshot'lardaki modeller de guncel tier ile gosterilir.

Formul (Bolum 2.2):
    vram_margin = hardware.vram_gb - model.required_vram_gb
    ram_margin  = hardware.ram_gb  - model.required_ram_gb

    vram_margin >= 2 AND ram_margin >= 4   -> "Tam Uyumlu"        (good)
    vram_margin >= 0 AND ram_margin >= 0   -> "Uyumlu (Sinirda)"  (warn)
    vram_margin >= -1.5                    -> "Dikkatli Kullan"   (orange)
    else                                    -> "Uygun Degil"      (bad)

    context_flag (ayri):
    model.context_length_estimated_at < model.context_length_supported
        -> "Context kisitli tahmin edildi (gercek limit: {supported})"
"""

from __future__ import annotations

from typing import Any

from .schemas import HardwareProfileEntry, ModelRecord, TierResult, TierThresholds


def _tier_from_notes(
    loaded_into_vram: bool, insufficient_note: bool
) -> tuple[str, str]:
    """Sayısal veri yokken not ipuçlarına göre (tier, tone) döndürür."""
    if loaded_into_vram and not insufficient_note:
        return "Tam Uyumlu", "good"
    if insufficient_note:
        return "Dikkatli Kullan", "orange"
    # Hic veri yok — tarafsiz, kullanicinin dikkatini cek
    return "Uyumlu (Sinirda)", "warn"


def _tier_from_margins(
    vram_margin: float,
    ram_margin: float,
    run_mode: str,
    thresholds: TierThresholds,
) -> tuple[str, str]:
    """VRAM/RAM marjlerine ve run_mode'a göre (tier, tone) döndürür.

    Sprint 12: run_mode hesaba kat. run_mode yoksa eski katı mantık.
    """
    mode_lower = run_mode.lower()
    # CPU modunda: VRAM onemsiz, RAM'e bak
    if mode_lower in ("cpu", "cpu_only"):
        if ram_margin >= thresholds.ram_full_margin:
            return "Tam Uyumlu", "good"
        if ram_margin >= 0:
            return "Uyumlu (Sinirda)", "warn"
        if ram_margin >= thresholds.vram_caution_margin:
            return "Dikkatli Kullan", "orange"
        return "Uygun Degil", "bad"
    # CPU offload: VRAM esnek (12GB eksik bile calisabilir, 30B Q4)
    if "cpu_offload" in mode_lower or "mixed" in mode_lower:
        if vram_margin >= (thresholds.vram_full_margin - 2.0) and ram_margin >= 0:
            return "Tam Uyumlu", "good"
        if vram_margin >= -6.0 and ram_margin >= 0:
            return "Uyumlu (Sinirda)", "warn"
        if vram_margin >= -12.0:
            return "Dikkatli Kullan", "orange"
        return "Uygun Degil", "bad"
    # GPU mode veya run_mode yok: mevcut katı mantık
    if (
        vram_margin >= thresholds.vram_full_margin
        and ram_margin >= thresholds.ram_full_margin
    ):
        return "Tam Uyumlu", "good"
    if vram_margin >= 0 and ram_margin >= 0:
        return "Uyumlu (Sinirda)", "warn"
    if vram_margin >= thresholds.vram_caution_margin:
        return "Dikkatli Kullan", "orange"
    return "Uygun Degil", "bad"


def compute_tier(
    model: ModelRecord,
    hardware: HardwareProfileEntry,
    thresholds: TierThresholds | None = None,
) -> TierResult:
    """Bir model icin tier + tooltip hesaplar.

    Eksik veri (required_vram_gb = None) durumlari guvenli sekilde ele alinir:
    - Eger 'GPU: model loaded into VRAM' notu varsa (model.loaded_into_vram)
      ve required_vram_gb yoksa, model donanim uzerinde zaten calisiyor demek;
      "Tam Uyumlu" varsayilir.
    - Eger 'Insufficient VRAM' notu varsa ve sayisal deger yoksa, kenar
      durumda "Dikkatli Kullan" verilir (guvenli taraf).
    - Tamamen veri yoksa "Sinirda" -> neutral, tooltip aciklamasiyla.
    """
    if thresholds is None:
        thresholds = TierThresholds()

    required_vram = model.required_vram_gb
    required_ram = model.required_ram_gb

    # Not bazli ipuclari (model notes'tan parse edilen boolean'lar)
    loaded_into_vram = bool(getattr(model, "loaded_into_vram", False))
    insufficient_note = bool(getattr(model, "insufficient", False))

    if required_vram is None and required_ram is None:
        # Sayisal veri yok — not ipuclarina guven
        tier, tone = _tier_from_notes(loaded_into_vram, insufficient_note)
        vram_margin = None
        ram_margin = None
    else:
        vram_margin = hardware.vram_gb - (required_vram or 0)
        ram_margin = hardware.ram_gb - (required_ram or 0)
        run_mode = getattr(model, "run_mode", None) or ""
        tier, tone = _tier_from_margins(vram_margin, ram_margin, run_mode, thresholds)

    context_flag = compute_context_flag(model)
    tooltip = build_tooltip(
        tier=tier,
        model=model,
        hardware=hardware,
        vram_margin=vram_margin,
        ram_margin=ram_margin,
        context_flag=context_flag,
    )

    vram_str = f"{vram_margin:+.1f} GB" if vram_margin is not None else "bilinmiyor"
    ram_str = f"{ram_margin:+.1f} GB" if ram_margin is not None else "bilinmiyor"
    req_vram = model.required_vram_gb if model.required_vram_gb is not None else 0.0
    explanation = (
        f"VRAM marjı: {vram_str} "
        f"(donanım: {hardware.vram_gb:.1f} GB, model gereksinimi: {req_vram:.1f} GB), "
        f"RAM marjı: {ram_str}"
    )
    inputs = {
        "vram_gb": hardware.vram_gb,
        "required_vram_gb": model.required_vram_gb,
        "ram_gb": hardware.ram_gb,
        "required_ram_gb": model.required_ram_gb,
        "run_mode": getattr(model, "run_mode", "") or "",
    }
    verify_cmd = f"llmfit check {model.name}"

    return TierResult(
        tier=tier,
        tone=tone,
        vram_margin_gb=vram_margin,
        ram_margin_gb=ram_margin,
        context_flag=context_flag,
        tooltip=tooltip,
        explanation=explanation,
        inputs=inputs,
        verify_cmd=verify_cmd,
    )


def compute_context_flag(model: ModelRecord) -> str | None:
    """Context kisitli mi? Bolum 2.2'deki context_flag kurali."""
    est = model.context_length_estimated_at
    sup = model.context_length_supported
    if est is not None and sup is not None and est < sup:
        return f"Context kisitli tahmin edildi (gercek limit: {sup})"
    return None


def build_tooltip(
    tier: str,
    model: ModelRecord,
    hardware: HardwareProfileEntry,
    vram_margin: float | None,
    ram_margin: float | None,
    context_flag: str | None,
) -> str:
    """Bolum 2.3'teki tooltip formatini uretir.

    Ornek cikti:
        Gerekli VRAM: 7.6 GB | Senin: 12 GB | Bosluk: +4.4 GB
        Gerekli RAM: 8.3 GB | Senin: 32 GB | Bosluk: +23.7 GB
        Context: 8192 ile tahmin edildi (model gercekte 32768 destekliyor)
    """
    lines = [f"Tier: {tier}"]

    if model.required_vram_gb is not None:
        lines.append(
            f"Gerekli VRAM: {model.required_vram_gb:g} GB | "
            f"Senin: {hardware.vram_gb:g} GB | "
            f"Bosluk: {('+' if (vram_margin or 0) >= 0 else '')}{vram_margin:.1f} GB"
        )
    else:
        lines.append(f"Senin VRAM: {hardware.vram_gb:g} GB (gerekli deger bilinmiyor)")

    if model.required_ram_gb is not None:
        lines.append(
            f"Gerekli RAM: {model.required_ram_gb:g} GB | "
            f"Senin: {hardware.ram_gb:g} GB | "
            f"Bosluk: {('+' if (ram_margin or 0) >= 0 else '')}{ram_margin:.1f} GB"
        )
    else:
        lines.append(f"Senin RAM: {hardware.ram_gb:g} GB (gerekli deger bilinmiyor)")

    est = model.context_length_estimated_at
    sup = model.context_length_supported
    if est is not None and sup is not None and est < sup:
        lines.append(
            f"Context: {est} ile tahmin edildi (model gercekte {sup} destekliyor)"
        )
    elif sup is not None:
        lines.append(f"Context: {sup} destekliyor")
    elif est is not None:
        lines.append(f"Context: {est} ile tahmin edildi")

    if context_flag:
        lines.append(context_flag)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Donanım Uyumluluk Simülatörü (ADR-0012, Sprint 53 / Ortakheyet Konsensüsü)
# ---------------------------------------------------------------------------

QUANT_BITS_MAP: dict[str, float] = {
    "FP16": 16.0,
    "BF16": 16.0,
    "Q8_0": 8.5,
    "Q6_K": 6.6,
    "Q5_K_M": 5.5,
    "Q5_K_S": 5.2,
    "Q4_K_M": 4.5,
    "Q4_K_XL": 4.6,
    "Q4_0": 4.2,
    "NVFP4": 4.0,
    "Q3_K_M": 3.4,
    "Q3_K_S": 3.2,
    "IQ2_M": 2.6,
    "IQ2_XXS": 2.2,
    "PTQ1_0": 1.6,
}


def load_interconnect_config() -> dict[str, Any]:
    """config/interconnect.json okur; yoksa varsayılan tek-GPU bandı döner."""
    import json as _json
    from pathlib import Path as _Path

    path = _Path(__file__).resolve().parent.parent / "config" / "interconnect.json"
    if not path.is_file():
        return {
            "default": "single",
            "interconnects": {"single": {"bandwidth_gb_s": 450.0}},
            "multi_gpu_overhead_pct": 12.0,
        }
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "default": "single",
            "interconnects": {"single": {"bandwidth_gb_s": 450.0}},
            "multi_gpu_overhead_pct": 12.0,
        }


def effective_bandwidth_gb_s(interconnect: str, gpu_count: int) -> float:
    """Çoklu GPU etkin bant genişliği (GB/s). Tek GPU → 450 (eski sabit)."""
    if gpu_count <= 1:
        return 450.0
    cfg = load_interconnect_config()
    table = cfg.get("interconnects") or {}
    entry = table.get(interconnect) or table.get("single") or {"bandwidth_gb_s": 450.0}
    link_bw = float(entry.get("bandwidth_gb_s", 450.0))
    # Çoklu GPU: toplam kapasite 450*gpu_count, ama hâl devri interconnect ile sınırlı.
    # Etkin bant = min(tek-GPU bandı * gpu_count, link_bw * (gpu_count-1) + tek-GPU?)
    # Sadeleştirme (ADR-0016): etkin = min(450*gpu_count, link_bw*gpu_count) - %12 overhead
    # PCIe/Ethernet darboğazında hız link ile sınırlanır.
    total = min(
        450.0 * gpu_count, link_bw * gpu_count if link_bw < 450 else 450.0 * gpu_count
    )
    overhead = float(cfg.get("multi_gpu_overhead_pct", 12.0))
    return round(total * (1.0 - overhead / 100.0), 1)


def simulate_hardware_fit(
    param_count_b: float,
    quant: str = "Q4_K_M",
    context_length: int = 4096,
    user_vram_gb: float | None = None,
    user_ram_gb: float | None = None,
    gpu_count: int = 1,
    interconnect: str = "single",
) -> dict[str, Any]:
    """Bir model indirilmeden önce donanım sığma ve hız bütçe simülasyonu yapar."""
    if user_vram_gb is None:
        from .system_info import detect_gpu_vram

        detected = detect_gpu_vram()
        user_vram_gb = float(detected.get("vram_total_gb", 12.0))

    if user_ram_gb is None:
        user_ram_gb = 32.0

    quant_norm = quant.upper().replace("-", "_")
    bits = QUANT_BITS_MAP.get(quant_norm, 4.5)

    # 1. Model Ağırlık Boyutu (GB)
    weights_gb = round((param_count_b * 1e9 * (bits / 8.0)) / (1024**3), 2)

    # 2. KV Cache Boyutu (GB) — 7B model 4K'da ~0.5 GB
    kv_cache_gb = round(
        max(0.1, (param_count_b / 7.0) * (context_length / 4096.0) * 0.45), 2
    )

    # 3. CUDA/Compute Buffer & Runtime Overhead (GB)
    overhead_gb = 0.85

    # 4. Toplam VRAM Bütçesi
    total_required_vram_gb = round(weights_gb + kv_cache_gb + overhead_gb, 2)
    vram_margin = round(user_vram_gb - total_required_vram_gb, 2)

    # 5. Offload Oranı & Çalışma Modu (Adım 5: interconnect bant farkında)
    bandwidth = effective_bandwidth_gb_s(interconnect, gpu_count)
    total_vram = user_vram_gb * max(1, gpu_count)
    vram_margin = round(total_vram - total_required_vram_gb, 2)

    # 5. Offload Oranı & Çalışma Modu
    if vram_margin >= 0:
        offload_pct = 100.0
        run_mode = "GPU"
        # Tahmini hız: etkin bant (tek GPU'da 450 — eski sabit ile aynı)
        estimated_speed_tps = round(min(125.0, bandwidth / max(1.0, weights_gb)), 1)
        fit_status = "TAM_UYUMLU"
        tone = "good"
    elif total_required_vram_gb <= (total_vram + user_ram_gb * 0.7):
        # Kısmi GPU + Sistem RAM'i (CPU Offload)
        gpu_fraction = max(
            0.2, (total_vram - overhead_gb - kv_cache_gb) / max(1.0, weights_gb)
        )
        offload_pct = round(min(95.0, gpu_fraction * 100.0), 1)
        run_mode = "CPU_OFFLOAD"
        # Hibrit hız cezası (etkin bantla)
        estimated_speed_tps = round(
            max(3.5, (bandwidth / max(1.0, weights_gb)) * (offload_pct / 100.0) * 0.35),
            1,
        )
        fit_status = "DIKKATLI_KULLAN"
        tone = "orange"
    else:
        offload_pct = 0.0
        run_mode = "CPU_ONLY"
        estimated_speed_tps = round(max(1.5, 60.0 / max(1.0, weights_gb)), 1)
        fit_status = "UYGUN_DEGIL"
        tone = "bad"

    return {
        "param_count_b": param_count_b,
        "quantization": quant,
        "context_length": context_length,
        "hardware": {
            "vram_gb": user_vram_gb,
            "ram_gb": user_ram_gb,
            "gpu_count": max(1, gpu_count),
            "interconnect": interconnect,
        },
        "budget": {
            "weights_gb": weights_gb,
            "kv_cache_gb": kv_cache_gb,
            "overhead_gb": overhead_gb,
            "total_required_vram_gb": total_required_vram_gb,
            "vram_margin_gb": vram_margin,
        },
        "simulation": {
            "fit_status": fit_status,
            "tone": tone,
            "run_mode": run_mode,
            "gpu_offload_pct": offload_pct,
            "estimated_speed_tps": estimated_speed_tps,
            "effective_bandwidth_gb_s": bandwidth,
        },
    }
