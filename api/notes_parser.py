"""llmfit 'notes' metninden yapilsal alan cikarma.

llmfit CLI'si uyumlulukla ilgili tum bilgiyi serbest metin (JSON array ya da
satir listesi) olarak döndürür. Ornek gercek cikti (benchmark_history.db):

    ["Context capped at 8192 tokens for estimation (model supports up to 32768; ...)",
     "Insufficient VRAM and system RAM",
     "Need 7.6 GB VRAM or 8.3 GB system RAM",
     "Baseline estimated speed: 66.7 tok/s"]

ya da (uyumlu modellerde):

    ["Context capped at 8192 tokens for estimation (model supports up to 32768; ...)",
     "GPU: model loaded into VRAM",
     "Best quantization for hardware: Q8_0 (model default: Q4_K_M)",
     "Baseline estimated speed: 64.7 tok/s"]

Bu modul, metni tutarli sekilde sayisal alanlara donusturur. Hatalar asla
yukari firlatilmaz: parse basarisiz olursa ilgili alan None kalir. Bu
Bolum 9'daki dayaniklilik kriterini karsilar ("bir model parse edilemezse
tum snapshot'i dusurmek yerine o modeli 'eksik veri' olarak isaretle").
"""

from __future__ import annotations

import re
from typing import Any

# --- Regex sablonlari -------------------------------------------------------
# Hepsi case-insensitive. Gercek DB satirlarina gore test edilmistir.

# "Need 7.6 GB VRAM or 8.3 GB system RAM"
# Eger model uyumluysa bu satir YOKTUR → None doner, tier formulu "loaded into
# VRAM" ipucuna guvenir (compat.py icerisinde).
RE_NEED_VRAM_RAM = re.compile(
    r"need\s+([\d.]+)\s*gb\s+vram\s+or\s+([\d.]+)\s*gb\s+system\s+ram",
    re.IGNORECASE,
)

# Örnek: "Context capped at 8192 ... (supports up to 32768)"  # noqa: ERA001
# Grup 1 = estimated, Grup 2 = supported
RE_CONTEXT = re.compile(
    r"capped\s+at\s+(\d+)\s*tokens?\s+for\s+estimation"
    r".*?supports?\s+up\s+to\s+(\d+)",
    re.IGNORECASE | re.DOTALL,
)
# Bazen sadece "supports up to N" yok, sadece cap var:
RE_CONTEXT_EST_ONLY = re.compile(r"capped\s+at\s+(\d+)\s*tokens?", re.IGNORECASE)
RE_CONTEXT_SUPPORTED_ONLY = re.compile(
    r"supports?\s+up\s+to\s+(\d+)\s*tokens?", re.IGNORECASE
)

# Örnek: "Best quantization for hardware: Q8_0 (model default: Q4_K_M)"  # noqa: ERA001
RE_QUANT_HW = re.compile(
    r"best\s+quantization\s+for\s+hardware:\s*([A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)

# Örnek: "Baseline estimated speed: 66.7 tok/s"  # noqa: ERA001
RE_SPEED = re.compile(
    r"(?:baseline\s+)?estimated\s+speed:\s*([\d.]+)\s*tok/s",
    re.IGNORECASE,
)

# Model adindan parametre sayisi: "Qwen2.5-Coder-14B-Instruct" -> 14
# 0.5B, 1.5B, 3B, 7B, 8B, 11B, 13B, 14B, 70B, 405B, vb.
RE_PARAM_FROM_NAME = re.compile(r"[-_/](\d+(?:\.\d+)?)B\b", re.IGNORECASE)

# Model adindan quantizasyon (notes'ta yoksa): AWQ, GPTQ-Int4, bnb-4bit, FP8, NVFP4
# Duzen: suffix veya parca olarak gecer.
RE_QUANT_FROM_NAME = re.compile(
    r"\b(AWQ|GPTQ-Int4|GPTQ|FP8|NVFP4|bnb-4bit|bnb-8bit|4bit|8bit|Q[0-9]_[A-Z]|Q[0-9]_K_[A-Z])\b",
    re.IGNORECASE,
)

# GPU'ya sigdi ipucu (uyumlu modeller)
RE_LOADED_INTO_VRAM = re.compile(r"loaded\s+into\s+vram", re.IGNORECASE)
# Acikca yetersiz ipucu
RE_INSUFFICIENT = re.compile(r"insufficient\s+vram", re.IGNORECASE)


def _flatten_notes(notes: object) -> str:
    """notes alanini tek bir kucuk-harfli metne donusturur.

    - list/dict -> json.dumps
    - str       -> oldugu gibi
    - None      -> ""
    """
    if notes is None:
        return ""
    if isinstance(notes, (list, dict)):
        import json

        return json.dumps(notes, ensure_ascii=False)
    return str(notes)


def _safe_float(match: re.Match | None, group: int) -> float | None:
    """Regex eşleşmesinden float çıkarır; hatada None (asla fırlatmaz)."""
    if match is None:
        return None
    try:
        return float(match.group(group))
    except Exception:  # noqa: BLE001 — bozuk notes asla fırlatma
        return None


def _parse_need_vram_ram(text: str) -> tuple[float | None, float | None]:
    """'Need VRAM: XGB, RAM: YGB' deseninden (vram, ram) çifti."""
    try:
        m = RE_NEED_VRAM_RAM.search(text)
        if m:
            return _safe_float(m, 1), _safe_float(m, 2)
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _parse_context(text: str) -> tuple[int | None, int | None]:
    """Context deseninden (estimated_at, supported) çifti."""
    try:
        mc = RE_CONTEXT.search(text)
        if mc:
            return int(mc.group(1)), int(mc.group(2))
        me = RE_CONTEXT_EST_ONLY.search(text)
        ms = RE_CONTEXT_SUPPORTED_ONLY.search(text)
        return (
            int(me.group(1)) if me else None,
            int(ms.group(1)) if ms else None,
        )
    except Exception:  # noqa: BLE001
        return None, None


def _parse_quant_from_text(text: str) -> str | None:
    """Metinden quantizasyon (Q4_K_M vb.) çıkarır."""
    try:
        m = RE_QUANT_HW.search(text)
        if m:
            return m.group(1).upper()
    except Exception:  # noqa: BLE001
        pass
    return None


def _parse_speed(text: str) -> float | None:
    """Metinden tahmini hız (tok/s) çıkarır."""
    return _safe_float(RE_SPEED.search(text), 1)


def parse_notes(notes: object, model_name: str | None = None) -> dict:
    """Tek bir modelin 'notes' alanini yapilsal alanlara donusturur.

    Donus sozlugu (None = "bu alan cikarilamadi"):
        required_vram_gb          : float | None
        required_ram_gb           : float | None
        context_length_estimated_at: int | None   (cap, ornek 8192)
        context_length_supported  : int | None    (model limiti, ornek 32768)
        quantization              : str | None    (ornek "Q8_0")
        estimated_speed_tok_s     : float | None
        loaded_into_vram          : bool          (GPU'ya sigdi ipucu)
        insufficient              : bool          (acik yetersiz ipucu)

    Bu fonksiyon HICBIR zaman firlatma yapmaz. Bozuk notes gelirse bos dict
    degil, tum degerleri None/False olan bir dict doner.
    """
    out: dict[str, Any] = {
        "required_vram_gb": None,
        "required_ram_gb": None,
        "context_length_estimated_at": None,
        "context_length_supported": None,
        "quantization": None,
        "estimated_speed_tok_s": None,
        "loaded_into_vram": False,
        "insufficient": False,
    }
    try:
        text = _flatten_notes(notes)
    except Exception:  # noqa: BLE001
        text = ""

    if text:
        out["required_vram_gb"], out["required_ram_gb"] = _parse_need_vram_ram(text)
        out["context_length_estimated_at"], out["context_length_supported"] = (
            _parse_context(text)
        )
        out["quantization"] = _parse_quant_from_text(text)
        out["estimated_speed_tok_s"] = _parse_speed(text)
        out["loaded_into_vram"] = bool(RE_LOADED_INTO_VRAM.search(text))
        out["insufficient"] = bool(RE_INSUFFICIENT.search(text))

    # Notes'ta quant yoksa model adindan cikarmaya calis
    if out["quantization"] is None and model_name:
        try:
            mn = RE_QUANT_FROM_NAME.search(model_name)
            if mn:
                out["quantization"] = mn.group(1).upper()
        except Exception:  # noqa: BLE001
            pass

    return out


def extract_param_count(model_name: str | None) -> float | None:
    """Model adindan parametre sayisini cikarir (milyar parametre).

    Ornekler:
        "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ" -> 14.0
        "meta-llama/Llama-3.2-11B-Vision"     -> 11.0
        "unsloth/gemma-4-E4B-it"              -> 4.0
        "Qwen/Qwen2.5-7B"                     -> 7.0

    Hicbiri eslesmezse None. Firlatma yapmaz.
    """
    if not model_name:
        return None
    try:
        # Bas suffix'leri once yakala; birden fazla eslesirse ilkini al
        # (model adinda genelde tek parametre geceri).
        m = RE_PARAM_FROM_NAME.search("/" + model_name)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def enrich_model(model_name: str, notes: object) -> dict:
    """parse_notes + extract_param_count'u birlestirip tek sozluk verir.

    Collector ve backfill icin ortak kullanilan yardimcidir. Donus:
        {
            "required_vram_gb": ..., "required_ram_gb": ...,
            "context_length_supported": ..., "context_length_estimated_at": ...,
            "quantization": ..., "param_count_b": ...,
            "estimated_speed_tok_s": ...,
            "loaded_into_vram": bool, "insufficient": bool
        }
    """
    parsed = parse_notes(notes, model_name)
    parsed["param_count_b"] = extract_param_count(model_name)
    moe = parse_moe_info(model_name, notes)
    parsed.update(moe)
    return parsed


def parse_moe_info(model_name: str = "", notes: object = None) -> dict:
    """Model adindan veya notlardan MoE (Mixture-of-Experts) mimarisini ve
    aktif/toplam parametre ayrimini tespit eder (Sprint 08).
    """
    raw_str = (str(model_name or "") + " " + str(notes or "")).lower()

    # 8x7B (Mixtral 8x7b) -> total 47B, active 13B
    if "8x7b" in raw_str:
        return {"is_moe": True, "active_params_b": 13.0, "total_params_b": 47.0}
    # 8x22B (Mixtral 8x22b) -> total 141B, active 39B
    if "8x22b" in raw_str:
        return {"is_moe": True, "active_params_b": 39.0, "total_params_b": 141.0}
    # Geneltilmis MoE veya Mixtral/DeepSeek MoE
    if "moe" in raw_str or "mixtral" in raw_str:
        return {"is_moe": True, "active_params_b": 13.0, "total_params_b": 47.0}

    return {"is_moe": False, "active_params_b": None, "total_params_b": None}
