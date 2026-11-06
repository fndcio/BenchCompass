"""api/concurrent_bench.py — Eşzamanlılık stres ölçümü (Adım 4, 06.11.2026).

N paralel SSE streaming isteğiyle N=1/2/4/8 seviyelerinde TTFT/ITL
gecikme dağılımı (p50/p95/p99) + toplam decode throughput ölçer.
Kuyruk etkisi = N=1 bazına göre p95 artış oranı.

Tasarım: `generate_fn` enjekte edilebilir (testte sahte ölçüm); varsayılan
`api.openai_client.openai_generate` (SSE streaming, Adım 2).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Yüzdelik (lineer interpolasyon, stdlib only). Boş listede 0.0."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 1)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    value = sorted_values[low] * (1 - frac) + sorted_values[high] * frac
    return round(value, 1)


def _latency_stats(latencies_ms: list[float]) -> dict[str, float]:
    """{p50, p95, p99, mean} — sıralı gecikmelerden."""
    ordered = sorted(latencies_ms)
    n = len(ordered)
    mean = round(sum(ordered) / n, 1) if n else 0.0
    return {
        "p50": _percentile(ordered, 50),
        "p95": _percentile(ordered, 95),
        "p99": _percentile(ordered, 99),
        "mean": mean,
    }


def run_one_level(
    model: str,
    base_url: str,
    prompt: str,
    max_tokens: int,
    concurrency: int,
    generate_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Tek eşzamanlılık seviyesi: N paralel üretim + istatistikler.

    Başarısız çağrılar `errors` sayılır; en az 1 başarı yoksa hata fırlatır.
    """

    def _call() -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            gen = generate_fn(
                prompt=prompt,
                model=model,
                base_url=base_url,
                max_tokens=max_tokens,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            return {
                "ok": True,
                "ttft_ms": float(gen.get("ttft_ms") or 0.0),
                "itl_ms": gen.get("itl_ms"),
                "tps": float(gen.get("tps") or 0.0),
                "total_ms": elapsed_ms,
            }
        except Exception as exc:  # noqa: BLE001 — tek çağrı hatası toplama girer
            return {"ok": False, "error": str(exc), "ttft_ms": 0.0, "tps": 0.0}

    count = max(1, concurrency)
    with ThreadPoolExecutor(max_workers=count) as pool:
        rows = list(pool.map(lambda _: _call(), range(count)))

    ok_rows = [r for r in rows if r.get("ok")]
    if not ok_rows:
        raise RuntimeError("tüm eşzamanlı çağrılar başarısız oldu")
    latencies = [float(r["total_ms"]) for r in ok_rows]
    ttfts = [float(r["ttft_ms"]) for r in ok_rows if r.get("ttft_ms")]
    stats = _latency_stats(latencies)
    ttft_stats = (
        _latency_stats(ttfts)
        if ttfts
        else {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}
    )
    throughput = round(sum(float(r["tps"]) for r in ok_rows), 1)
    return {
        "concurrency": count,
        "success": len(ok_rows),
        "errors": len(rows) - len(ok_rows),
        "latency_p50_ms": stats["p50"],
        "latency_p95_ms": stats["p95"],
        "latency_p99_ms": stats["p99"],
        "latency_mean_ms": stats["mean"],
        "ttft_p50_ms": ttft_stats["p50"],
        "ttft_p95_ms": ttft_stats["p95"],
        "throughput_tps": throughput,
    }


def run_concurrent_stress(
    model: str,
    base_url: str,
    prompt: str,
    max_tokens: int,
    levels: list[int],
    generate_fn: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Tüm seviyeler + kuyruk etkisi (N=1 baz p95'e göre artış %)."""
    if generate_fn is None:
        from .openai_client import openai_generate as default_fn

        generate_fn = default_fn

    ordered = sorted({max(1, int(level)) for level in levels}) or [1]
    results = [
        run_one_level(model, base_url, prompt, max_tokens, level, generate_fn)
        for level in ordered
    ]
    base_p95 = next(
        (r["latency_p95_ms"] for r in results if r["concurrency"] == 1), None
    )
    for row in results:
        if base_p95 and row["concurrency"] > 1:
            row["queue_effect_pct"] = round(
                (row["latency_p95_ms"] - base_p95) / base_p95 * 100.0, 1
            )
        else:
            row["queue_effect_pct"] = 0.0
    return results
