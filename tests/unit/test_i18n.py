"""
Unit testler — api/i18n.py (çeviri kataloğu, ADR-0009)
==========================================================================
Çeviri katmanının davranışı: TR/EN çeviri, fallback, parametre doldurma,
dil tespiti. Backend kullanıcı mesajlarının tek kaynağı (DRY/Y18).

Test piramidi katman 1 (unit): saf fonksiyon testi, DB/network yok.
"""

from __future__ import annotations

from api.i18n import (
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    CATALOG,
    _t,
    detect_lang,
    supported_langs,
)


class TestT:
    """_t() çeviri fonksiyonu."""

    def test_tr_default(self):
        assert _t("tier.full") == "Tam Uyumlu"

    def test_en(self):
        assert _t("tier.full", lang="en") == "Fully Compatible"

    def test_unknown_lang_falls_back_to_tr(self):
        assert _t("tier.full", lang="fr") == "Tam Uyumlu"

    def test_missing_key_returns_key(self):
        assert _t("__missing_key__") == "__missing_key__"

    def test_params_interpolation(self):
        msg = _t("llmfit_timeout", lang="tr", timeout=60)
        assert msg == "llmfit komutu 60 sn içinde yanıt vermedi (timeout)."

    def test_en_has_same_keys_as_tr(self):
        """Y18: EN kataloğu TR kataloğunun tüm anahtarlarını içermeli."""
        missing = [k for k in CATALOG if "en" not in CATALOG[k]]
        assert missing == []


class TestDetectLang:
    """İstek dil tespiti."""

    def test_query_wins(self):
        assert detect_lang(query="en") == "en"

    def test_accept_language(self):
        assert detect_lang(header="en-US,en;q=0.9") == "en"

    def test_default_tr_when_nothing(self):
        assert detect_lang() == DEFAULT_LANG

    def test_unsupported_lang_falls_back(self):
        assert detect_lang(query="fr") == DEFAULT_LANG


class TestSupport:
    """Desteklenen diller."""

    def test_supported_langs(self):
        langs = supported_langs()
        assert langs == ["tr", "en"]

    def test_supported_constants(self):
        assert "tr" in SUPPORTED_LANGS
        assert "en" in SUPPORTED_LANGS
