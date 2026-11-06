"""api/calibration.py — Tahmin -> Ölçüm Kalibrasyon Mantığı (P1-2).

`api/compat.py` ve `data/benchmark_cache.json` tarafından tahmin edilen tok/s
ile gerçekte ölçülen tok/s arasındaki sapmayı hesaplar ve özetler.
"""

from __future__ import annotations

import math
from typing import Any


def compute_calibration_delta(
    measured_tps: float | None, predicted_tps: float | None
) -> float | None:
    """Ölçülen ve tahmin edilen TPS arasındaki yüzde sapmayı hesaplar.

    Formül: (measured_tps - predicted_tps) / predicted_tps * 100
    Pozitif değer: Model beklenenden daha hızlı çalıştı.
    Negatif değer: Model beklenenden daha yavaş çalıştı (darboğaz/yük).
    """
    if measured_tps is None or predicted_tps is None:
        return None
    if predicted_tps <= 0 or measured_tps <= 0:
        return None
    return round(((measured_tps - predicted_tps) / predicted_tps) * 100, 2)


def summarize_calibration(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Kalibrasyon kayıtlarından istatistiksel özet üretir."""
    deltas = [
        r["prediction_delta_pct"]
        for r in records
        if r.get("prediction_delta_pct") is not None
    ]
    n = len(deltas)
    if n == 0:
        return {
            "n": 0,
            "mean_delta_pct": None,
            "abs_mean_delta_pct": None,
            "std_delta_pct": None,
            "median_delta_pct": None,
            "accuracy_band": "insufficient_data",
            "within_10_pct_ratio": 0.0,
            "within_25_pct_ratio": 0.0,
        }

    mean_delta = round(sum(deltas) / n, 2)
    abs_mean = round(sum(abs(d) for d in deltas) / n, 2)
    variance = sum((d - mean_delta) ** 2 for d in deltas) / n
    std_delta = round(math.sqrt(variance), 2)

    sorted_deltas = sorted(deltas)
    if n % 2 == 1:
        median_delta = round(sorted_deltas[n // 2], 2)
    else:
        median_delta = round((sorted_deltas[n // 2 - 1] + sorted_deltas[n // 2]) / 2, 2)

    within_10 = sum(1 for d in deltas if abs(d) <= 10.0)
    within_25 = sum(1 for d in deltas if abs(d) <= 25.0)

    if abs_mean <= 10.0:
        accuracy_band = "green"  # Yüksek isabet (±%10)
    elif abs_mean <= 25.0:
        accuracy_band = "yellow"  # Kabul edilebilir (±%25)
    else:
        accuracy_band = "red"  # Kalibrasyon gerekli (>%25)

    return {
        "n": n,
        "mean_delta_pct": mean_delta,
        "abs_mean_delta_pct": abs_mean,
        "std_delta_pct": std_delta,
        "median_delta_pct": median_delta,
        "accuracy_band": accuracy_band,
        "within_10_pct_ratio": round(within_10 / n, 2),
        "within_25_pct_ratio": round(within_25 / n, 2),
    }
