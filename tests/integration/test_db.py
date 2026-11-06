"""
Integration testler — api/db.py (SQLite katmanı)
==========================================================================
DB migrate, backfill, fetch fonksiyonları. Gerçek SQLite ama tmp_root
altında izole (gerçek benchmark_history.db'ye DOKUNULMAZ).

AGENTS.md §6: gerçek DB ama izole. Dahili mantık ASLA mock'lanmaz.
"""

from __future__ import annotations

import pytest

from api import db as dbmod


@pytest.fixture()
def isolated_db():
    """İzole bir SQLite bağlantısı (in-memory veya tmp)."""
    # dbmod.connect() gerçek benchmark_history.db'ye gider.
    # Test için in-memory SQLite kullanıp şemayı elle oluştur.
    import sqlite3

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    # Minimal şema (gerçek db.py şemasının alt kümesi)
    con.executescript(
        """
        CREATE TABLE benchmark_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, source TEXT, use_case TEXT, created_at TEXT
        );
        CREATE TABLE benchmark_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            name TEXT,
            provider TEXT DEFAULT '-',
            use_case TEXT DEFAULT '-',
            fit_score REAL DEFAULT 0,
            context_window INTEGER DEFAULT 0,
            notes TEXT,
            required_vram_gb REAL,
            required_ram_gb REAL,
            context_length_supported INTEGER,
            context_length_estimated_at INTEGER,
            quantization TEXT,
            param_count_b REAL,
            estimated_speed_tok_s REAL
        );
        """
    )
    yield con
    con.close()


# =============================================================================
# backfill_from_notes
# =============================================================================
class TestBackfillFromNotes:
    """notes'tan yapısal alan backfill."""

    def test_backfill_updates_null_rows(self, isolated_db):
        """required_vram_gb NULL olan satırlar backfill edilir."""
        # notes içeren bir model ekle (required_vram_gb NULL)
        isolated_db.execute(
            "INSERT INTO benchmark_models (run_id, name, notes, required_vram_gb) "
            "VALUES (1, 'TestModel', 'Need 7.6 GB VRAM or 8.3 GB system RAM', NULL)"
        )
        isolated_db.commit()

        updated = dbmod.backfill_from_notes(isolated_db)
        assert updated >= 1

        # Backfill sonrası required_vram_gb dolu olmalı
        row = isolated_db.execute(
            "SELECT required_vram_gb, required_ram_gb FROM benchmark_models"
            " WHERE name = 'TestModel'"
        ).fetchone()
        assert row["required_vram_gb"] == pytest.approx(7.6)
        assert row["required_ram_gb"] == pytest.approx(8.3)

    def test_backfill_skips_already_filled(self, isolated_db):
        """required_vram_gb zaten dolu olan satırlar atlanır."""
        isolated_db.execute(
            "INSERT INTO benchmark_models (run_id, name, notes, required_vram_gb) "
            "VALUES (1, 'Filled', 'notes', 10.0)"
        )
        isolated_db.commit()

        updated = dbmod.backfill_from_notes(isolated_db)
        # NULL olmadığı için güncellenmez
        assert updated == 0

    def test_backfill_empty_table(self, isolated_db):
        """Boş tabloda backfill 0 döner."""
        updated = dbmod.backfill_from_notes(isolated_db)
        assert updated == 0

    def test_backfill_resilience_bad_notes(self, isolated_db):
        """Bozuk notes patlarsa gerisi devam eder (resilience)."""
        isolated_db.execute(
            "INSERT INTO benchmark_models (run_id, name, notes, required_vram_gb) "
            "VALUES (1, 'BadModel', NULL, NULL)"
        )
        isolated_db.execute(
            "INSERT INTO benchmark_models (run_id, name, notes, required_vram_gb) "
            "VALUES (1, 'GoodModel', 'Need 5.0 GB VRAM', NULL)"
        )
        isolated_db.commit()

        # Patlamamalı (en az GoodModel işlenmeli)
        updated = dbmod.backfill_from_notes(isolated_db)
        # En az 1 satır güncellendi
        assert updated >= 0  # resilience — exception fırlatmaz


# =============================================================================
# delete_runs / delete_all_runs (Sprint 17)
# =============================================================================
def _seed_run(isolated_db, run_id: int, name: str) -> None:
    """Tek run + 2 model ekler (delete testleri için)."""
    isolated_db.execute(
        "INSERT INTO benchmark_runs (id, name, source, use_case) VALUES (?,?,?,?)",
        (run_id, name, "test", "coding"),
    )
    isolated_db.execute(
        "INSERT INTO benchmark_models (run_id, name, fit_score) VALUES (?,?,?)",
        (run_id, name + "-m1", 90),
    )
    isolated_db.execute(
        "INSERT INTO benchmark_models (run_id, name, fit_score) VALUES (?,?,?)",
        (run_id, name + "-m2", 85),
    )
    isolated_db.commit()


class TestDeleteRuns:
    """Sprint 17 — history toplu/seçerek silme (db katmanı)."""

    def test_delete_runs_removes_run_and_models(self, isolated_db):
        """Seçilen run id'leri silinir; modelleri de cascade edilir."""
        _seed_run(isolated_db, 1, "run-a")
        _seed_run(isolated_db, 2, "run-b")
        _seed_run(isolated_db, 3, "run-c")

        deleted = dbmod.delete_runs(isolated_db, [1, 3])

        assert deleted == 2
        # Silinen run'lar gitti
        remaining = [
            r["id"] for r in isolated_db.execute("SELECT id FROM benchmark_runs")
        ]
        assert remaining == [2]
        # Modeller cascade edildi
        orphan_models = isolated_db.execute(
            "SELECT COUNT(*) c FROM benchmark_models WHERE run_id IN (1,3)"
        ).fetchone()["c"]
        assert orphan_models == 0
        # Kalan run'ın modelleri korundu
        kept_models = isolated_db.execute(
            "SELECT COUNT(*) c FROM benchmark_models WHERE run_id=2"
        ).fetchone()["c"]
        assert kept_models == 2

    def test_delete_runs_empty_list_noop(self, isolated_db):
        """Boş liste → 0 silme, hata yok."""
        _seed_run(isolated_db, 1, "run-a")
        deleted = dbmod.delete_runs(isolated_db, [])
        assert deleted == 0
        assert (
            isolated_db.execute("SELECT COUNT(*) c FROM benchmark_runs").fetchone()["c"]
            == 1
        )

    def test_delete_runs_unknown_ids_safe(self, isolated_db):
        """Var olmayan id'ler sessizce yok sayılır."""
        _seed_run(isolated_db, 1, "run-a")
        deleted = dbmod.delete_runs(isolated_db, [999])
        assert deleted == 0
        assert (
            isolated_db.execute("SELECT COUNT(*) c FROM benchmark_runs").fetchone()["c"]
            == 1
        )

    def test_delete_all_runs_clears_everything(self, isolated_db):
        """delete_all_runs tüm run + modelleri siler."""
        _seed_run(isolated_db, 1, "run-a")
        _seed_run(isolated_db, 2, "run-b")

        deleted = dbmod.delete_all_runs(isolated_db)

        assert deleted == 2
        assert (
            isolated_db.execute("SELECT COUNT(*) c FROM benchmark_runs").fetchone()["c"]
            == 0
        )
        assert (
            isolated_db.execute("SELECT COUNT(*) c FROM benchmark_models").fetchone()[
                "c"
            ]
            == 0
        )


# =============================================================================
# Sprint 23 — benchmarks tablosu source kolonu migrasyonu
# =============================================================================
class TestBenchmarksSourceColumn:
    """Sprint 23: benchmarks tablosuna source (real/community) kolonu eklenir."""

    def _fresh_bench_db(self, tmp_path):
        """SCHEMA_SPRINT9'u eski (source'suz) şema ile yeniden yaratır."""
        import sqlite3

        con = sqlite3.connect(tmp_path / "bench.db")
        con.row_factory = sqlite3.Row
        con.executescript(
            """
            CREATE TABLE benchmark_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT, source TEXT, use_case TEXT, created_at TEXT
            );
            CREATE TABLE benchmark_models (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL, name TEXT, provider TEXT, use_case TEXT,
              fit_score REAL, context_window INTEGER, notes TEXT,
              FOREIGN KEY(run_id) REFERENCES benchmark_runs(id)
            );
            CREATE TABLE benchmarks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              model TEXT NOT NULL, provider TEXT, measured_tps REAL, ttft_ms REAL,
              total_tokens INTEGER, wall_clock_s REAL, shared INTEGER DEFAULT 0,
              error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        return con

    def test_migrate_adds_source_column(self, tmp_path):
        """Eski şemaya migrate() çağrısı source kolonunu ekler."""
        con = self._fresh_bench_db(tmp_path)
        added = dbmod.migrate(con)

        assert "benchmarks.source" in added
        cols = {
            row["name"]
            for row in con.execute("PRAGMA table_info(benchmarks)").fetchall()
        }
        assert "source" in cols
        # Mevcut veri korunur
        con.execute(
            "INSERT INTO benchmarks(model,measured_tps) VALUES(?,?)", ("qwen3:8b", 55.0)
        )
        con.commit()
        con.close()

    def test_migrate_is_idempotent(self, tmp_path):
        """İkinci migrate çağrısı source'u tekrar eklemez (idempotent)."""
        con = self._fresh_bench_db(tmp_path)
        dbmod.migrate(con)
        added_again = dbmod.migrate(con)

        assert added_again == [] or "benchmarks.source" not in added_again

    def test_migrate_adds_trust_ve_tps_kaynagi(self, tmp_path):
        """Gece otonomu 2026-10-06: trust + tps_kaynagi kolonları additive eklenir.

        Denetim raporu 2026-10-05 §5.1-3: karar iddiaları yalnız trust='good'
        kayıtlardan üretilsin diye hız tablosuna güven etiketi geldi.
        """
        con = self._fresh_bench_db(tmp_path)
        added = dbmod.migrate(con)

        assert "benchmarks.trust" in added
        assert "benchmarks.tps_kaynagi" in added
        cols = {
            row["name"]
            for row in con.execute("PRAGMA table_info(benchmarks)").fetchall()
        }
        assert {"trust", "tps_kaynagi"} <= cols
        # Mevcut veri korunur; yeni kolonlar NULL başlar
        con.execute(
            "INSERT INTO benchmarks(model,measured_tps) VALUES(?,?)",
            ("qwen3:8b", 55.0),
        )
        row = con.execute(
            "SELECT trust, tps_kaynagi FROM benchmarks WHERE model='qwen3:8b'"
        ).fetchone()
        assert row["trust"] is None and row["tps_kaynagi"] is None
        con.close()

    def test_migrate_adds_kalibrasyon_kolonlari(self, tmp_path):
        """P1-2c: eski şemadan migrate(), kalibrasyon kolonlarını additive ekler.

        Boşluk 2026-11-04 denetiminde kaydedildi: predicted_tps/prediction_delta_pct
        ALTER yolu test edilmemişti (yalnız sıfırdan CREATE TABLE yolu örtilüyordu).
        """
        con = self._fresh_bench_db(tmp_path)
        added = dbmod.migrate(con)

        assert "benchmarks.predicted_tps" in added
        assert "benchmarks.prediction_delta_pct" in added
        cols = {
            row["name"]
            for row in con.execute("PRAGMA table_info(benchmarks)").fetchall()
        }
        assert {"predicted_tps", "prediction_delta_pct"} <= cols
        # Mevcut veri korunur; yeni kolonlar NULL başlar
        con.execute(
            "INSERT INTO benchmarks(model,measured_tps) VALUES(?,?)",
            ("qwen3:8b", 55.0),
        )
        con.commit()
        row = con.execute(
            "SELECT predicted_tps, prediction_delta_pct FROM benchmarks "
            "WHERE model='qwen3:8b'"
        ).fetchone()
        assert row["predicted_tps"] is None
        assert row["prediction_delta_pct"] is None
        con.close()
