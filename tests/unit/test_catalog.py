"""
Unit tests — api/catalog.py (Sprint 19 yerel model kataloğu)
==========================================================================
hf_models.json'dan yükleme, arama, filtreleme ve ModelRecord eşlemesi.
Gerçek data/ dosyasına dokunulmaz — tmp izole katalog kullanılır (AGENTS.md §6).
"""

from __future__ import annotations

import json

import pytest

from api import catalog


@pytest.fixture()
def sample_catalog(tmp_path):
    """İzole küçük katalog — gerçek data/hf_models.json'a dokunmaz."""
    models = [
        {
            "name": "Qwen/Qwen3-Coder-7B-Instruct-GGUF",
            "provider": "qwen",
            "parameter_count": "7B",
            "parameters_raw": 7_000_000_000,
            "min_ram_gb": 8.0,
            "recommended_ram_gb": 16.0,
            "min_vram_gb": 6.0,
            "quantization": "Q4_K_M",
            "format": "gguf",
            "context_length": 32768,
            "use_case": "Code generation and completion",
            "capabilities": ["tool_use"],
            "is_moe": False,
            "hf_downloads": 1000,
            "hf_likes": 50,
            "gguf_sources": [
                {"repo": "Qwen/Qwen3-Coder-7B-Instruct-GGUF", "provider": "hf"}
            ],
        },
        {
            "name": "Qwen/Qwen3-MoE-30B-A3B",
            "provider": "qwen",
            "parameter_count": "30B",
            "parameters_raw": 30_000_000_000,
            "min_ram_gb": 24.0,
            "recommended_ram_gb": 48.0,
            "min_vram_gb": 18.0,
            "quantization": "Q4_K_M",
            "format": "gguf",
            "context_length": 65536,
            "use_case": "General purpose",
            "capabilities": [],
            "is_moe": True,
            "num_experts": 64,
            "active_experts": 8,
            "active_parameters": 3_000_000_000,
            "hf_downloads": 500,
            "hf_likes": 10,
        },
        {
            "name": "meta-llama/Llama-3.2-1B-Instruct",
            "provider": "meta",
            "parameter_count": "1B",
            "parameters_raw": 1_000_000_000,
            "min_ram_gb": 2.0,
            "recommended_ram_gb": 4.0,
            "min_vram_gb": 1.0,
            "quantization": "Q4_K_M",
            "format": "gguf",
            "context_length": 8192,
            "use_case": "Instruction following, chat",
            "capabilities": [],
            "is_moe": False,
            "hf_downloads": 5000,
            "hf_likes": 200,
        },
    ]
    path = tmp_path / "hf_models.json"
    path.write_text(json.dumps(models), encoding="utf-8")
    return path


@pytest.fixture()
def cat(sample_catalog):
    """sample_catalog üzerinden yüklenmiş Catalog."""
    return catalog.Catalog(sample_catalog)


# ---------------------------------------------------------------------------
# Yükleme
# ---------------------------------------------------------------------------
def test_load_record_count(cat):
    """Katalog 3 kayıt yükler."""
    assert len(cat.models) == 3


def test_load_missing_file(tmp_path):
    """Dosya yoksa boş katalog döner (çökmez)."""
    c = catalog.Catalog(tmp_path / "yok.json")
    assert c.models == []
    assert c.loaded is False


# ---------------------------------------------------------------------------
# Arama
# ---------------------------------------------------------------------------
def test_search_by_name_substring(cat):
    """q ile ad alt-dizesi aranır."""
    res = cat.search(q="qwen")
    assert len(res) == 2
    assert all("qwen" in m["name"].lower() for m in res)


def test_search_empty_query_returns_all(cat):
    """q boşsa tüm kayıtlar döner."""
    res = cat.search(q="")
    assert len(res) == 3


def test_search_no_match(cat):
    """Eşleşme yoksa boş liste."""
    assert cat.search(q="olmayan-model") == []


# ---------------------------------------------------------------------------
# Filtreleme
# ---------------------------------------------------------------------------
def test_filter_provider(cat):
    res = cat.search(provider="qwen")
    assert len(res) == 2
    assert all(m["provider"] == "qwen" for m in res)


def test_filter_is_moe(cat):
    res = cat.search(is_moe=True)
    assert len(res) == 1
    assert res[0]["is_moe"] is True


def test_filter_min_ctx(cat):
    res = cat.search(min_ctx=32768)
    assert len(res) == 2
    assert all(m["context_length"] >= 32768 for m in res)


def test_filter_use_case_substring(cat):
    res = cat.search(use_case="code")
    assert len(res) == 1
    assert "Code generation" in res[0]["use_case"]


# ---------------------------------------------------------------------------
# use_case tek kaynak (T5 — DRY, denetim turu 2)
# ---------------------------------------------------------------------------
class TestUseCaseTekKaynak:
    """T5: use_case anahtar eşlemesi tek kaynak — `api.catalog.use_case_key`.

    Katalog filtresi ve aile skoru zenginleştirme (routes/shared) aynı eşlemeyi
    paylaşır; anahtar setleri birbirinden sapamaz (Y27 ruhu: tek formül tek yerde).
    """

    def test_kanonik_esleme(self):
        assert catalog.use_case_key("Code generation and completion") == "coding"
        assert (
            catalog.use_case_key("Advanced reasoning, chain-of-thought") == "reasoning"
        )
        assert catalog.use_case_key("Instruction following, chat") == "chat"
        # "General purpose" bilinçli olarak None (test_api.py:1026 sözleşmesi korunur)
        assert catalog.use_case_key("General purpose") is None

    def test_shared_ayni_kaynagi_kullaniyor(self):
        from api.routes.shared import _use_case_key

        for text in (
            "Code generation",
            "Advanced reasoning",
            "Instruction following, chat",
            "General purpose",
        ):
            assert _use_case_key(text) == catalog.use_case_key(text)

    def test_matches_use_case_anahtarlarla(self):
        m_reason = {"name": "x", "use_case": "Advanced reasoning"}
        assert catalog._matches_use_case(m_reason, "reasoning") is True
        assert catalog._matches_use_case(m_reason, "chat") is False

    def test_matches_use_case_coder_isim_kurali(self):
        """İsimde "coder" varsa coding filtresine girer (katalog ek kuralı)."""
        m = {"name": "Qwen/Qwen-Coder-Base", "use_case": "General purpose"}
        assert catalog._matches_use_case(m, "coding") is True
        # "general" T5 ile artık chat'e eşlenmiyor — dar kanonik bilinçli seçim
        assert catalog._matches_use_case(m, "chat") is False

    def test_matches_use_case_bilinmeyen_anahtar_alt_dize(self):
        m = {"name": "x", "use_case": "Code generation and completion"}
        assert catalog._matches_use_case(m, "code") is True  # ham alt-dize yolu


def test_limit(cat):
    res = cat.search(q="", limit=2)
    assert len(res) == 2


# ---------------------------------------------------------------------------
# ModelRecord eşlemesi (G5)
# ---------------------------------------------------------------------------
def test_to_model_record_mapping(cat):
    """Katalog alanları ModelRecord alanlarına eşlenir (min_vram→required_vram vb.)."""
    rec = cat.to_model_record(cat.models[0])
    assert rec.name == "Qwen/Qwen3-Coder-7B-Instruct-GGUF"
    assert rec.required_vram_gb == 6.0  # min_vram_gb
    assert rec.required_ram_gb == 8.0  # min_ram_gb
    assert rec.context_window == 32768  # context_length
    assert rec.quantization == "Q4_K_M"
    assert rec.is_moe is False
    assert rec.provider == "qwen"


def test_to_model_record_moe(cat):
    """MoE kaydı aktif/toplam parametre eşlenir."""
    rec = cat.to_model_record(cat.models[1])
    assert rec.is_moe is True
    assert rec.total_params_b == pytest.approx(30.0)
    assert rec.active_params_b == pytest.approx(3.0)


def test_to_model_record_gguf_source_repo(cat):
    """gguf_sources varsa ilk repo bilgisi kaydedilir."""
    rec = cat.to_model_record(cat.models[0])
    assert rec.notes is not None
    assert "Qwen/Qwen3-Coder-7B-Instruct-GGUF" in str(rec.notes)


def test_to_model_record_family_fit_score(cat, monkeypatch, tmp_path):
    """Sprint 21: use_case aile verisi fit_score'u güçlendirir."""
    import json

    from api import fit_scores as fs_mod

    uc_data = {
        "families": [
            {
                "match": ["qwen3-coder"],
                "scores": {"coding": 90, "reasoning": 78, "chat": 72},
            },
        ]
    }
    path = tmp_path / "uc.json"
    path.write_text(json.dumps(uc_data), encoding="utf-8")
    fake = fs_mod.FitScores(usecase_path=path, baseline_path=tmp_path / "yok.json")
    monkeypatch.setattr(fs_mod, "get_fit", lambda: fake)

    rec = cat.to_model_record(
        cat.models[0]
    )  # Qwen/Qwen3-Coder-7B, use_case "Code generation"

    assert rec.fit_score == 90
    assert rec.required_vram_gb == 6.0


def test_to_model_record_family_no_match_fit_zero(cat, monkeypatch, tmp_path):
    """Sprint 21: aile eşleşmezse fit_score 0 kalır (çökmez)."""
    import json

    from api import fit_scores as fs_mod

    uc_data = {"families": [{"match": ["olmayan"], "scores": {"coding": 50}}]}
    path = tmp_path / "uc.json"
    path.write_text(json.dumps(uc_data), encoding="utf-8")
    fake = fs_mod.FitScores(usecase_path=path, baseline_path=tmp_path / "yok.json")
    monkeypatch.setattr(fs_mod, "get_fit", lambda: fake)

    rec = cat.to_model_record(cat.models[1])  # Qwen3-MoE, use_case "General purpose"
    assert rec.fit_score == 0.0
