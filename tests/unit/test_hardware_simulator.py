"""tests/unit/test_hardware_simulator.py — Donanım Simülatörü ve Bütçe Motoru Birim Testi."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.compat import simulate_hardware_fit
from api.main import app

client = TestClient(app)


def test_simulate_hardware_fit_small_model() -> None:
    # 8B Q4_K_M modeli 12 GB VRAM'e rahatça sığmalıdır
    res = simulate_hardware_fit(
        param_count_b=8.0,
        quant="Q4_K_M",
        context_length=4096,
        user_vram_gb=12.0,
        user_ram_gb=32.0,
    )
    assert res["simulation"]["fit_status"] == "TAM_UYUMLU"
    assert res["simulation"]["run_mode"] == "GPU"
    assert res["simulation"]["gpu_offload_pct"] == 100.0
    assert res["simulation"]["estimated_speed_tps"] > 30.0
    assert res["budget"]["weights_gb"] < 6.0


def test_simulate_hardware_fit_medium_model_offload() -> None:
    # 27B Q4_K_M (~14 GB) 12 GB VRAM'de CPU_OFFLOAD moduna geçmelidir
    res = simulate_hardware_fit(
        param_count_b=27.0,
        quant="Q4_K_M",
        context_length=4096,
        user_vram_gb=12.0,
        user_ram_gb=32.0,
    )
    assert res["simulation"]["fit_status"] == "DIKKATLI_KULLAN"
    assert res["simulation"]["run_mode"] == "CPU_OFFLOAD"
    assert 0.0 < res["simulation"]["gpu_offload_pct"] < 100.0


def test_simulate_hardware_fit_huge_model_cpu() -> None:
    # 70B FP16 (~130 GB) 12 GB VRAM + 32 GB RAM'e sığmaz
    res = simulate_hardware_fit(
        param_count_b=70.0,
        quant="FP16",
        context_length=4096,
        user_vram_gb=12.0,
        user_ram_gb=32.0,
    )
    assert res["simulation"]["fit_status"] == "UYGUN_DEGIL"
    assert res["simulation"]["run_mode"] == "CPU_ONLY"


def test_compat_simulate_http_endpoint() -> None:
    resp = client.get(
        "/api/compat/simulate",
        params={"param_count_b": 8.0, "quant": "Q4_K_M", "context_length": 4096},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "budget" in data
    assert "simulation" in data
    assert data["simulation"]["fit_status"] in (
        "TAM_UYUMLU",
        "DIKKATLI_KULLAN",
        "UYGUN_DEGIL",
    )


# ---------------------------------------------------------------------------
# Adım 5 — interconnect / çoklu GPU (ADR-0016)
# ---------------------------------------------------------------------------
def test_effective_bandwidth_geri_uyumlu() -> None:
    from api.compat import effective_bandwidth_gb_s

    assert effective_bandwidth_gb_s("single", 1) == 450.0
    assert effective_bandwidth_gb_s("nvlink", 2) == 792.0  # 900 %12 = 792
    assert effective_bandwidth_gb_s("pcie4", 2) == 56.3  # 64 %12 darlığı


def test_multi_gpu_kucuk_modeli_siga_bilir() -> None:
    """8B model tek 12GB'de sığıyor; çoklu GPU'da da sığmalı, bant artar."""
    single = simulate_hardware_fit(8.0, "Q4_K_M", 4096, 12.0, 32.0, 1, "single")
    multi = simulate_hardware_fit(8.0, "Q4_K_M", 4096, 12.0, 32.0, 2, "nvlink")
    assert (
        single["simulation"]["estimated_speed_tps"]
        <= multi["simulation"]["estimated_speed_tps"]
    )
    assert multi["simulation"]["effective_bandwidth_gb_s"] == 792.0
    assert multi["hardware"]["gpu_count"] == 2


def test_interconnect_darligi_hizi_dusurur() -> None:
    """Ethernet 2-GPU, NVLink 2-GPU'dan belirgin yavaş olmalı."""
    eth = simulate_hardware_fit(8.0, "Q4_K_M", 4096, 12.0, 32.0, 2, "ethernet")
    nv = simulate_hardware_fit(8.0, "Q4_K_M", 4096, 12.0, 32.0, 2, "nvlink")
    assert (
        eth["simulation"]["estimated_speed_tps"]
        < nv["simulation"]["estimated_speed_tps"]
    )


def test_compat_simulate_coklu_gpu_http() -> None:
    resp = client.get(
        "/api/compat/simulate",
        params={
            "param_count_b": 27.0,
            "quant": "Q4_K_M",
            "gpu_count": 2,
            "interconnect": "pcie4",
            "vram_gb": 12.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["hardware"]["gpu_count"] == 2
    assert "effective_bandwidth_gb_s" in data["simulation"]
