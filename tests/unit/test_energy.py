"""Unit testler: api/energy.py — Sprint 45 & P1-6 enerji/maliyet/CO2 hesap servisi.

Saf fonksiyonlar; dosya/network yok. Matematik bilinen değerlerle doğrulanır.
"""

from __future__ import annotations

import json

from api.energy import (
    DEFAULT_PRICING,
    estimate_energy,
    load_pricing,
    monthly_co2_grams,
)


class TestLoadPricing:
    def test_dosya_yoksa_default(self, tmp_path):
        p = load_pricing(tmp_path / "yok.json")
        assert p == DEFAULT_PRICING

    def test_kismi_dosya_uzerine_yazar(self, tmp_path):
        cfg = tmp_path / "energy_pricing.json"
        cfg.write_text(json.dumps({"electricity_try_per_kwh": 5.0}), encoding="utf-8")
        p = load_pricing(cfg)
        assert p["electricity_try_per_kwh"] == 5.0
        assert p["usd_try"] == DEFAULT_PRICING["usd_try"]  # kalanı default

    def test_bozuk_json_graceful(self, tmp_path):
        cfg = tmp_path / "energy_pricing.json"
        cfg.write_text("{bozuk", encoding="utf-8")
        assert load_pricing(cfg) == DEFAULT_PRICING

    def test_string_degerler_yutulmaz(self, tmp_path):
        """Sayı olmayan alanlar varsayılanı bozmaz (tip güvenliği)."""
        cfg = tmp_path / "energy_pricing.json"
        cfg.write_text(json.dumps({"usd_try": "kırk iki"}), encoding="utf-8")
        p = load_pricing(cfg)
        assert p["usd_try"] == DEFAULT_PRICING["usd_try"]

    def test_bool_deger_sayi_sayilmaz(self, tmp_path):
        """Sprint 52 (K5): true → 1.0 tuzağı — bool reddedilir."""
        cfg = tmp_path / "energy_pricing.json"
        cfg.write_text(
            json.dumps({"usd_try": True, "electricity_try_per_kwh": False}),
            encoding="utf-8",
        )
        p = load_pricing(cfg)
        assert p["usd_try"] == DEFAULT_PRICING["usd_try"]
        assert (
            p["electricity_try_per_kwh"] == DEFAULT_PRICING["electricity_try_per_kwh"]
        )


class TestEstimateEnergy:
    def test_matematik_bilinen_degerlerle(self):
        # 10 t/s, 100 W, 2 h/gün: 0.1 kWh/h × 2 × 30 = 6 kWh/ay
        # tokens: 10 × 3600 × 2 × 30 = 2.16M → bulut 2.16 × 0.38 = 0.8208 $ → 34.47 ₺
        pricing = {
            "electricity_try_per_kwh": 2.5,
            "daily_usage_hours": 2.0,
            "cloud_blended_usd_per_mtok": 0.38,
            "usd_try": 42.0,
        }
        r = estimate_energy(10.0, 100.0, pricing)
        assert r["tok_per_joule"] == 0.1  # 10 t/s / 100 W
        assert r["kwh_month"] == 6.0
        assert r["tokens_month_m"] == 2.16
        assert r["cost_try_month"] == 15.0  # 6 × 2.5
        assert r["cloud_cost_try_month"] == 34.47  # 2.16 × 0.38 × 42 = 34.4736
        assert r["local_vs_cloud_ratio"] == round(15.0 / 34.4736, 3)

    def test_tok_per_joule_verimlilik_siralamasi(self):
        """Aynı watt'ta yüksek t/s → yüksek tok/J (verimlilik yönü doğru)."""
        pricing = dict(DEFAULT_PRICING)
        fast = estimate_energy(40.0, 100.0, pricing)
        slow = estimate_energy(10.0, 100.0, pricing)
        assert fast["tok_per_joule"] > slow["tok_per_joule"]

    def test_sifir_watt_none_verimlilik(self):
        r = estimate_energy(10.0, 0.0, dict(DEFAULT_PRICING))
        assert r["tok_per_joule"] is None
        assert r["local_vs_cloud_ratio"] == 0.0  # 0 maliyet → yerel bedava

    def test_bulut_sifir_fiyat_ratio_none(self):
        pricing = dict(DEFAULT_PRICING)
        pricing["cloud_blended_usd_per_mtok"] = 0.0
        r = estimate_energy(10.0, 100.0, pricing)
        assert r["local_vs_cloud_ratio"] is None


class TestCO2Emissions:
    def test_monthly_co2_basic(self):
        # 120 W, 2 h/gün, 450 g/kWh
        # kwh_month = 0.12 * 2 * 30 = 7.2 kWh
        # co2_g = 7.2 * 450 = 3240.0 g
        res = monthly_co2_grams(power_w=120.0, daily_hours=2.0, grid_co2_g_kwh=450.0)
        assert res == 3240.0
        assert isinstance(res, float)

    def test_estimate_energy_includes_co2(self):
        pricing = dict(DEFAULT_PRICING)
        r = estimate_energy(tps=45.0, power_w=120.0, pricing=pricing)
        assert "co2_monthly_g" in r
        assert "co2_car_km_equiv" in r
        assert "grid_co2_g_per_kwh" in r
        assert r["co2_monthly_g"] == 3240.0
        # 3240.0 / 120.0 = 27.0 km
        assert r["co2_car_km_equiv"] == 27.0
