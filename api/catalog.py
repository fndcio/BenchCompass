"""Yerel LLM model kataloğu — api/catalog.py

Sprint 19: AlexsJones/llmfit (MIT) `hf_models.json` (5744 gerçek model) yerel
katalog olarak sunulur. Local-First (AGENTS.md §1): veri `data/hf_models.json`
altında lokal yaşar; arama/filtreleme DB'ye YAZMAZ (tek kaynak: JSON).

Alan eşlemesi (to_model_record) tek yerde — frontend/backend ModelRecord
şemasına çevrilir (DRY/Y17). Schema migration YOK (Y15).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import ModelRecord

BASE = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_PATH = BASE / "data" / "hf_models.json"

# Katalog'da listelenen bilinen provider'lar (filtre UI için)
KNOWN_PROVIDERS = [
    "qwen",
    "meta",
    "mistralai",
    "deepseek",
    "google",
    "microsoft",
    "nvidia",
    "allenai",
    "openai",
    "ibm",
    "cohere",
]


class Catalog:
    """hf_models.json kataloğu — yükleme, arama, filtreleme, ModelRecord eşleme."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DEFAULT_CATALOG_PATH
        self.models: list[dict] = []
        self.loaded = False
        self.load()

    def load(self) -> None:
        """Kataloğu JSON'dan yükler. Dosya yoksa boş katalog (çökmez)."""
        if not self.path.exists():
            self.models = []
            self.loaded = False
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.models = data if isinstance(data, list) else []
            self.loaded = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.models = []
            self.loaded = False

    def search(
        self,
        q: str = "",
        provider: str = "",
        use_case: str = "",
        is_moe: bool | None = None,
        min_ctx: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Ad/provider alt-dizesi + provider/use_case/moe/context filtreleri."""
        query = q.strip().lower()
        uc = use_case.strip().lower()
        results = [
            m
            for m in self.models
            if _matches_filters(m, query, provider, uc, is_moe, min_ctx)
        ]
        results.sort(key=lambda m: -(m.get("hf_downloads") or 0))
        return results[: max(limit, 1)]

    def get(self, name: str) -> dict | None:
        """Tam model adıyla kaydı döndürür."""
        for m in self.models:
            if m.get("name") == name:
                return m
        return None

    def to_model_record(self, raw: dict) -> ModelRecord:
        """Katalog kaydını ModelRecord şemasına eşler (tek yer — DRY)."""
        sources = raw.get("gguf_sources") or []
        repo = sources[0].get("repo", "") if sources else (raw.get("name") or "")
        params_raw = raw.get("parameters_raw") or 0
        family_score = _family_fit_score(raw)
        return ModelRecord(
            name=raw.get("name") or "-",
            provider=raw.get("provider") or "-",
            use_case=raw.get("use_case") or "-",
            fit_score=family_score or 0.0,
            context_window=int(raw.get("context_length") or 0),
            notes=f"Yerel katalog ({repo})",
            required_vram_gb=_num(raw.get("min_vram_gb")),
            required_ram_gb=_num(raw.get("min_ram_gb")),
            context_length_supported=int(raw.get("context_length") or 0),
            context_length_estimated_at=None,
            quantization=raw.get("quantization"),
            param_count_b=_billion(params_raw),
            is_moe=bool(raw.get("is_moe")),
            active_params_b=_billion(raw.get("active_parameters")),
            total_params_b=_billion(params_raw),
        )


def _family_fit_score(raw: dict) -> float | None:
    """Sprint 21: use_case aile eşleşmesinden fit skoru (yoksa None)."""
    try:
        from .fit_scores import get_fit

        uc = str(raw.get("use_case") or "").lower()
        use_case_key = (
            "coding"
            if any(k in uc for k in ("code", "coder", "coding"))
            else (
                "reasoning" if "reasoning" in uc else ("chat" if "chat" in uc else None)
            )
        )
        if use_case_key:
            return get_fit().use_case_score(raw.get("name") or "", use_case_key)
    except Exception:  # noqa: BLE001 — aile verisi yoksa fit skoru None kalır
        return None
    return None


def _billion(v: Any) -> float | None:
    """Ham parametre sayısını milyar (B) cinsine çevirir."""
    if not v:
        return None
    return round(float(v) / 1e9, 2)


def _num(v: Any) -> float | None:
    """Sayısal değeri float'a çevirir; None/boş ise None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def use_case_key(use_case: str) -> str | None:
    """Serbest use_case metninden anahtar use_case döndürür (coding/reasoning/chat).

    TEK KAYNAK (AGENTS.md §1.6 DRY): katalog filtresi (`_matches_use_case`) ve
    aile skoru zenginleştirme (`api/routes/shared.py`) bu eşlemeyi paylaşır.
    `api/routes/shared.py`'deki eski yerel kopya kaldırıldı — buradan import eder.
    """
    uc = (use_case or "").lower()
    if any(k in uc for k in ("code", "coder", "coding")):
        return "coding"
    if "reasoning" in uc:
        return "reasoning"
    if "chat" in uc or "conversation" in uc or "instruction" in uc:
        return "chat"
    return None


def _matches_use_case(m: dict, uc: str) -> bool:
    """Use case filtresini model üzerinde kontrol eder (P0-1 & CC bölünmesi).

    Anahtar kelime eşlemesi `use_case_key` tek kaynağından gelir; katalog,
    kodlama modelleri için isim bazlı ek kural ("coder" geçen model adı) ekler.
    """
    model_uc = (m.get("use_case") or "").lower()
    model_name = (m.get("name") or "").lower()
    if use_case_key(model_uc) == uc:
        return True
    if uc == "coding" and "coder" in model_name:
        return True
    # Bilinen üç anahtar dışındaki filtre değerleri için ham alt-dize (geriye dönük uyum)
    return uc in model_uc


def _matches_filters(
    m: dict,
    query: str,
    provider: str,
    uc: str,
    is_moe: bool | None,
    min_ctx: int,
) -> bool:
    """Katalog filtrelerini tek model üzerinde değerlendirir (Sprint 33 CC)."""
    if query:
        name = (m.get("name") or "").lower()
        prov = (m.get("provider") or "").lower()
        if query not in name and query not in prov:
            return False
    if provider and (m.get("provider") or "").lower() != provider.lower():
        return False
    if uc and not _matches_use_case(m, uc):
        return False
    if is_moe is not None and bool(m.get("is_moe")) != is_moe:
        return False
    if min_ctx and (m.get("context_length") or 0) < min_ctx:
        return False
    return True


# Modül seviyesinde singleton (FastAPI endpoint'leri için)
_default_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    """Varsayılan kataloğu döndürür (dosya yoksa boş katalog — çökmez)."""
    global _default_catalog
    if _default_catalog is None:
        _default_catalog = Catalog()
    return _default_catalog


def providers() -> list[str]:
    """Katalogda fiilen bulunan provider'lar (sıralı, benzersiz)."""
    cat = get_catalog()
    seen: set[str] = set()
    for m in cat.models:
        p = (m.get("provider") or "").strip()
        if p:
            seen.add(p)
    return sorted(seen) if seen else KNOWN_PROVIDERS
