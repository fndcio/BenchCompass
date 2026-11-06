"""api/routes/benchcompass.py — benchcompass proxy route'ları (Sprint 31 Y7 bölme).

`api/main.py`'den taşındı: info/plan/diff/system/recommend/doctor/fit/cache +
fit/baseline. Davranış birebir korunur. Test uyumu: `shared.X` üzerinden erişim.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Response
from pydantic import BaseModel as PydBaseModel

from .. import fit_scores
from . import shared

router = APIRouter()


class PlanRequest(PydBaseModel):
    model: str
    context: int = 8192
    memory_gb: float | None = None
    vram_gb: float | None = None
    quant: str | None = None
    target_tps: float | None = None


@router.get("/api/benchcompass/info/{model_name:path}")
def llmfit_info_endpoint(model_name: str, refresh: bool = False):
    """llmfit info <model> --json — tek model detayi.

    Model Detay modalinda kullanilir: score_components radar grafigi,
    verify_command, gguf_sources, alternative_quants, estimate_basis.
    """
    try:
        return shared.benchcompass_proxy.llmfit_info(model_name, use_cache=not refresh)
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.post("/api/benchcompass/plan")
def llmfit_plan_endpoint(req: PlanRequest, refresh: bool = False):
    """llmfit plan <model> --context N --json — upgrade simülasyonu.

    Ayarlar sekmesindeki Upgrade Simulatoru icin: VRAM/RAM slider + context
    dropdown ile 'bu model bu donanimda calisir mi?' sorusu cevaplanir.
    """
    try:
        return shared.benchcompass_proxy.llmfit_plan(
            model_name=req.model,
            context=req.context,
            memory_gb=req.memory_gb,
            vram_gb=req.vram_gb,
            quant=req.quant,
            target_tps=req.target_tps,
            use_cache=not refresh,
        )
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.get("/api/benchcompass/diff")
def llmfit_diff_endpoint(
    a: str | None = None,
    b: str | None = None,
    top_n: int = 2,
    refresh: bool = False,
):
    """llmfit diff a b --json (veya auto top N) — iki model karsilastirma.

    Model Karsilastirma modalinda kullanilir.
    """
    try:
        return shared.benchcompass_proxy.llmfit_diff(
            a, b, top_n=top_n, use_cache=not refresh
        )
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.get("/api/benchcompass/system")
def llmfit_system_endpoint(refresh: bool = False):
    """llmfit system --json — gercek donanim tespiti.

    Ayarlar'daki 'Otomatik tespit' butonu icin.
    """
    try:
        return shared.benchcompass_proxy.llmfit_system(use_cache=not refresh)
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.get("/api/recommend")
def llmfit_recommend_endpoint(
    use_case: str = "general",
    limit: int = 10,
    min_fit: str | None = None,
    tool_use: bool = False,
    refresh: bool = False,
):
    """llmfit recommend --use-case X --json — use-case bazli tavsiye.

    Karar asistanini guclendirmek icin. llmfit'in 6 use-case degeri:
    general, coding, reasoning, chat, multimodal, embedding.
    """
    try:
        return shared.benchcompass_proxy.llmfit_recommend(
            use_case=use_case,
            limit=limit,
            min_fit=min_fit,
            tool_use=tool_use,
            use_cache=not refresh,
        )
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.get("/api/fit/baseline")
def fit_baseline(model: str = "", role: str = "coding"):
    """Sprint 21 — frontier baseline karşılaştırması.

    baselines.json'dan seçili model + rol için baseline skorlarını ve aynı
    rolün en iyi baseline modelini döndürür. Model yerel değilse yalnızca
    `top` bilgisi gelir (kullanıcı yerel modelini karşılaştırabilir).
    """
    fit = fit_scores.get_fit()
    role_key = role if role in ("coding", "reasoning", "chat", "general") else "coding"
    top = fit.top_baseline_for_role(role_key)
    baseline = None
    if model:
        baseline = fit.baseline_for_role(model, role_key)
    return {
        "model": model,
        "role": role_key,
        "baseline": baseline,
        "top_baseline": top,
        "available": bool(fit.baselines),
    }


@router.get("/api/benchcompass/doctor")
def llmfit_doctor_endpoint(refresh: bool = False):
    """llmfit doctor — donanim tespit raporu.

    Hardware detayli diagnostik: GPU, CPU, RAM, VRAM, backend, driver surumleri.
    """
    try:
        report = shared.benchcompass_proxy.llmfit_doctor(use_cache=not refresh)
        return {"ok": True, "report": report}
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.get("/api/benchcompass/fit")
def llmfit_fit_endpoint(refresh: bool = False):
    """llmfit fit --json — tum modellerin fit siralamasi.

    llmfit'in katalogundaki her model icin fit_score, tier, estimated_speed,
    memory_required, context bilgisi. Frontend bu veriyi DB'deki modellerle
    birlestirebilir.
    """
    try:
        return shared.benchcompass_proxy.llmfit_fit(refresh=refresh)
    except shared.benchcompass_proxy.LlmfitError as e:
        return shared._llmfit_error_response(e)


@router.post("/api/benchcompass/cache/clear")
def llmfit_cache_clear(pattern: str = ""):
    """llmfit proxy cache'ini temizler.

    pattern verilirse sadece o kelimeyi iceren key'leri siler.
    Ornek: 'recommend' -> sadece recommend cache'ini temizler.
    """
    shared.benchcompass_proxy.cache_clear(pattern)
    return {"ok": True, "cleared": True, "pattern": pattern or "all"}


@router.get("/api/benchcompass/cache/status")
def llmfit_cache_status():
    """Cache durumunu dondurur (kac entry, hangi key'ler)."""
    now = time.time()
    entries = []
    for k, (expires, v) in shared.benchcompass_proxy._CACHE.items():
        entries.append(
            {
                "key": k[:60],
                "ttl_remaining": round(max(0, expires - now)),
                "size": len(str(v)[:200]),
            }
        )
    return {"ok": True, "count": len(entries), "entries": entries}


@router.get("/api/share-card/svg")
def share_card_svg(
    model: str = "Gemma-4-12B-It",
    tps: float = 62.5,
    ttft_ms: float = 145.0,
    tier: str = "Tam Uyumlu",
    gpu: str | None = None,
    context_window: int = 4096,
    score: float | None = None,
):
    """Sosyal medya paylaşımı için 1200x630 SVG infografik üretir."""
    from ..share_card import generate_share_card_svg

    svg_content = generate_share_card_svg(
        model=model,
        tps=tps,
        ttft_ms=ttft_ms,
        tier=tier,
        gpu=gpu,
        context_window=context_window,
        score=score,
    )
    return Response(content=svg_content, media_type="image/svg+xml")
