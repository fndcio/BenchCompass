"""api/routes/dashboard.py — Dashboard route'ları (Sprint 31 Y7 bölme).

`api/main.py`'den taşındı: summary/history/snapshot/delete + grafiks/ekstra +
export/report. Davranış birebir korunur (route path'leri değişmez).
Test uyumu: monkeypatch hedefleri `api.routes.shared.X`; sabit/yardımcılar
`shared` modül nesnesi üzerinden erişilir (conftest izolasyonu için).
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Body, Response

from .. import db as dbmod
from . import shared

router = APIRouter()


@router.get("/api/dashboard/summary")
def dashboard_summary():
    """Mevcut davranisi birebir korur — ayni JSON shape, fazladan yapilsal alanlar."""
    con = dbmod.connect()
    try:
        latest = dbmod.fetch_latest(con)
        shared._enrich_models_with_real_benchmark(con, latest.get("models") or [])
        shared._enrich_models_with_community_speed(latest.get("models") or [])
        shared._enrich_models_with_family_score(latest.get("models") or [])
        return {
            "source": "sqlite",
            "latest": latest,
            "history": dbmod.fetch_history(con, 200),
        }
    finally:
        con.close()


@router.get("/api/dashboard/history")
def dashboard_history():
    con = dbmod.connect()
    try:
        return {"history": dbmod.fetch_history(con, 200)}
    finally:
        con.close()


@router.post("/api/dashboard/snapshot")
def dashboard_snapshot(payload: dict = Body(default_factory=dict)):  # noqa: B008
    """Snapshot olusturur. Boş isim gelirse otomatik timestamp uretilir."""
    name = (payload.get("name") or "").strip()
    if not name:
        name = datetime.now().strftime("%Y-%m-%d-%H:%M")
    con = dbmod.connect()
    try:
        return dbmod.insert_snapshot(con, name)
    finally:
        con.close()


@router.delete("/api/dashboard/history")
def dashboard_history_delete(payload: dict = Body(default_factory=dict)):  # noqa: B008
    """Sprint 17 — history toplu/seçerek silme.

    Body: {"run_ids": [1,2,3]} → seçilen run'lar silinir
          {"all": true}        → tüm history silinir
    Donus: {"ok": true, "deleted": N}
    """
    run_ids = payload.get("run_ids") or []
    all_flag = payload.get("all") is True
    con = dbmod.connect()
    try:
        deleted = (
            dbmod.delete_all_runs(con) if all_flag else dbmod.delete_runs(con, run_ids)
        )
        return {"ok": True, "deleted": deleted}
    finally:
        con.close()


@router.get("/api/grafiks/ekstra")
def extra_chart_data():
    """5 yeni grafik icin veri doner (frontend charts.js ile render eder).

    Donus:
      score_components_radar: top-5 modelin fit/quality/speed/context skorlari
      param_speed_scatter: {param_count_b, estimated_speed_tok_s} array
      fit_level_distribution: {Perfect: N, Good: N, ...}
      moe_trend: her snapshot icin MoE model yuzdesi
      capabilities_pie: {Tool Use: N, Vision: N, ...}
    """
    con = dbmod.connect()
    try:
        # Son run verisini al
        latest = dbmod.fetch_latest(con)
        models = latest.get("models", [])

        # Radar grafigi icin top-5 modeller
        radar = []
        for m in models[:5]:
            radar.append(
                {
                    "name": m.get("name", ""),
                    "fit": m.get("fit_score", 0),
                    "context": m.get("context_length_supported")
                    or m.get("context_window", 0),
                    "speed": m.get("estimated_speed_tok_s", 0),
                }
            )

        # param_speed_scatter
        scatter = [
            {
                "p": m.get("param_count_b"),
                "s": m.get("estimated_speed_tok_s"),
                "n": m.get("name", ""),
            }
            for m in models
            if m.get("param_count_b") and m.get("estimated_speed_tok_s")
        ]

        # fit_level
        fl: dict[str, int] = {}
        for m in models:
            lvl = m.get("fit_level") or "Unknown"
            fl[lvl] = fl.get(lvl, 0) + 1

        # moe_trend (her snapshot icin)
        history = dbmod.fetch_history(con, limit=50)
        moe_trend = []
        for h in history:
            ms = h.get("models", [])
            moe_count = sum(1 for m in ms if m.get("is_moe"))
            moe_trend.append(
                {
                    "run": h.get("name", ""),
                    "total": len(ms),
                    "moe": moe_count,
                    "pct": round(100 * moe_count / len(ms), 1) if ms else 0,
                }
            )

        # capabilities_pie
        caps: dict[str, int] = {}
        for m in models:
            raw = m.get("capabilities", "")
            for c in raw.split(","):
                c = c.strip()
                if c:
                    caps[c] = caps.get(c, 0) + 1

        return {
            "score_components_radar": radar,
            "param_speed_scatter": scatter,
            "fit_level_distribution": fl,
            "moe_trend": moe_trend,
            "capabilities_pie": caps,
        }
    finally:
        con.close()


@router.get("/api/export/report")
def export_report():
    """Kapsamli benchmark raporu (Markdown) olusturur.

    Rapor: donanim profili, tier ozeti, benchmark gecmisi, model detaylari.
    """
    con = dbmod.connect()
    try:
        latest = dbmod.fetch_latest(con)
        history = dbmod.fetch_history(con, 200)
        hw = {}
        if shared.HARDWARE_FILE.exists():
            hw = json.loads(shared.HARDWARE_FILE.read_text(encoding="utf-8"))

        lines = ["# BenchCompass — Benchmark Raporu", ""]
        lines.append(f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Kaynak:** {latest.get('source', 'sqlite')}")
        lines.append("")

        # Donanim
        active_id = hw.get("active_profile", "")
        profiles = hw.get("profiles", [])
        active: dict = next((p for p in profiles if p.get("id") == active_id), {})
        lines.append("## Donanim Profili")
        lines.append(f"- **Cihaz:** {active.get('device_name', '-')}")
        lines.append(f"- **GPU:** {active.get('gpu', '-')}")
        lines.append(f"- **VRAM:** {active.get('vram_gb', '-')} GB")
        lines.append(f"- **RAM:** {active.get('ram_gb', '-')} GB")
        lines.append("")

        # Tier dagilimi
        models = latest.get("models", [])
        tiers = {
            "Tam Uyumlu": 0,
            "Uyumlu (Sinirda)": 0,
            "Dikkatli Kullan": 0,
            "Uygun Degil": 0,
        }
        from ..schemas import HardwareProfileEntry, ModelRecord, TierThresholds

        hw_entry = (
            HardwareProfileEntry(**active)
            if active
            else HardwareProfileEntry(
                id="unknown", device_name="-", vram_gb=0, ram_gb=0
            )
        )
        for m in models:
            from ..compat import compute_tier

            thresholds_obj = TierThresholds(**hw.get("tier_thresholds", {}))
            t = compute_tier(ModelRecord(**m), hw_entry, thresholds_obj)
            if t.tier in tiers:
                tiers[t.tier] += 1
        lines.append("## Tier Dagilimi (Aktif Havuz)")
        for tier_name, count in tiers.items():
            lines.append(f"- **{tier_name}:** {count} model")
        lines.append("")

        # Top modeller
        lines.append("## En Yuksek Fit Skorlular")
        sorted_models = sorted(
            models, key=lambda m: m.get("fitScore") or 0, reverse=True
        )[:10]
        for i, m in enumerate(sorted_models, 1):
            name = m.get("name", "-")
            fit = m.get("fitScore", "-")
            prov = m.get("provider", "-")
            lines.append(f"  {i}. **{name}** — Fit: {fit}, Provider: {prov}")
        lines.append("")

        # Benchmark gecmisi
        bench_rows = con.execute(
            "SELECT * FROM benchmarks ORDER BY id DESC LIMIT 20"
        ).fetchall()
        if bench_rows:
            lines.append("## Benchmark Gecmisi")
            lines.append("| Model | tok/s | TTFT (ms) | Tarih |")
            lines.append("|-------|-------|-----------|-------|")
            for r in bench_rows:
                lines.append(
                    f"| {r['model']} | {r['measured_tps']} | {r['ttft_ms']} | {r['created_at']} |"
                )
            lines.append("")

        # Gecmis run ozeti
        lines.append("## Snapshot Gecmisi")
        for h in history[-10:]:
            ms = h.get("models", [])
            lines.append(
                f"- **{h.get('name', '-')}** ({h.get('created_at', '-')}) — {len(ms)} model"
            )
        lines.append("")

        report = "\n".join(lines)
        return Response(
            content=report,
            media_type="text/markdown",
            headers={
                "Content-Disposition": "attachment; filename=benchcompass-benchmark-report.md"
            },
        )
    finally:
        con.close()


@router.get("/api/score/normalized")
def get_normalized_score(model: str, tps: float, gpu: str = "") -> dict:
    """Ölçülen tok/s'yi donanım sınıfı veya topluluk ortalamasına göre normalize eder (P1-1)."""
    from ..bench_data import get_bench

    bench = get_bench()
    ref_tps = bench.get_reference_tps(model_name=model, gpu_name=gpu)
    score: float | None = None
    if ref_tps and ref_tps > 0 and tps > 0:
        score = round((tps / ref_tps) * 100, 1)
    return {
        "model": model,
        "measured_tps": tps,
        "ref_tps": ref_tps,
        "score": score,
        "unit": "% of class average",
    }


@router.get("/api/calibration/summary")
def get_calibration_summary(limit: int = 30) -> dict:
    """Son N ölçümdeki tahmin kalibrasyonunu ve sapma istatistiklerini özetler (P1-2)."""
    from ..calibration import summarize_calibration

    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT model, measured_tps, predicted_tps, prediction_delta_pct, created_at "
            "FROM benchmarks "
            "WHERE prediction_delta_pct IS NOT NULL "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        records = [
            {
                "model": r["model"],
                "measured_tps": r["measured_tps"],
                "predicted_tps": r["predicted_tps"],
                "prediction_delta_pct": r["prediction_delta_pct"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        summary = summarize_calibration(records)
        summary["records"] = records
        return summary
    finally:
        con.close()
