"""api/routes/catalog.py — Katalog route'ları (Sprint 31 Y7 bölme).

`api/main.py`'den taşındı: catalog summary/search + hf-search.
"""

from __future__ import annotations

from fastapi import APIRouter

from .. import catalog
from .. import benchcompass_proxy

router = APIRouter()


@router.get("/api/catalog")
def catalog_summary():
    """Yerel kataloğun özeti: kayıt sayısı + mevcut provider'lar."""
    cat = catalog.get_catalog()
    return {
        "loaded": cat.loaded,
        "total_models": len(cat.models),
        "providers": catalog.providers()[:50],
        "source": str(catalog.DEFAULT_CATALOG_PATH),
    }


@router.get("/api/catalog/search")
def catalog_search(
    q: str = "",
    provider: str = "",
    use_case: str = "",
    is_moe: bool | None = None,
    min_ctx: int = 0,
    limit: int = 20,
):
    """Yerel katalogda ara (ağ yok — hf_models.json). Sonuç ModelRecord şeması."""
    cat = catalog.get_catalog()
    results = cat.search(
        q=q,
        provider=provider,
        use_case=use_case,
        is_moe=is_moe,
        min_ctx=min_ctx,
        limit=limit,
    )
    return {
        "total": len(results),
        "limit": limit,
        "source": "local-catalog",
        "models": [cat.to_model_record(m).model_dump() for m in results],
    }


@router.get("/api/hf-search")
def hf_search(query: str, limit: int = 20):
    """HuggingFace GGUF model ara (llmfit hf-search uzerinden)."""
    try:
        return benchcompass_proxy.llmfit_hf_search(query, limit=limit)
    except benchcompass_proxy.LlmfitError as e:
        # hf-search bazen bos doner (eslesme yoksa) — bu hata degil
        return {"models": [], "error": e.message}
