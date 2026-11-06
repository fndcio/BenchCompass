"""i18n ceviri katalogu (ADR-0009).

Backend kullanici mesajlari icin tek kaynak (DRY). Sifir bagimlilik (stdlib),
gettext/derleme adimi yok. Kullanimi:

    from api.i18n import _t

    msg = _t("llmfit_not_found", lang="tr")

Ceviri yalnizca KULLANICIYA donen metinler icindir (API error/message alanlari,
raporlar). Kod kimlikleri Ingilizce kalir; log mesajlari Turcce kalir.

Anahtar zinciri:
  - Exception'lar (LlmfitError/OllamaError) anahtar tasir -> ceviri kenarda
    (route/exception handler) _t() ile yapilir.
  - Tier etiketleri canonical degerini korur ("Tam Uyumlu" vb.), goruntuleme
    _t("tier.full", lang) ile cevrilir — web/app.js computeTier mirror'i bozulmaz.

Uyum: web/i18n.js (frontend). Ayni anahtar adlari iki tarafta da tutar (Y17/DRY).
"""

from __future__ import annotations

from typing import Any

# Anahtar -> {dil: metin}. {var} yer tutucular _t() icinde doldurulur.
CATALOG: dict[str, dict[str, str]] = {
    # --- Tier etiketleri (canonical; goruntuleme katmani) ---
    "tier.full": {
        "tr": "Tam Uyumlu",
        "en": "Fully Compatible",
    },
    "tier.border": {
        "tr": "Uyumlu (Sınırda)",
        "en": "Compatible (Borderline)",
    },
    "tier.caution": {
        "tr": "Dikkatli Kullan",
        "en": "Use with Caution",
    },
    "tier.notfit": {
        "tr": "Uygun Değil",
        "en": "Not Compatible",
    },
    # --- llmfit proxy hatalari (LlmfitError) ---
    "llmfit_not_found": {
        "tr": "llmfit bulunamadı. PATH'te olduğundan emin olun (scoop install llmfit veya cargo install llmfit).",
        "en": "llmfit not found. Make sure it is on your PATH (scoop install llmfit or cargo install llmfit).",
    },
    "llmfit_timeout": {
        "tr": "llmfit komutu {timeout} sn içinde yanıt vermedi (timeout).",
        "en": "llmfit command did not respond within {timeout} s (timeout).",
    },
    "llmfit_start_failed": {
        "tr": "llmfit başlatılamadı: {err}",
        "en": "llmfit could not be started: {err}",
    },
    "llmfit_exit_error": {
        "tr": "llmfit hatası: {msg}",
        "en": "llmfit error: {msg}",
    },
    "llmfit_empty_output": {
        "tr": "llmfit boş çıktı döndürdü.",
        "en": "llmfit returned empty output.",
    },
    "llmfit_invalid_json": {
        "tr": "llmfit çıktısı JSON değil: {err}",
        "en": "llmfit output is not valid JSON: {err}",
    },
    "llmfit_doctor_not_found": {
        "tr": "llmfit bulunamadi.",
        "en": "llmfit not found.",
    },
    "llmfit_doctor_timeout": {
        "tr": "llmfit doctor timeout",
        "en": "llmfit doctor timeout",
    },
    "llmfit_doctor_failed": {
        "tr": "llmfit doctor basarisiz",
        "en": "llmfit doctor failed",
    },
    "llmfit_doctor_empty": {
        "tr": "Bos rapor",
        "en": "Empty report",
    },
    # --- Ollama hatalari (OllamaError) ---
    "ollama_api_unreachable": {
        "tr": "Ollama API'ye erisilemiyor ({url}): {err}",
        "en": "Cannot reach Ollama API ({url}): {err}",
    },
    "ollama_bad_json": {
        "tr": "Ollama JSON yaniti bozuk: {err}",
        "en": "Malformed Ollama JSON response: {err}",
    },
    "ollama_post_failed": {
        "tr": "Ollama POST hatasi ({url}): {err}",
        "en": "Ollama POST error ({url}): {err}",
    },
    "ollama_stop_failed": {
        "tr": "ollama stop basarisiz: {stderr}",
        "en": "ollama stop failed: {stderr}",
    },
    "ollama_bench_failed": {
        "tr": "llmfit bench basarisiz: {stderr}",
        "en": "llmfit bench failed: {stderr}",
    },
    "ollama_bench_no_json": {
        "tr": "llmfit JSON ciktisi bulunamadi",
        "en": "llmfit JSON output not found",
    },
    "ollama_bench_bad_format": {
        "tr": "Beklenmeyen bench formati: {detail}",
        "en": "Unexpected bench format: {detail}",
    },
    "ollama_bench_timeout": {
        "tr": "llmfit bench timeout (60 sn)",
        "en": "llmfit bench timeout (60 s)",
    },
    "ollama_bench_parse": {
        "tr": "llmfit JSON parse hatasi: {err}",
        "en": "llmfit JSON parse error: {err}",
    },
    "ollama_cli_not_found": {
        "tr": "ollama CLI bulunamadi",
        "en": "ollama CLI not found",
    },
    "llmfit_cli_not_found": {
        "tr": "llmfit CLI bulunamadi",
        "en": "llmfit CLI not found",
    },
    # --- Benchmark ortak (community fallback) ---
    "bench_no_measurement": {
        "tr": "llmfit bench çalıştırılamadı ve bu model için community ölçümü bulunamadı. Dürüst sonuç: ölçüm yapılmadı.",
        "en": "llmfit bench could not be run and no community measurement exists for this model. Honest result: no measurement taken.",
    },
    # --- Ollama run ---
    "ollama_run_started": {
        "tr": "ollama run baslatildi",
        "en": "ollama run started",
    },
    "ollama_run_bg": {
        "tr": "ollama run arkaplanda calisiyor",
        "en": "ollama run running in background",
    },
    # --- HTTPException / 404 ---
    "dashboard_html_missing": {
        "tr": "Dashboard HTML bulunamadi (web/index.html yok)",
        "en": "Dashboard HTML not found (web/index.html missing)",
    },
    "hardware_profile_missing": {
        "tr": "config/hardware_profile.json bulunamadi",
        "en": "config/hardware_profile.json not found",
    },
    "task_not_found": {
        "tr": "task not found",
        "en": "task not found",
    },
}

DEFAULT_LANG = "tr"
SUPPORTED_LANGS = ("tr", "en")


def _t(key: str, lang: str = DEFAULT_LANG, **fmt: Any) -> str:
    """Anahtar-bazli ceviri. Bilinmeyen anahtar TR'ye duser, o da yoksa
    anahtarin kendisini dondurur (anahtar sizintisini onler)."""
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    entry = CATALOG.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    for k, v in fmt.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def supported_langs() -> list[str]:
    return list(SUPPORTED_LANGS)


def detect_lang(header: str | None = None, query: str | None = None) -> str:
    """Istek dilini belirler: ?lang= -> Accept-Language -> 'tr'."""
    if query and query in SUPPORTED_LANGS:
        return query
    if header:
        first = (header or "").split(",")[0].strip().lower()
        base = first.split("-")[0]
        if base in SUPPORTED_LANGS:
            return base
    return DEFAULT_LANG
