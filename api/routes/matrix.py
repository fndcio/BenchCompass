"""api/routes/matrix.py — Veri-güdümlü karar matrisi (Sprint 46) + görev
profili öneri motoru (Sprint 47).

KONTROL_MERKEZI.html'deki elle bakımlı 7-rollük master matrisinin yerine,
kendi verisinden türetilen canlı matris: roller ``fit_scores`` use-case
anahtarlarından doğar (veri-güdümlü — yeni use-case elenirse rol kartı
kendiliğinden belirir), adaylar son collector run'ı + aile skorlarıyla
sıralanır. Tier hesabı frontend'de yapılır (tek kaynak: computeTier mirror,
G8) — aday satırı gerekli donanım alanlarını taşır.

Frontier baseline karşılaştırması llmfit baselines.json'dan gelir (rol adı
eşleşirse; eşleşmezse kartta yer almaz — dürüst boşluk).

Sprint 47: ``POST /api/matrix/recommend`` — "bugünkü görev profilim"
ağırlıklarıyla (rol → 0-100) ağırlıklı skor sıralaması ve öneri seti.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import db as dbmod
from ..fit_scores import FitScores, get_fit

router = APIRouter()

# Tier hesabı için frontend'e taşınan alanlar (computeTier kontratı).
_TIER_FIELDS = ("required_vram_gb", "required_ram_gb", "run_mode")


class ProfileWeights(BaseModel):
    """Görev profili ağırlıkları — rol adı → 0-100 (Y23: Pydantic Body kontratı)."""

    weights: dict[str, float] = Field(default_factory=dict)


def _latest_run_models(limit: int = 100) -> list[dict[str, Any]]:
    """Son benchmark run'ının model satırları (dict)."""
    con = dbmod.connect()
    try:
        run = con.execute(
            "SELECT id FROM benchmark_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not run:
            return []
        rows = con.execute(
            "SELECT * FROM benchmark_models WHERE run_id = ? LIMIT ?",
            (run["id"], limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def measured_tps_map(source: str = "real") -> dict[str, Any]:
    """Model adı → en yeni ölçüm t/s (benchmarks tablosu, tek kaynak — Sprint 52).

    ``source`` ayrımı bilinçlidir: 'real' = serving mini-bench ölçümü;
    'benchkit' = 440 görevlük suite ortalaması. İkisi karşılaştırılabilir
    olmadığından (ve enerji/matris/sağlık turlarının hepsi serving performansı
    izlediğinden) çağıranlar varsayılan olarak yalnız 'real' okur.
    Sıralama id-bazlıdır (id ASC → son kazanır): benchkit'in geri tarihli
    damgaları kronolojiyi bozamaz. LIMIT, tablo yıllar içinde büyüdüğünde
    çağrı başına maliyeti sınırlar.
    """
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT model, measured_tps, created_at FROM benchmarks "
            "WHERE measured_tps IS NOT NULL AND source = ? "
            "ORDER BY id DESC LIMIT 2000",
            (source,),
        ).fetchall()
    finally:
        con.close()
    out: dict[str, Any] = {}
    for r in reversed(rows):  # DESC → ters çevir: son satır kazanır (en yeni)
        out[r["model"]] = {"tps": float(r["measured_tps"]), "last_at": r["created_at"]}
    return out


def roles_from_fit(fit: FitScores) -> list[str]:
    """Skor tablosunda görülen use-case anahtarlarını görülme sırasıyla döndürür.

    Roller sabit liste DEĞİL — veri-güdümlüdür (YAGNI): use_case_benchmarks.json'a
    yeni aile/skor eklendiğinde matrise yeni rol kartı otomatik düşer.
    """
    seen: list[str] = []
    for fam in fit.families:
        for key in fam.get("scores") or {}:
            if key not in seen:
                seen.append(key)
    return seen


@router.get("/api/matrix")
def decision_matrix(top_per_role: int = 3) -> dict[str, Any]:
    """Rol → adaylar matrisi: aile skoruyla sıralı top-N + frontier baseline."""
    models = _latest_run_models()
    fit = get_fit()
    tps_map = measured_tps_map()
    roles: list[dict[str, Any]] = []
    for role in roles_from_fit(fit):
        scored: list[dict[str, Any]] = []
        for m in models:
            name = m.get("name") or ""
            score = fit.use_case_score(name, role)
            if score is None:
                continue
            cand: dict[str, Any] = {
                "name": name,
                "score": score,
                "measured_tps": (tps_map.get(name) or {}).get("tps"),
            }
            for field in _TIER_FIELDS:
                cand[field] = m.get(field)
            scored.append(cand)
        scored.sort(key=lambda c: (-c["score"], c["name"]))
        roles.append(
            {
                "role": role,
                "candidates": scored[: max(1, min(top_per_role, 10))],
                "frontier_baseline": fit.top_baseline_for_role(role),
            }
        )
    return {"roles": roles, "model_count": len(models)}


def weighted_profile_score(
    scores: dict[str, Any], weights: dict[str, float]
) -> float | None:
    """Rol skorları + profil ağırlıkları → ağırlıklı ortalama (0-100).

    Skoru olmayan roller katkı vermez; hiçbir rol eşleşmezse veya ağırlık
    toplamı 0 ise None döner (dürüst boşluk). Saf fonksiyon — test edilir.
    """
    total_w = 0.0
    acc = 0.0
    for role, weight in weights.items():
        w = float(weight or 0)
        if w <= 0:
            continue
        score = scores.get(role)
        if score is None:
            continue
        total_w += w
        acc += w * float(score)
    if total_w <= 0:
        return None
    return round(acc / total_w, 1)


@router.post("/api/matrix/recommend")
def recommend_for_profile(body: ProfileWeights) -> dict[str, Any]:
    """Görev profili ağırlıklarına göre öneri seti (ağırlıklı skor sıralı)."""
    models = _latest_run_models()
    fit = get_fit()
    tps_map = measured_tps_map()
    roles = roles_from_fit(fit)
    weights = {k: v for k, v in body.weights.items() if k in roles}

    results: list[dict[str, Any]] = []
    for m in models:
        name = m.get("name") or ""
        scores = {role: fit.use_case_score(name, role) for role in roles}
        weighted = weighted_profile_score(scores, weights)
        if weighted is None:
            continue
        cand: dict[str, Any] = {
            "name": name,
            "weighted_score": weighted,
            "measured_tps": (tps_map.get(name) or {}).get("tps"),
        }
        for field in _TIER_FIELDS:
            cand[field] = m.get(field)
        results.append(cand)
    results.sort(key=lambda c: (-c["weighted_score"], c["name"]))
    return {
        "roles": roles,
        "weights_used": weights,
        "recommendations": results[:5],
        "model_count": len(models),
    }
