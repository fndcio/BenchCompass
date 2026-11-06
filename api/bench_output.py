"""llmfit bench çıktısı ortak normalizatörü (tek kaynak — Y17/DRY).

llmfit CLI'nin bench alt komutu sürümler arasında farklı JSON formatları
üretir (sürüm direnci). Bu normalizasyon daha önce İKİ yerde bağımsız
yazılmıştı (``benchcompass_proxy._normalize_bench_output`` ve
``ollama_client.run_benchmark``) ve ayrışmaya açıktı; Sprint 43 ile tek
kaynağa indirildi. Her iki çağıran da kendi dönüş şemasını bu modül
üzerinden üretir.

Desteklenen formatlar:
  - eski üst düzey: measured_tps / tokens_per_second / avg_tps / tok_s
  - results[] (liste) veya result (dict) blokları
  - llmfit 1.1.x: {"result": {"runs": [{"tps","ttft_ms",...}],
    "summary": {"avg_tps","avg_ttft_ms","num_runs",...}}}
"""

from __future__ import annotations

from typing import Any


def first_truthy(mapping: dict, *keys: str) -> Any:
    """Verilen anahtarlardan ilk truthy değeri döndür (or-zinciri semantiği).

    Değerler ``or`` zinciriyle aynı şekilde alınır — 0/" "/[] falsy kabul edilir
    (önceki sürüm davranışı korunur). Hiçbiri yoksa None döner.
    """
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def as_float(v) -> float | None:
    """Değeri float'a çevirir; None/dönüştürülemez ise None döner."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_top_level_bench(raw: dict) -> tuple:
    """Eski üst-düzey format: measured_tps / ttft / token / süre."""
    measured = first_truthy(
        raw, "measured_tps", "tokens_per_second", "avg_tps", "tok_s"
    )
    ttft = raw.get("ttft_ms") or raw.get("ttft")
    total_tokens = raw.get("total_tokens") or raw.get("tokens")
    total_ms = raw.get("total_ms")
    return measured, ttft, total_tokens, total_ms, None


def best_run(runs: list) -> dict | None:
    """En yüksek tps'li tekrarı temsilci seç (tps'si olanlar arasından)."""
    return max(
        (r for r in runs if r.get("tps") is not None),
        key=lambda r: r["tps"],
        default=None,
    )


def extract_dict_result(results: dict, ttft, total_tokens, total_ms) -> tuple:
    """llmfit 1.1.x: ``result`` dict bloğu — summary + runs[].tps.

    measured önceliği: results → summary (avg_tps/max_tps) → en iyi run.
    num_runs summary'den gelir (yoksa None — caller kendi varsayılanını kullanır).
    """
    summary = results.get("summary") or {}
    measured = first_truthy(
        results, "measured_tps", "tokens_per_second", "avg_tps"
    ) or first_truthy(summary, "avg_tps", "max_tps")
    ttft = ttft or results.get("ttft_ms") or summary.get("avg_ttft_ms")
    total_tokens = (
        total_tokens
        or results.get("total_tokens")
        or summary.get("total_tokens")
        or summary.get("avg_output_tokens")
    )
    total_ms = total_ms or results.get("total_ms") or summary.get("avg_total_ms")
    num_runs = summary.get("num_runs")

    runs = results.get("runs")
    if isinstance(runs, list) and runs:
        best = best_run(runs)
        if best is not None:
            if measured is None:
                measured = best["tps"]
            ttft = ttft or best.get("ttft_ms")
            total_tokens = total_tokens or best.get("output_tokens")
            total_ms = total_ms or best.get("total_ms")
    return measured, ttft, total_tokens, total_ms, num_runs


def extract_list_result(results: list, ttft, total_tokens, total_ms) -> tuple:
    """Eski ``results[]`` listesi: ilk öğeden değerler; num_runs = liste uzunluğu."""
    first = results[0]
    measured = first_truthy(
        first, "measured_tps", "tokens_per_second", "avg_tps", "tps"
    )
    ttft = ttft or first.get("ttft_ms")
    total_tokens = total_tokens or (
        first.get("total_tokens") or first.get("output_tokens")
    )
    total_ms = total_ms or first.get("total_ms")
    return measured, ttft, total_tokens, total_ms, len(results)


def normalize_bench_output(raw: dict) -> dict:
    """llmfit bench JSON çıktısını tutarlı şemaya çevirir (sürüm direnci).

    Dönüş: {measured_tps, ttft_ms, total_tokens, total_ms, num_runs,
    source: "real", raw_keys}. Eşleşen değerlerin ilkini kullanır;
    hiçbiri yoksa measured_tps=None döner (caller fallback karar verir).
    """
    measured, ttft, total_tokens, total_ms, num_runs = extract_top_level_bench(raw)
    raw_keys = list(raw.keys())

    # results[] içinde ilk öğe veya result (dict) iç içe olabilir
    results = raw.get("results") or raw.get("result")
    if isinstance(results, dict):
        measured, ttft, total_tokens, total_ms, num_runs = extract_dict_result(
            results, ttft, total_tokens, total_ms
        )
    elif isinstance(results, list) and results:
        measured, ttft, total_tokens, total_ms, num_runs = extract_list_result(
            results, ttft, total_tokens, total_ms
        )

    return {
        "measured_tps": as_float(measured),
        "ttft_ms": as_float(ttft),
        "total_tokens": total_tokens,
        "total_ms": as_float(total_ms),
        "num_runs": num_runs,
        "source": "real",
        "raw_keys": raw_keys,
    }
