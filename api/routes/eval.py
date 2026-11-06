"""api/routes/eval.py — LLMFit Benchmark Eval geçmiş koşu route'ları (Sprint 34).

`benchmarks` SQLite zaman serisinden geçmiş koşu listesi + per-model trend.
ADR-0004 Gelecek: dashboard `[ RAPOR ]` sekmesi için.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import db as dbmod

router = APIRouter()


@router.get("/api/eval/history")
def eval_history(
    model: str | None = Query(None, description="Model adı filtresi"),
    limit: int = Query(100, ge=1, le=500),
):
    """Geçmiş benchmark koşularını döndürür (koşu tarihi, model, tps, ttft).

    SQLite ``benchmarks`` tablosundan okur. ``model`` verilirse o modele ait
    zaman serisi döner (trend görünümü için).
    """
    con = dbmod.connect()
    try:
        if model:
            rows = con.execute(
                "SELECT id, model, provider, measured_tps, ttft_ms, source, created_at "
                "FROM benchmarks WHERE model=? AND measured_tps IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (model, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, model, provider, measured_tps, ttft_ms, source, created_at "
                "FROM benchmarks WHERE measured_tps IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {
            "ok": True,
            "total": len(rows),
            "runs": [dict(r) for r in rows],
        }
    finally:
        con.close()


@router.get("/api/eval/history/models")
def eval_history_models():
    """Geçmiş koşusu olan benzersiz model adları (liste sekmesi için)."""
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT DISTINCT model FROM benchmarks "
            "WHERE measured_tps IS NOT NULL ORDER BY model"
        ).fetchall()
        return {"ok": True, "models": [r["model"] for r in rows]}
    finally:
        con.close()


@router.get("/api/eval/compare")
def eval_compare(
    model_a: str = Query(..., description="Model A adı"),
    model_b: str = Query(..., description="Model B adı"),
):
    """İki modelin eşli (aynı görev) kalite karşılaştırması — McNemar (Adım 3).

    Kaynak: ``benchmark_quality`` (kodlama görevleri, artefakt-g7 hariç).
    Her (model, gorev) için en yeni kayıt alınır, ``pass1`` ikili eşli listeler
    kurulur; McNemar exact (stdlib) + görev bazlı drill-down döner.
    """
    con = dbmod.connect()
    try:
        from plugin.benchcompass_benchmark_eval.benchcompass_benchmark_eval.grading import (  # type: ignore[import-not-found]
            compare_details,
        )
    except ImportError:
        # Plugin kurulu değilse inline exact (aynı formül, stdlib).
        import math as _math

        def _p(b: int, c: int) -> float:
            n = b + c
            if n == 0:
                return 1.0
            k = min(b, c)
            tail = sum(_math.comb(n, i) * (0.5**n) for i in range(k + 1))
            return min(1.0, 2.0 * tail)

        def compare_details(details_a, details_b):  # type: ignore[no-redef]
            pa = {str(d["id"]): bool(d["pass"]) for d in details_a}
            pb = {str(d["id"]): bool(d["pass"]) for d in details_b}
            common = sorted(set(pa) & set(pb))
            b = sum(1 for k in common if pa[k] and not pb[k])
            c = sum(1 for k in common if not pa[k] and pb[k])
            p = _p(b, c)
            rows = [
                {
                    "id": k,
                    "a_pass": pa[k],
                    "b_pass": pb[k],
                    "category": (
                        "both_pass"
                        if pa[k] and pb[k]
                        else "both_fail"
                        if (not pa[k] and not pb[k])
                        else "a_only"
                        if pa[k]
                        else "b_only"
                    ),
                }
                for k in common
            ]
            return {
                "n": len(common),
                "b": b,
                "c": c,
                "discordant": b + c,
                "p_value": round(p, 6),
                "significant": p < 0.05,
                "tasks": rows,
            }

    try:
        rows = con.execute(
            "SELECT model, gorev, pass1 FROM benchmark_quality "
            "WHERE COALESCE(gecerlilik, 'gecerli') <> 'artefakt-g7' "
            "AND model IN (?, ?) ORDER BY id DESC",
            (model_a, model_b),
        ).fetchall()
        latest: dict[tuple[str, str], bool] = {}
        for r in rows:
            key = (r["model"], r["gorev"])
            if key not in latest:
                latest[key] = bool(r["pass1"])
        details_a = [
            {"id": gorev, "pass": ok}
            for (m, gorev), ok in latest.items()
            if m == model_a
        ]
        details_b = [
            {"id": gorev, "pass": ok}
            for (m, gorev), ok in latest.items()
            if m == model_b
        ]
        result = compare_details(details_a, details_b)
        return {
            "ok": True,
            "model_a": model_a,
            "model_b": model_b,
            **result,
        }
    finally:
        con.close()


@router.get("/api/eval/quality")
def eval_quality(limit: int = Query(500, ge=1, le=2000)):
    """Kodlama değerlendirmesinin KALİTE boyutu (``benchmark_quality``, 7 Ekim 2026).

    `benchmarks` tablosu yalnız hız (tok/s) tutar; Pass@1/Pass@N ve
    visible/hidden sonuçları bu tablodadır. Denetim bulgusu P0-2'nin kapanışı:
    sonuçlar artık sorgulanabilir kalıcı veride.

    `gecerlilik='artefakt-g7'` kayıtları **silinmez**, işaretlenir (trust
    kolonu deseni) — 6 Ekim'de G7 test modülü iki isim import ederken prompt tek
    fonksiyon istiyordu, collection `ImportError` doğru cevabı "başarısız"
    gösteriyordu (bkz. lessons-learned-2026-10-07). ``ozet`` yalnız geçerli
    ölçümlerden türetilir.
    """
    con = dbmod.connect()
    try:
        kayitlar = dbmod.fetch_quality(con, limit=limit)
        ozet = dbmod.quality_summary(con)
        return {
            "ok": True,
            "total": len(kayitlar),
            "ozet": ozet,
            "kayitlar": kayitlar,
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Adım 6 — YAML suite + red-team (ADR-0017, §9.2 pyyaml onayı)
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class RedteamGradeBody(BaseModel):
    """Red-team grade isteği (Y23: JSON body için Pydantic modeli zorunlu)."""

    task_id: str
    response: str


def _redteam_module():
    """Plugin redteam modülünü yükler; yoksa None."""
    import sys
    from pathlib import Path as _Path

    root = (
        _Path(__file__).resolve().parents[2] / "plugin" / "benchcompass-benchmark-eval"
    )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from benchcompass_benchmark_eval import redteam  # type: ignore[import-not-found]

        return redteam
    except ImportError:
        return None


@router.get("/api/eval/redteam-plan")
def eval_redteam_plan():
    """Red-team planı (halka açık: prompt + kategori; desenler kapalı)."""
    redteam = _redteam_module()
    if redteam is None:
        raise HTTPException(status_code=404, detail="red-team plugin modülü bulunamadı")
    return {"ok": True, "tasks": redteam.public_tasks()}


@router.post("/api/eval/redteam/grade")
def eval_redteam_grade(body: RedteamGradeBody):
    """Tek red-team yanıtını deterministik desenle değerlendirir.

    Kapsam dürüstlüğü: LLM-judge yok; desen tabanlı red tespitidir.
    """
    redteam = _redteam_module()
    if redteam is None:
        raise HTTPException(status_code=404, detail="red-team plugin modülü bulunamadı")
    task = redteam.find_task(body.task_id)
    if task is None:
        raise HTTPException(status_code=422, detail=f"bilinmeyen görev: {body.task_id}")
    result = redteam.grade_redteam(task, body.response)
    return {"ok": True, "task_id": body.task_id, **result}
