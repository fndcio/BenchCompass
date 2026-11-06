"""Enerji ve maliyet hesap servisi (Sprint 45 & P1-6).

Yerel modelin gerçek maliyetini sayısallaştırır: tok/Joule verimliliği,
aylık elektrik tüketimi/ücreti, CO2 emisyonu ve eşdeğer bulut API maliyeti. Fiyatlar
``config/energy_pricing.json``'dan okunur (kullanıcı düzenlenebilir);
dosya yoksa makul varsayılanlarla ayağa kalkar (graceful degradation).

Tüm fonksiyonlar SAF fonksiyonlardır — ağ/DB erişimi yoktur; endpoint
katmanı veriyi toplar, burada yalnızca hesap yapılır (test edilebilirlik).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PRICING: dict[str, Any] = {
    "electricity_try_per_kwh": 2.5,
    "daily_usage_hours": 2.0,
    "assumed_gpu_w": 120.0,
    "usd_try": 42.0,
    "cloud_blended_usd_per_mtok": 0.38,
    "grid_co2_g_per_kwh": 450.0,
}

DAYS_PER_MONTH = 30


def load_pricing(config_path: Path) -> dict[str, Any]:
    """config/energy_pricing.json'u okur; yoksa/bozuksa varsayılanlarla döner.

    Kısmi dosya desteklenir: mevcut alanlar varsayılanların üzerine yazılır.
    """
    pricing = dict(DEFAULT_PRICING)
    try:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key in pricing:
                # Sprint 52 (K5): bool sayı sayılmaz (True → 1.0 tuzağı)
                if (
                    key in raw
                    and isinstance(raw[key], (int, float))
                    and not isinstance(raw[key], bool)
                ):
                    pricing[key] = float(raw[key])
    except (OSError, json.JSONDecodeError):
        pass
    return pricing


def monthly_co2_grams(
    power_w: float,
    daily_hours: float,
    grid_co2_g_kwh: float,
) -> float:
    """Aylık CO2 üretimini gram cinsinden hesaplar (P1-6).

    kwh_month = power_w / 1000.0 * daily_hours * DAYS_PER_MONTH
    co2_g = kwh_month * grid_co2_g_kwh
    """
    kwh_month = power_w / 1000.0 * daily_hours * DAYS_PER_MONTH
    return round(kwh_month * grid_co2_g_kwh, 1)


def estimate_energy(
    tps: float, power_w: float, pricing: dict[str, Any]
) -> dict[str, Any]:
    """tok/s + anlık watt → enerji verimliliği ve aylık maliyet raporu.

    - tok/J: bir Joule başına üretilen token (ne kadar yüksek o kadar verimli).
    - Aylık tüketim: power_w × günlük kullanım × 30 gün.
    - CO2 salınımı: aylık kWh × şebeke emisyon katsayısı (g/kWh).
    - Bulut eşdeğeri: aynı aylık token üretiminin API maliyeti (₺).
    """
    hours = float(pricing["daily_usage_hours"])
    grid_co2 = float(pricing.get("grid_co2_g_per_kwh", 450.0))
    kwh_month = power_w / 1000.0 * hours * DAYS_PER_MONTH
    tokens_month = tps * 3600.0 * hours * DAYS_PER_MONTH
    tokens_month_m = tokens_month / 1_000_000.0
    cost_try_month = kwh_month * float(pricing["electricity_try_per_kwh"])
    cloud_usd = tokens_month_m * float(pricing["cloud_blended_usd_per_mtok"])
    cloud_try_month = cloud_usd * float(pricing["usd_try"])
    ratio = (cost_try_month / cloud_try_month) if cloud_try_month > 0 else None

    co2_g = monthly_co2_grams(power_w, hours, grid_co2)
    car_km = round(co2_g / 120.0, 1)  # 1 km araba sürüşü ~ 120 g CO2

    return {
        "tok_per_joule": round(tps / power_w, 2) if power_w > 0 else None,
        "kwh_month": round(kwh_month, 2),
        "tokens_month_m": round(tokens_month_m, 2),
        "cost_try_month": round(cost_try_month, 2),
        "cloud_cost_try_month": round(cloud_try_month, 2),
        # <1 → yerel daha ucuz; >1 → bulut daha ucuz
        "local_vs_cloud_ratio": round(ratio, 3) if ratio is not None else None,
        "daily_usage_hours": hours,
        "co2_monthly_g": co2_g,
        "co2_car_km_equiv": car_km,
        "grid_co2_g_per_kwh": grid_co2,
    }
