"""
Unit testler — benchmark_collector.normalize()
==========================================================================
llmfit yanıtını benchmark_models satır dict'lerine dönüştürme.

AGENTS.md §6 TDD: refactor öncesi davranışı sabitle (karakterizasyon testi).
Bu testler normalize()'in çıktısını dondur — refactor sonrası aynı kalmalı.
"""

from __future__ import annotations

import pytest

from benchmark_collector import _insert_models, normalize


# =============================================================================
# Temel dönüşüm
# =============================================================================
class TestNormalizeBasic:
    def test_empty_list_returns_empty(self):
        """Boş liste → boş çıkış."""
        assert normalize([], "all") == []

    def test_dict_with_models_key(self):
        """{'models': [...]} → liste normalize edilir."""
        data = {"models": [{"name": "test"}]}
        result = normalize(data, "all")
        assert len(result) == 1
        assert result[0]["name"] == "test"

    def test_list_passthrough(self):
        """Liste girdisi direkt normalize edilir."""
        data = [{"name": "m1"}, {"name": "m2"}]
        result = normalize(data, "all")
        assert len(result) == 2

    def test_unknown_name_fallback(self):
        """name yoksa 'model' alanına, o da yoksa 'Unknown'a düşer."""
        result = normalize([{"model": "from-model"}], "all")
        assert result[0]["name"] == "from-model"

        result = normalize([{}], "all")
        assert result[0]["name"] == "Unknown"


# =============================================================================
# llmfit first-class alanları
# =============================================================================
class TestNormalizeFirstClassFields:
    def test_params_b_direct(self):
        """llmfit params_b first-class alanı direkt kullanılır."""
        data = [{"name": "m", "params_b": 14.0}]
        result = normalize(data, "all")
        assert result[0]["param_count_b"] == pytest.approx(14.0)

    def test_parameter_count_string_parsing(self):
        """String '14.8B' formatı parse edilir."""
        data = [{"name": "m", "parameter_count": "14.8B"}]
        result = normalize(data, "all")
        assert result[0]["param_count_b"] == pytest.approx(14.8)

    def test_memory_required_gb_becomes_vram(self):
        """memory_required_gb → required_vram_gb (run_mode=GPU ise)."""
        data = [{"name": "m", "memory_required_gb": 8.5}]
        result = normalize(data, "all")
        assert result[0]["required_vram_gb"] == pytest.approx(8.5)

    def test_estimated_tps_becomes_speed(self):
        data = [{"name": "m", "estimated_tps": 45.2}]
        result = normalize(data, "all")
        assert result[0]["estimated_speed_tok_s"] == pytest.approx(45.2)

    def test_context_length_fields(self):
        data = [
            {
                "name": "m",
                "context_length": 32768,
                "effective_context_length": 8192,
            }
        ]
        result = normalize(data, "all")
        assert result[0]["context_length_supported"] == 32768
        assert result[0]["context_length_estimated_at"] == 8192

    def test_best_quant(self):
        data = [{"name": "m", "best_quant": "Q4_K_M"}]
        result = normalize(data, "all")
        assert result[0]["quantization"] == "Q4_K_M"

    def test_sprint7_new_fields(self):
        """Sprint 7: fit_level, is_moe, capabilities, disk_size_gb, llmfit_score."""
        data = [
            {
                "name": "m",
                "fit_level": "Perfect",
                "is_moe": True,
                "capabilities": ["chat", "vision"],
                "disk_size_gb": 5.2,
                "score": 95.5,
            }
        ]
        result = normalize(data, "all")
        row = result[0]
        assert row["fit_level"] == "Perfect"
        assert row["is_moe"] is True
        assert row["capabilities"] == "chat,vision"
        assert row["disk_size_gb"] == pytest.approx(5.2)
        assert row["llmfit_score"] == pytest.approx(95.5)

    def test_run_mode_passthrough(self):
        """Sprint 12: run_mode direkt geçirilir."""
        data = [{"name": "m", "run_mode": "cpu_offload"}]
        result = normalize(data, "all")
        assert result[0]["run_mode"] == "cpu_offload"


# =============================================================================
# _insert_models — DB'ye yazma (run_mode kaybi regresyonu)
# =============================================================================
class TestInsertModelsPersistsRunMode:
    """llmfit 1.1.16 doneminde: normalize() run_mode uretiyordu ama INSERT
    listesinde olmadigi icin DB'ye hic yazilmazdi (0/50 dolu). Tier motoru
    (api/compat.py compute_tier) run_mode okudugu icin bu sessiz veri kaybi
    onemlidir. Test, tam yazma zincirini izole DB uzerinde dogrular.
    """

    @staticmethod
    def _isolated_con(tmp_root, monkeypatch):
        import api.db as dbmod

        monkeypatch.setattr(dbmod, "DB", tmp_root / "benchmark_history.db")
        return dbmod.connect()

    def test_run_mode_reaches_db(self, tmp_root, monkeypatch):
        """run_mode INSERT ediliyor (CPU+GPU dahil llmfit 1.1.16 bicimi)."""
        con = self._isolated_con(tmp_root, monkeypatch)
        cur = con.execute(
            "INSERT INTO benchmark_runs(name,source,use_case) VALUES('t','test','all')"
        )
        run_id = cur.lastrowid
        models = normalize(
            [{"name": "m", "run_mode": "CPU+GPU", "memory_required_gb": 10.0}],
            "all",
        )
        _insert_models(con, run_id, models)
        row = con.execute(
            "SELECT run_mode, fit_level FROM benchmark_models WHERE run_id=?",
            (run_id,),
        ).fetchone()
        con.close()
        assert row["run_mode"] == "CPU+GPU"

    def test_all_llmfit_fields_persisted(self, tmp_root, monkeypatch):
        """Sprint 7 first-class alanlarinin tamami DB'ye yazilir."""
        con = self._isolated_con(tmp_root, monkeypatch)
        cur = con.execute(
            "INSERT INTO benchmark_runs(name,source,use_case) VALUES('t','test','all')"
        )
        run_id = cur.lastrowid
        models = normalize(
            [
                {
                    "name": "m",
                    "params_b": 27.0,
                    "memory_required_gb": 10.0,
                    "estimated_tps": 45.3,
                    "fit_level": "Perfect",
                    "is_moe": True,
                    "capabilities": "chat,tool_use",
                    "disk_size_gb": 5.95,
                    "score": 97.9,
                    "run_mode": "GPU",
                }
            ],
            "all",
        )
        _insert_models(con, run_id, models)
        row = con.execute(
            """SELECT fit_level, is_moe, capabilities, disk_size_gb, llmfit_score,
                      run_mode, estimated_speed_tok_s, param_count_b
               FROM benchmark_models WHERE run_id=?""",
            (run_id,),
        ).fetchone()
        con.close()
        assert row["fit_level"] == "Perfect"
        assert row["is_moe"] == 1
        assert row["capabilities"] == "chat,tool_use"
        assert row["disk_size_gb"] == pytest.approx(5.95)
        assert row["llmfit_score"] == pytest.approx(97.9)
        assert row["run_mode"] == "GPU"
        assert row["estimated_speed_tok_s"] == pytest.approx(45.3)
        assert row["param_count_b"] == pytest.approx(27.0)

    def test_run_mode_null_stays_null(self, tmp_root, monkeypatch):
        """llmfit run_mode vermiyorsa NULL yazilir (COALESCE ile sahte deger yok)."""
        con = self._isolated_con(tmp_root, monkeypatch)
        cur = con.execute(
            "INSERT INTO benchmark_runs(name,source,use_case) VALUES('t','test','all')"
        )
        run_id = cur.lastrowid
        _insert_models(con, run_id, normalize([{"name": "m"}], "all"))
        row = con.execute(
            "SELECT run_mode FROM benchmark_models WHERE run_id=?", (run_id,)
        ).fetchone()
        con.close()
        assert row["run_mode"] is None


# =============================================================================
# RAM tahmini (VRAM yoksa)
# =============================================================================
class TestNormalizeRamEstimation:
    def test_ram_estimated_from_vram(self):
        """required_ram verilmemişse VRAM * 1.15 tahmin edilir."""
        data = [{"name": "m", "memory_required_gb": 10.0}]
        result = normalize(data, "all")
        assert result[0]["required_ram_gb"] == pytest.approx(11.5)


# =============================================================================
# Resilience — tek model patlarsa gerisi devam eder
# =============================================================================
class TestNormalizeResilience:
    def test_bad_model_skipped_others_continue(self):
        """AGENTS.md resilience: bir model patlarsa atlanır, gerisi devam eder."""
        data = [
            {"name": "good-model", "params_b": 7.0},
            {"name": "will-crash"},  # bu patlamalı
            {"name": "also-good", "params_b": 14.0},
        ]
        result = normalize(data, "all")
        # En az 2 model işlendi (bad olan atlandı)
        names = [r["name"] for r in result]
        assert "good-model" in names
        assert "also-good" in names

    def test_notes_fallback_when_no_first_class(self):
        """First-class alan yoksa notes regex devreye girer."""
        data = [
            {"name": "Qwen2.5-7B", "notes": "Need 5.0 GB VRAM or 6.0 GB system RAM"}
        ]
        result = normalize(data, "all")
        assert result[0]["required_vram_gb"] == pytest.approx(5.0)
        assert result[0]["required_ram_gb"] == pytest.approx(6.0)
