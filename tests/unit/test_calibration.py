"""tests/unit/test_calibration.py — Tahmin->Ölçüm Kalibrasyon Testleri (P1-2)."""

from fastapi.testclient import TestClient

from api.calibration import compute_calibration_delta, summarize_calibration
from api.db import connect
from api.main import app
from api.routes.shared import _save_benchmark_record


def test_compute_calibration_delta():
    # Model tahmin edilenden %20 daha hızlı
    assert compute_calibration_delta(30.0, 25.0) == 20.0

    # Model tahmin edilenden %20 daha yavaş
    assert compute_calibration_delta(20.0, 25.0) == -20.0

    # Birebir aynı hız
    assert compute_calibration_delta(25.0, 25.0) == 0.0

    # Geçersiz veya boş değerler
    assert compute_calibration_delta(None, 25.0) is None
    assert compute_calibration_delta(25.0, None) is None
    assert compute_calibration_delta(0.0, 25.0) is None
    assert compute_calibration_delta(25.0, 0.0) is None
    assert compute_calibration_delta(-5.0, 25.0) is None


def test_summarize_calibration_empty():
    summary = summarize_calibration([])
    assert summary["n"] == 0
    assert summary["accuracy_band"] == "insufficient_data"
    assert summary["mean_delta_pct"] is None


def test_summarize_calibration_bands():
    # Yeşil bant: sapmalar küçük (ortalama <= %10)
    green_records = [
        {"prediction_delta_pct": 5.0},
        {"prediction_delta_pct": -4.0},
        {"prediction_delta_pct": 8.0},
    ]
    summary_green = summarize_calibration(green_records)
    assert summary_green["n"] == 3
    assert summary_green["accuracy_band"] == "green"
    assert summary_green["within_10_pct_ratio"] == 1.0

    # Sarı bant: orta sapma (%10 < ortalama mutlak sapma <= %25)
    yellow_records = [
        {"prediction_delta_pct": 18.0},
        {"prediction_delta_pct": -15.0},
        {"prediction_delta_pct": 20.0},
    ]
    summary_yellow = summarize_calibration(yellow_records)
    assert summary_yellow["accuracy_band"] == "yellow"
    assert summary_yellow["within_10_pct_ratio"] == 0.0
    assert summary_yellow["within_25_pct_ratio"] == 1.0

    # Kırmızı bant: yüksek sapma (> %25)
    red_records = [
        {"prediction_delta_pct": 45.0},
        {"prediction_delta_pct": -35.0},
    ]
    summary_red = summarize_calibration(red_records)
    assert summary_red["accuracy_band"] == "red"


def test_calibration_api_endpoint(monkeypatch, tmp_path):
    # İzole geçici veritabanı
    test_db = tmp_path / "test_calibration.db"
    monkeypatch.setattr("api.db.DB", test_db)

    # DB hazırla
    con = connect()
    con.close()

    # Örnek benchmark kaydı ekle
    sample_result = {
        "measured_tps": 48.0,
        "predicted_tps": 40.0,
        "ttft_ms": 120.0,
        "output_tokens": 100,
        "total_ms": 2083.0,
        "source": "unit-test",
    }
    _save_benchmark_record("test-model-7b", "ollama", sample_result)

    client = TestClient(app)
    response = client.get("/api/calibration/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["n"] == 1
    assert data["records"][0]["model"] == "test-model-7b"
    assert data["records"][0]["measured_tps"] == 48.0
    assert data["records"][0]["predicted_tps"] == 40.0
    # (48 - 40) / 40 * 100 = 20.0%
    assert data["records"][0]["prediction_delta_pct"] == 20.0
    assert data["accuracy_band"] == "yellow"
