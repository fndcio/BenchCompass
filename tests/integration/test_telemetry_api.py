"""Integration testler: api/routes/telemetry.py — Sprint 44 GPU telemetri.

subprocess mock'lanır (gerçek nvidia-smi çalışmaz — AGENTS.md §6 dış
bağımlılık mock kuralı). Parser saf fonksiyon olarak doğrudan test edilir.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes.telemetry import _level_for, parse_nvidia_smi_line

client = TestClient(app)


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


# --- Parser (saf fonksiyon) --------------------------------------------------


def test_parse_normal_line():
    m = parse_nvidia_smi_line("12288, 8192, 4096, 45, 85.32, 30")
    assert m == {
        "vram_total_mb": 12288,
        "vram_used_mb": 8192,
        "vram_free_mb": 4096,
        "temp_c": 45.0,
        "power_w": 85.32,
        "util_pct": 30.0,
    }


def test_parse_na_power_becomes_none():
    """power.draw 'N/A' dönebilir (idle P-state) — alan None kalır."""
    m = parse_nvidia_smi_line("12288, 8192, 4096, 45, N/A, 0")
    assert m["power_w"] is None
    assert m["vram_used_mb"] == 8192


def test_parse_short_line_returns_none():
    assert parse_nvidia_smi_line("12288, 8192") is None


def test_parse_all_na_returns_none():
    assert parse_nvidia_smi_line("N/A, N/A, N/A, N/A, N/A, N/A") is None


# --- Eşik türetme (sentinel %92/%96 oranı) ------------------------------------


def test_level_thresholds():
    total = 12288  # 12 GB — sentinel'in donanımı
    assert _level_for(8192, total) == "ok"
    assert _level_for(int(total * 0.925), total) == "warn"
    assert _level_for(int(total * 0.965), total) == "crit"
    # Sentinel sabitleriyle uyum: 11.2 GB warn bandında, 11.7 GB crit
    assert _level_for(11468, total) == "warn"
    assert _level_for(11980, total) == "crit"


def test_level_missing_values_ok():
    assert _level_for(None, 12288) == "ok"
    assert _level_for(8192, None) == "ok"


def test_level_boundary_values():
    """Eşik sınır değerleri (denetim kapanışı): 91.9 ok / 92 warn / 95.9 warn / 96 crit."""
    total = 1000
    assert _level_for(919, total) == "ok"
    assert _level_for(920, total) == "warn"
    assert _level_for(959, total) == "warn"
    assert _level_for(960, total) == "crit"


# --- Eşik alanları (denetim kapanışı — tek kaynak backend, Y17) -----------------


def test_threshold_payload_fields():
    from api.routes.telemetry import _threshold_payload

    p = _threshold_payload()
    assert p["warn_pct"] == 92
    assert p["crit_pct"] == 96
    assert p["temp_warn_c"] == 75
    assert p["temp_crit_c"] == 82


def test_gpu_endpoint_includes_thresholds(monkeypatch):
    """Eşikler yanıtta döner — frontend kendi sabitinden değil backend'den beslenir."""
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="12288, 8192, 4096, 45, 85.5, 30"),
    )
    d = client.get("/api/telemetry/gpu").json()
    assert d["warn_pct"] == 92
    assert d["crit_pct"] == 96
    assert d["temp_warn_c"] == 75
    assert d["temp_crit_c"] == 82


# --- Endpoint (subprocess mock'lu) --------------------------------------------


def test_gpu_endpoint_available(monkeypatch):
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="12288, 8192, 4096, 45, 85.5, 30"),
    )
    r = client.get("/api/telemetry/gpu")
    assert r.status_code == 200
    d = r.json()
    assert d["available"] is True
    assert d["vram_used_mb"] == 8192
    assert d["used_pct"] == 66.7
    assert d["level"] == "ok"
    assert "ts" in d


def test_gpu_endpoint_crit_level(monkeypatch):
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="12288, 11900, 388, 78, 140.2, 97"),
    )
    d = client.get("/api/telemetry/gpu").json()
    assert d["level"] == "crit"


def test_gpu_endpoint_no_binary(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError("nvidia-smi yok")

    monkeypatch.setattr("api.routes.telemetry.subprocess.run", _raise)
    d = client.get("/api/telemetry/gpu").json()
    assert d["available"] is False
    assert d["error"]


def test_gpu_endpoint_smi_error(monkeypatch):
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(returncode=1, stdout=""),
    )
    d = client.get("/api/telemetry/gpu").json()
    assert d["available"] is False


def test_gpu_endpoint_garbage_output(monkeypatch):
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="birseyler ters gitti"),
    )
    d = client.get("/api/telemetry/gpu").json()
    assert d["available"] is False
    assert d["error"]


# --- NPU Telemetrisi (Sprint 51) ----------------------------------------------


def test_parse_npu_devices():
    from api.routes.telemetry import parse_npu_devices

    assert parse_npu_devices("NPU Compute Accelerator Device\n  \n") == [
        "NPU Compute Accelerator Device"
    ]
    assert parse_npu_devices("") == []


def test_npu_endpoint_available(monkeypatch):
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="NPU Compute Accelerator Device\n"),
    )
    d = client.get("/api/telemetry/npu").json()
    assert d["available"] is True
    assert d["devices"] == ["NPU Compute Accelerator Device"]
    assert d["utilization_pct"] is None  # sayaç yok — dürüst boşluk
    assert "ts" in d


def test_npu_endpoint_not_found(monkeypatch):
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout=""),
    )
    d = client.get("/api/telemetry/npu").json()
    assert d["available"] is False
    assert d["devices"] == []


def test_npu_endpoint_powersless_error(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError("powershell yok")

    monkeypatch.setattr("api.routes.telemetry.subprocess.run", _raise)
    d = client.get("/api/telemetry/npu").json()
    assert d["available"] is False
    assert d["error"]


# --- Enerji & Maliyet (Sprint 45) ---------------------------------------------


def _seed_benchmark(model: str, tps: float) -> None:
    from api import db as dbmod

    con = dbmod.connect()
    try:
        con.execute(
            "INSERT INTO benchmarks (model, provider, measured_tps, source) "
            "VALUES (?, 'ollama', ?, 'real')",
            (model, tps),
        )
        con.commit()
    finally:
        con.close()


def test_energy_models_list():
    _seed_benchmark("qwen3:8b", 41.2)
    d = client.get("/api/telemetry/energy").json()
    models = {m["model"]: m for m in d["models"]}
    assert "qwen3:8b" in models
    assert models["qwen3:8b"]["measured_tps"] == 41.2


def test_energy_estimate_live_power(monkeypatch):
    _seed_benchmark("qwen3:8b", 40.0)
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="12288, 9000, 3288, 60, 95.0, 99"),
    )
    r = client.get("/api/telemetry/energy/qwen3:8b")
    assert r.status_code == 200
    d = r.json()
    assert d["power_source"] == "live"
    assert d["power_w"] == 95.0
    assert d["measured_tps"] == 40.0
    assert d["tok_per_joule"] == round(40.0 / 95.0, 2)
    assert "cost_try_month" in d and "cloud_cost_try_month" in d


def test_energy_estimate_assumed_power(monkeypatch):
    """Telemetri yoksa config varsayılan watt + dürüst 'assumed' etiketi."""
    _seed_benchmark("muse:30b", 7.5)

    def _raise(*a, **kw):
        raise FileNotFoundError("nvidia-smi yok")

    monkeypatch.setattr("api.routes.telemetry.subprocess.run", _raise)
    d = client.get("/api/telemetry/energy/muse:30b").json()
    assert d["power_source"] == "assumed"
    assert d["power_w"] > 0


def test_energy_estimate_idle_gpu_assumed(monkeypatch):
    """Sprint 52 (K8): GPU var ama idle (util < %20) → idle watt'la yanıltıcı
    iyimser 'live' tok/J üretilmez; assumed yük watt'ı kullanılır."""
    _seed_benchmark("qwen3:8b", 40.0)
    monkeypatch.setattr(
        "api.routes.telemetry.subprocess.run",
        lambda *a, **kw: _FakeProc(stdout="12288, 900, 11388, 40, 15.0, 3"),
    )
    d = client.get("/api/telemetry/energy/qwen3:8b").json()
    assert d["power_source"] == "assumed"  # util=3 < 20 → live sayılmaz


def test_energy_unknown_model_404():
    r = client.get("/api/telemetry/energy/olmayan-model")
    assert r.status_code == 404
