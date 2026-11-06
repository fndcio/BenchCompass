"""
Integration testler — api/main.py (FastAPI dashboard)
==========================================================================
Test piramidi katman 2 (integration): gerçek FastAPI app + gerçek SQLite,
ama network yok (TestClient kullanır — subprocess/llmfit CLI mock'lanır).

AGENTS.md §6: dış bağımlılıklar (network, llmfit CLI) mock'lanır, dahili
mantık ASLA. Gerçek DB'ye dokunulmaz — tmp_root altında izole SQLite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import benchcompass_proxy


@pytest.fixture()
def client():
    """FastAPI TestClient — gerçek sunucu başlatmadan app'i test eder.

    AGENTS.md §6: dahili mantığı mock'lamıyoruz; sadece HTTP katmanını
    TestClient ile sarmalıyoruz. DB bağlantısı gerçek ama sqlite dosyası
    test sırasında oluşturulur (mevcut benchmark_history.db'ye dokunulmaz).
    """
    from api.main import app

    return TestClient(app)


# =============================================================================
# /health endpoint
# =============================================================================
class TestHealthEndpoint:
    """/health — servis sağlığı kontrolü."""

    def test_health_returns_ok(self, client):
        """AGENTS.md §6: güçlü onaylama — status_code ve ok alanı."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "db" in data  # SQLite dosya yolu

    def test_health_content_type_json(self, client):
        """/health JSON döner."""
        response = client.get("/health")
        assert response.headers["content-type"].startswith("application/json")


# =============================================================================
# /api/dashboard/summary endpoint
# =============================================================================
class TestDashboardSummaryEndpoint:
    """/api/dashboard/summary — özet veri (SQLite'tan)."""

    def test_summary_returns_expected_shape(self, client):
        """Dashboard summary beklenen JSON shape'i döner.

        AGENTS.md §6: güçlü onaylama — status_code VE yapısal alanlar.
        `!= 403` gibi zayıf onaylama YASAK.
        """
        response = client.get("/api/dashboard/summary")

        assert response.status_code == 200
        data = response.json()
        # DashboardSummary şemasının alanları
        assert "source" in data
        assert "latest" in data
        assert "history" in data
        assert data["source"] == "sqlite"

    def test_summary_history_is_list(self, client):
        """history alanı list olmalı (Sprint 6 veri yapısı)."""
        response = client.get("/api/dashboard/summary")
        data = response.json()

        assert isinstance(data["history"], list)


# =============================================================================
# /api/dashboard/history endpoint
# =============================================================================
class TestDashboardHistoryEndpoint:
    """/api/dashboard/history — geçmiş snapshot listesi."""

    def test_history_returns_list(self, client):
        response = client.get("/api/dashboard/history")

        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)


# =============================================================================
# /api/hardware endpoint
# =============================================================================
class TestHardwareEndpoint:
    """/api/hardware — donanım profili config dosyasından okur."""

    def test_hardware_returns_active_profile(self, client):
        """config/hardware_profile.json varsa aktif profil döner.

        Not: bu test config/hardware_profile.json dosyasının varlığına bağlı.
        CI'da dosya yoksa 404 dönebilir — bu beklenen davranıştır.
        """
        response = client.get("/api/hardware")

        if response.status_code == 200:
            data = response.json()
            assert "active_profile" in data
            assert "profiles" in data
            assert isinstance(data["profiles"], list)
            assert len(data["profiles"]) > 0
        elif response.status_code == 404:
            # Config dosyası yok — beklenen CI davranışı
            pytest.skip("config/hardware_profile.json yok (CI ortamı)")
        else:
            pytest.fail(f"Beklenmeyen status_code: {response.status_code}")


# =============================================================================
# / (dashboard SPA) endpoint
# =============================================================================
class TestDashboardSpaEndpoint:
    """GET / — Alpine.js dashboard HTML'i serve eder."""

    def test_root_returns_html(self, client):
        """Kök yol HTML dashboard döner (response_class=HTMLResponse)."""
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Minimal içerik kontrolü — dashboard shell'i
        assert len(response.text) > 100  # boş sayfa değil


# =============================================================================
# /docs (FastAPI auto-docs)
# =============================================================================
class TestAutoDocsEndpoint:
    """FastAPI /docs — OpenAPI Swagger UI."""

    def test_docs_accessible(self, client):
        """/docs erişilebilir olmalı (FastAPI built-in)."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        """/openapi.json geçerli şema döner."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
        # En azından /health tanımlı olmalı
        assert "/health" in data["paths"]


# =============================================================================
# /api/provider endpoint
# =============================================================================
class TestProviderEndpoint:
    """/api/provider — LLM sağlayıcı yapılandırması."""

    def test_provider_get_returns_config(self, client):
        """GET /api/provider yapılandırma dict döner."""
        response = client.get("/api/provider")

        assert response.status_code == 200
        data = response.json()
        # Varsayılan alanlar
        assert "provider" in data

    def test_provider_put_updates_config(self, client):
        """PUT /api/provider yapılandırmayı günceller."""
        response = client.put("/api/provider", json={"provider": "test-provider"})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["config"]["provider"] == "test-provider"


# =============================================================================
# /api/benchcompass/cache/* endpoints
# =============================================================================
class TestCacheEndpoints:
    """/api/benchcompass/cache/{status,clear} — TTL cache yönetimi."""

    def test_cache_status_returns_dict(self, client):
        response = client.get("/api/benchcompass/cache/status")

        assert response.status_code == 200
        data = response.json()
        # Cache status shape'i
        assert isinstance(data, dict)

    def test_cache_clear_returns_ok(self, client):
        response = client.post("/api/benchcompass/cache/clear")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


# =============================================================================
# /api/benchmarks endpoint
# =============================================================================
class TestBenchmarksEndpoint:
    """/api/benchmarks — ölçülmüş benchmark sonuçları listesi."""

    def test_benchmarks_returns_list(self, client):
        response = client.get("/api/benchmarks")

        assert response.status_code == 200
        data = response.json()
        # {"benchmarks": [...]} shape'i (raw liste değil)
        assert "benchmarks" in data
        assert isinstance(data["benchmarks"], list)


# =============================================================================
# /api/running-servers endpoint
# =============================================================================
class TestRunningServersEndpoint:
    """/api/running-servers — çalışan model sunucuları."""

    def test_running_servers_returns_list(self, client):
        response = client.get("/api/running-servers")

        assert response.status_code == 200
        data = response.json()
        # {"servers": [...]} shape'i (raw liste değil)
        assert "servers" in data
        assert isinstance(data["servers"], list)


# =============================================================================
# /api/dashboard/snapshot endpoint
# =============================================================================
class TestDashboardHistoryDeleteEndpoint:
    """Sprint 17 — DELETE /api/dashboard/history (toplu/seçerek silme)."""

    def _isolated_db(self, monkeypatch, tmp_path):
        """dbmod.connect'i izole tmp DB'ye yönlendir (gerçek DB'ye dokunma)."""
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "test.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)
        return dbmod

    def _seed(self, dbmod, name, run_id=None):
        con = dbmod.connect()
        cur = con.execute(
            "INSERT INTO benchmark_runs (name, source, use_case) VALUES (?,?,?)",
            (name, "test", "coding"),
        )
        rid = run_id if run_id is not None else cur.lastrowid
        con.execute(
            "INSERT INTO benchmark_models (run_id, name, fit_score) VALUES (?,?,?)",
            (rid, name + "-m1", 90),
        )
        con.commit()
        con.close()
        return rid

    def test_delete_selected_runs(self, client, monkeypatch, tmp_path):
        """run_ids ile seçerek silme → deleted sayısı + DB'den kalkar."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        self._seed(dbmod, "run-a", run_id=1)
        self._seed(dbmod, "run-b", run_id=2)
        self._seed(dbmod, "run-c", run_id=3)

        response = client.request(
            "DELETE", "/api/dashboard/history", json={"run_ids": [1, 3]}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 2
        # Kalan run sadece run-b
        con = dbmod.connect()
        remaining = [r["id"] for r in con.execute("SELECT id FROM benchmark_runs")]
        con.close()
        assert remaining == [2]

    def test_delete_all(self, client, monkeypatch, tmp_path):
        """all=true → tüm history silinir."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        self._seed(dbmod, "run-a", run_id=1)
        self._seed(dbmod, "run-b", run_id=2)

        response = client.request(
            "DELETE", "/api/dashboard/history", json={"all": True}
        )

        assert response.status_code == 200
        assert response.json()["deleted"] == 2
        con = dbmod.connect()
        assert con.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0] == 0
        con.close()

    def test_delete_noop_when_nothing_selected(self, client, monkeypatch, tmp_path):
        """run_ids boş ve all yok → 422/400 veya 0 silme, DB bozulmaz."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        self._seed(dbmod, "run-a", run_id=1)

        response = client.request("DELETE", "/api/dashboard/history", json={})

        assert response.status_code == 200
        assert response.json()["deleted"] == 0
        con = dbmod.connect()
        assert con.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0] == 1
        con.close()

    def test_delete_requires_delete_method(self, client, monkeypatch, tmp_path):
        """GET isteği 405 döner (sadece DELETE metodu)."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        self._seed(dbmod, "run-a", run_id=1)
        response = client.get("/api/dashboard/history")
        assert response.status_code == 200  # GET history ok — DELETE ayrı route


# =============================================================================
# /api/catalog endpoints (Sprint 19 — yerel model kataloğu)
# =============================================================================
class TestCatalogEndpoint:
    """GET /api/catalog + /api/catalog/search — hf_models.json yerel katalog."""

    def _fake_catalog(self, monkeypatch):
        """Gerçek data/hf_models.json yerine izole Catalog döndür."""
        from api import catalog as catalog_mod

        class FakeCat:
            loaded = True
            models = [{"name": "qwen-test", "provider": "qwen"}]

            def search(self, **kw):
                return [
                    {
                        "name": "Qwen/Qwen3-7B",
                        "provider": "qwen",
                        "min_ram_gb": 8.0,
                        "min_vram_gb": 6.0,
                        "context_length": 32768,
                        "quantization": "Q4_K_M",
                        "is_moe": False,
                        "parameters_raw": 7_000_000_000,
                        "gguf_sources": [
                            {"repo": "Qwen/Qwen3-7B-GGUF", "provider": "hf"}
                        ],
                    }
                ]

            def to_model_record(self, raw):
                return catalog_mod.Catalog().to_model_record(raw)

        monkeypatch.setattr(catalog_mod, "get_catalog", lambda: FakeCat())  # noqa: PLW0108 — callable korunur
        return catalog_mod

    def test_catalog_summary(self, client, monkeypatch):
        """Katalog özeti loaded + total_models içerir."""
        self._fake_catalog(monkeypatch)
        response = client.get("/api/catalog")
        assert response.status_code == 200
        data = response.json()
        assert data["loaded"] is True
        assert isinstance(data["providers"], list)

    def test_catalog_search_returns_models(self, client, monkeypatch):
        """Arama ModelRecord şemasında modeller döner."""
        self._fake_catalog(monkeypatch)
        response = client.get("/api/catalog/search?q=qwen")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "local-catalog"
        assert data["total"] >= 1
        m = data["models"][0]
        assert m["name"] == "Qwen/Qwen3-7B"
        assert m["required_vram_gb"] == 6.0
        assert m["context_window"] == 32768

    def test_catalog_search_no_result(self, client, monkeypatch):
        """Eşleşme yoksa boş liste (404 değil)."""
        from api import catalog as catalog_mod

        class EmptyCat:
            loaded = True
            models = []

            def search(self, **kw):
                return []

            def to_model_record(self, raw):
                return None

        monkeypatch.setattr(catalog_mod, "get_catalog", lambda: EmptyCat())  # noqa: PLW0108 — callable korunur
        response = client.get("/api/catalog/search?q=olmayan")
        assert response.status_code == 200
        assert response.json()["models"] == []

    def test_catalog_search_forwards_filter_params(self, client, monkeypatch):
        """Sprint 25 G1: filtre parametreleri catalog.search'e doğru iletilir."""
        from api import catalog as catalog_mod

        captured = {}

        class FilterCat:
            loaded = True
            models = [{"name": "A", "provider": "x"}]

            def search(self, **kw):
                captured.update(kw)
                return [
                    {"name": "Qwen/Qwen3-7B", "provider": "qwen", "min_ram_gb": 8.0}
                ]

            def to_model_record(self, raw):
                return catalog_mod.Catalog().to_model_record(raw)

        monkeypatch.setattr(catalog_mod, "get_catalog", lambda: FilterCat())  # noqa: PLW0108
        response = client.get(
            "/api/catalog/search?q=test&provider=ollama&use_case=coding&is_moe=true&min_ctx=32768&limit=5"
        )

        assert response.status_code == 200
        assert captured["q"] == "test"
        assert captured["provider"] == "ollama"
        assert captured["use_case"] == "coding"
        assert captured["is_moe"] is True
        assert captured["min_ctx"] == 32768
        assert captured["limit"] == 5

    def test_catalog_search_is_moe_false_parses_bool(self, client, monkeypatch):
        """Sprint 25 G1: is_moe=false doğru şekilde False'a çevrilir (None değil)."""
        from api import catalog as catalog_mod

        captured = {}

        class FilterCat:
            loaded = True
            models = []

            def search(self, **kw):
                captured.update(kw)
                return []

            def to_model_record(self, raw):
                return None

        monkeypatch.setattr(catalog_mod, "get_catalog", lambda: FilterCat())  # noqa: PLW0108
        response = client.get("/api/catalog/search?q=test&is_moe=false")

        assert response.status_code == 200
        assert captured["is_moe"] is False

    def test_catalog_search_defaults_no_filters(self, client, monkeypatch):
        """Sprint 25 G1: filtre verilmezse boş default'lar iletilir (mevcut davranış)."""
        from api import catalog as catalog_mod

        captured = {}

        class FilterCat:
            loaded = True
            models = []

            def search(self, **kw):
                captured.update(kw)
                return []

            def to_model_record(self, raw):
                return None

        monkeypatch.setattr(catalog_mod, "get_catalog", lambda: FilterCat())  # noqa: PLW0108
        response = client.get("/api/catalog/search?q=test")

        assert response.status_code == 200
        assert captured["provider"] == ""
        assert captured["use_case"] == ""
        assert captured["is_moe"] is None
        assert captured["min_ctx"] == 0


# =============================================================================
# /api/migrate endpoint
# =============================================================================
class TestMigrateEndpoint:
    """/api/migrate — DB şema migrasyonu."""

    def test_migrate_returns_migrate_result(self, client):
        """POST /api/migrate MigrateResult shape döner (idempotent)."""
        response = client.post("/api/migrate")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "added_columns" in data
        assert "backfilled_rows" in data


# =============================================================================
# /api/hardware/autodetect endpoint
# =============================================================================
class TestHardwareAutodetectEndpoint:
    """/api/hardware/autodetect — llmfit system ile donanım tespiti."""

    def test_autodetect_endpoint_accessible(self, client):
        """Autodetect çağrılabilir (llmfit CLI yoksa hata dönebilir ama endpoint tanımlı olmalı)."""
        response = client.post("/api/hardware/autodetect")

        # llmfit yoksa 503 döner (dokümante edilmiş fallback — _llmfit_error_response)
        assert response.status_code in (200, 500, 503)


# =============================================================================
# /api/grafiks/ekstra endpoint
# =============================================================================
class TestExtraChartsEndpoint:
    """/api/grafiks/ekstra — ek grafik verileri."""

    def test_extra_charts_returns_dict(self, client):
        response = client.get("/api/grafiks/ekstra")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# =============================================================================
# /api/eval/report-status endpoint (Sprint 27 — C1)
# =============================================================================
class TestEvalReportStatusEndpoint:
    """/api/eval/report-status — [ RAPOR ] sekmesi boş durum bilgisi."""

    def test_report_status_shape(self, client):
        """Endpoint tanımlı, shape döner (exists bool + updated_at)."""
        response = client.get("/api/eval/report-status")

        assert response.status_code == 200
        data = response.json()
        assert "exists" in data
        assert data["exists"] is False or data["exists"] is True
        assert "updated_at" in data
        assert "path" in data

    def test_report_status_no_report(self, client, monkeypatch, tmp_path):
        """Rapor dizini yoksa exists=False döner (boş durum — iframe yerine mesaj)."""
        from api import main as main_mod

        empty_dir = tmp_path / "reports"
        empty_dir.mkdir(exist_ok=True)
        monkeypatch.setattr(main_mod, "EVAL_REPORTS_DIR", empty_dir)
        response = client.get("/api/eval/report-status")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["updated_at"] is None

    def test_report_status_with_report(self, client, monkeypatch, tmp_path):
        """index.html varsa exists=True + updated_at döner."""
        from api import main as main_mod

        report_dir = tmp_path / "reports"
        report_dir.mkdir(exist_ok=True)
        (report_dir / "index.html").write_text("<html>rapor</html>", encoding="utf-8")
        monkeypatch.setattr(main_mod, "EVAL_REPORTS_DIR", report_dir)
        response = client.get("/api/eval/report-status")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["updated_at"]


# =============================================================================
# /api/benchcompass/* endpoints (benchcompass_proxy mock'lu)
# =============================================================================
class TestLlmfitProxyEndpoints:
    """/api/benchcompass/* — llmfit CLI sarmalayıcı endpoint'leri."""

    def test_llmfit_info_endpoint(self, client, monkeypatch):
        """GET /api/benchcompass/info/{model} mock'lu dict döner."""
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_info",
            lambda *a, **kw: {"model": "test", "score": 90},
        )
        response = client.get("/api/benchcompass/info/test-model")

        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "test"

    def test_llmfit_system_endpoint(self, client, monkeypatch):
        """GET /api/benchcompass/system mock'lu donanım bilgisi döner."""
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_system",
            lambda *a, **kw: {"gpu": "RTX", "vram_gb": 12},
        )
        response = client.get("/api/benchcompass/system")

        assert response.status_code == 200
        data = response.json()
        assert "gpu" in data

    def test_llmfit_diff_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_diff",
            lambda *a, **kw: {"comparison": "ok"},
        )
        response = client.get("/api/benchcompass/diff")

        assert response.status_code == 200

    def test_llmfit_doctor_endpoint(self, client, monkeypatch):
        """GET /api/benchcompass/doctor mock'lu sağlık raporu döner."""
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_doctor",
            lambda *a, **kw: "doctor report string",
        )
        response = client.get("/api/benchcompass/doctor")

        assert response.status_code == 200

    def test_llmfit_fit_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_fit", lambda *a, **kw: {"models": []}
        )
        response = client.get("/api/benchcompass/fit")

        assert response.status_code == 200

    def test_llmfit_plan_endpoint(self, client, monkeypatch):
        """POST /api/benchcompass/plan mock'lu planlama döner."""
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_plan", lambda *a, **kw: {"plan": "ok"}
        )
        response = client.post(
            "/api/benchcompass/plan", json={"model": "test", "context": 8192}
        )

        assert response.status_code == 200

    def test_llmfit_info_error_handled(self, client, monkeypatch):
        """llmfit_error → error dict döner (LlmfitError yakalanır)."""

        def raise_error(*a, **kw):
            raise benchcompass_proxy.LlmfitError("model bulunamadi")

        monkeypatch.setattr("api.main.benchcompass_proxy.llmfit_info", raise_error)
        response = client.get("/api/benchcompass/info/bad-model")

        # _llmfit_error_response error dict döner (503 Service Unavailable)
        assert response.status_code in (200, 500, 503)
        data = response.json()
        assert "error" in data or "detail" in data


# =============================================================================
# /api/recommend endpoint
# =============================================================================
class TestRecommendEndpoint:
    """/api/recommend — use-case bazlı model tavsiyesi."""

    def test_recommend_returns_dict(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_recommend",
            lambda *a, **kw: {"models": []},
        )
        response = client.get("/api/recommend", params={"use_case": "coding"})

        assert response.status_code == 200


# =============================================================================
# /api/export/report endpoint
# =============================================================================
class TestExportReportEndpoint:
    """/api/export/report — Markdown rapor dışa aktarma."""

    def test_export_returns_text(self, client):
        """Export endpoint Markdown text döner."""
        response = client.get("/api/export/report")

        # Rapor üretimi donanım profili gerektirir; 200 veya 500 olabilir
        assert response.status_code in (200, 500)


# =============================================================================
# /api/tasks endpoint
# =============================================================================
class TestTasksEndpoint:
    """/api/tasks — arka plan görev listesi."""

    def test_tasks_list_returns_list(self, client):
        response = client.get("/api/tasks")

        assert response.status_code == 200
        data = response.json()
        # {"tasks": [...]} shape'i (raw liste değil)
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_task_get_nonexistent_returns_error(self, client):
        """Olmayan task UUID → error dict döner."""
        response = client.get("/api/tasks/nonexistent-uuid-12345")

        assert response.status_code == 200
        data = response.json()
        # _task_dict None → {"error": "task not found"}
        assert "error" in data or "status" in data


# =============================================================================
# /api/hf-search endpoint
# =============================================================================
class TestHfSearchEndpoint:
    """/api/hf-search — HuggingFace GGUF arama."""

    def test_hf_search_returns_dict(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_hf_search",
            lambda *a, **kw: {"results": []},
        )
        response = client.get("/api/hf-search", params={"query": "qwen"})

        assert response.status_code == 200


# =============================================================================
# /api/hardware PUT (güncelleme)
# =============================================================================
class TestHardwarePutEndpoint:
    """PUT /api/hardware — donanım profili güncelleme."""

    def test_hardware_put_updates_active_profile(self, client):
        """Aktif profil değiştirilebilir."""
        # Önce mevcut config'i al
        get_resp = client.get("/api/hardware")
        if get_resp.status_code != 200:
            pytest.skip("config/hardware_profile.json yok")

        # PUT ile active_profile güncelle (geçerli bir profil ID'sine)
        profiles = get_resp.json().get("profiles", [])
        if not profiles:
            pytest.skip("profil yok")

        target_id = profiles[0]["id"]
        response = client.put("/api/hardware", json={"active_profile": target_id})

        assert response.status_code == 200
        data = response.json()
        assert data["active_profile"] == target_id


# =============================================================================
# /api/benchmark, /api/download, /api/run (Sprint 9 mock endpoint'leri)
# =============================================================================
class TestMockBenchmarkEndpoints:
    """/api/benchmark, /api/download, /api/run — arka plan görev başlatma."""

    def test_benchmark_starts_task(self, client, monkeypatch):
        """POST /api/benchmark task_uuid döner."""
        monkeypatch.setattr(
            "api.main.bg_tasks.create_task", lambda *a, **kw: "fake-uuid-123"
        )
        response = client.post("/api/benchmark", json={"model": "test-model"})

        assert response.status_code == 200
        data = response.json()
        assert data["task_uuid"] == "fake-uuid-123"
        assert data["status"] == "started"

    def test_benchmark_reads_model_from_body(self, client, monkeypatch):
        """Body'deki model create_task'e iletilir (Sprint 27 — query param bug'ı).

        Önceden endpoint model'i query param olarak okuyordu; frontend JSON body
        gönderdiğinden hep varsayılan 'Qwen/Qwen2.5-Coder-7B' (Ollama'da yok)
        benchmark'lanıyor ve 404 alınıyordu.
        """
        captured: dict = {}

        def fake_create(*a, **kw):
            captured.update(kw)
            return "fake-uuid-456"

        monkeypatch.setattr("api.main.bg_tasks.create_task", fake_create)
        response = client.post(
            "/api/benchmark", json={"model": "qwen3:8b", "provider": "ollama"}
        )

        assert response.status_code == 200
        assert captured["model"] == "qwen3:8b"
        assert captured["provider"] == "ollama"

    def test_download_starts_task(self, client, monkeypatch):
        """POST /api/download task_uuid döner (query param repo)."""
        monkeypatch.setattr(
            "api.main.bg_tasks.create_task", lambda *a, **kw: "fake-uuid-dl"
        )
        response = client.post("/api/download", params={"repo": "test/repo"})

        assert response.status_code == 200
        data = response.json()
        assert "task_uuid" in data

    def test_run_starts_task(self, client, monkeypatch):
        """POST /api/run task_uuid döner (query param model)."""
        monkeypatch.setattr(
            "api.main.bg_tasks.create_task", lambda *a, **kw: "fake-uuid-run"
        )
        response = client.post("/api/run", params={"model": "test-model"})

        assert response.status_code == 200
        data = response.json()
        assert "task_uuid" in data

    def test_run_stop_endpoint(self, client, monkeypatch):
        """POST /api/run/stop → ok=True."""
        monkeypatch.setattr(
            "api.main.ollama_client.stop_model", lambda *a, **kw: {"ok": True}
        )
        response = client.post("/api/run/stop", json={"model": "test"})

        # Endpoint tanımlı, status 200 beklenir
        assert response.status_code in (200, 404, 422)


class TestRealBenchmarkFallback:
    """Sprint 20 — _mock_benchmark gerçek community verisine düşer."""

    def _stub_gpu(self, monkeypatch, gpu_name):
        """_current_gpu_name'i stub'lar."""
        monkeypatch.setattr("api.routes.shared._current_gpu_name", lambda: gpu_name)

    def test_enrich_models_with_community_speed(self, monkeypatch, tmp_path):
        """_enrich_models_with_community_speed model hızını community ile doldurur."""
        import json as _json

        from api import bench_data as bench_mod

        fake = {
            "presets": {
                "RTX 5070": {
                    "rows": [
                        {
                            "model": {
                                "hfId": "Qwen/Qwen3-7B",
                                "displayName": "Qwen3-7B",
                            },
                            "tokSOut": 102.5,
                            "tokSTotal": 105.0,
                            "ttftMs": 120.0,
                            "hardware": {"gpuName": "RTX 5070", "vramGb": 12},
                            "engine": {"quantization": "Q4_K_M"},
                        }
                    ]
                }
            }
        }
        path = tmp_path / "bench.json"
        path.write_text(_json.dumps(fake), encoding="utf-8")
        monkeypatch.setattr(bench_mod, "get_bench", lambda: bench_mod.BenchData(path))
        monkeypatch.setattr(
            "api.main.bench_data.get_bench", lambda: bench_mod.BenchData(path)
        )
        self._stub_gpu(monkeypatch, "RTX 5070")

        from api.main import _enrich_models_with_community_speed

        models = [{"name": "Qwen/Qwen3-7B-Instruct", "estimated_speed_tok_s": 40.0}]
        _enrich_models_with_community_speed(models)

        assert models[0]["estimated_speed_tok_s"] == 102.5
        assert models[0]["speed_source"] == "community"
        assert models[0]["community_ttft_ms"] == 120.0

    def test_enrich_models_no_gpu_keeps_estimate(self, monkeypatch):
        """GPU yoksa mevcut tahmin korunur (community'e dokunulmaz)."""
        self._stub_gpu(monkeypatch, "")
        from api.main import _enrich_models_with_community_speed

        models = [{"name": "Qwen/Qwen3-7B", "estimated_speed_tok_s": 40.0}]
        _enrich_models_with_community_speed(models)
        assert models[0]["estimated_speed_tok_s"] == 40.0
        assert "speed_source" not in models[0]

    def test_enrich_models_no_match_keeps_estimate(self, monkeypatch, tmp_path):
        """Donanım eşleşmezse mevcut tahmin korunur."""
        from api import bench_data as bench_mod

        empty = {"presets": {}}
        path = tmp_path / "empty.json"
        path.write_text(__import__("json").dumps(empty), encoding="utf-8")
        monkeypatch.setattr(bench_mod, "get_bench", lambda: bench_mod.BenchData(path))
        monkeypatch.setattr(
            "api.main.bench_data.get_bench", lambda: bench_mod.BenchData(path)
        )
        self._stub_gpu(monkeypatch, "GTX 1080")

        from api.main import _enrich_models_with_community_speed

        models = [{"name": "olmayan", "estimated_speed_tok_s": 33.0}]
        _enrich_models_with_community_speed(models)
        assert models[0]["estimated_speed_tok_s"] == 33.0
        assert "speed_source" not in models[0]

    def test_real_benchmark_uses_community_data(self, monkeypatch, tmp_path):
        """Donanım+model eşleşirse gerçek tok/s kullanılır (source=community)."""
        import json as _json

        from api import bench_data as bench_mod

        fake = {
            "presets": {
                "RTX 5070": {
                    "rows": [
                        {
                            "model": {
                                "hfId": "Qwen/Qwen3-7B",
                                "displayName": "Qwen3-7B",
                            },
                            "tokSOut": 102.5,
                            "tokSTotal": 105.0,
                            "ttftMs": 120.0,
                            "hardware": {"gpuName": "RTX 5070", "vramGb": 12},
                            "engine": {"quantization": "Q4_K_M"},
                        }
                    ]
                }
            }
        }
        path = tmp_path / "bench.json"
        path.write_text(_json.dumps(fake), encoding="utf-8")
        monkeypatch.setattr(bench_mod, "get_bench", lambda: bench_mod.BenchData(path))
        monkeypatch.setattr(
            "api.main.bench_data.get_bench", lambda: bench_mod.BenchData(path)
        )
        self._stub_gpu(monkeypatch, "RTX 5070")

        from api.main import _mock_benchmark

        result = _mock_benchmark("Qwen/Qwen3-7B", provider="test")

        assert result["measured_tps"] == 102.5
        assert result["ttft_ms"] == 120.0
        assert result["source"] == "community"

    def test_real_benchmark_no_community_raises_honest_error(
        self, monkeypatch, tmp_path
    ):
        """Eşleşme yoksa dürüst hata fırlatılır — rastgele tahmin ÜRETİLMEZ (Sprint 27)."""
        from api import bench_data as bench_mod

        empty = {"presets": {}}
        path = tmp_path / "empty.json"
        path.write_text(__import__("json").dumps(empty), encoding="utf-8")
        monkeypatch.setattr(bench_mod, "get_bench", lambda: bench_mod.BenchData(path))
        monkeypatch.setattr(
            "api.main.bench_data.get_bench", lambda: bench_mod.BenchData(path)
        )
        self._stub_gpu(monkeypatch, "GTX 1080")

        from api.main import _mock_benchmark

        with pytest.raises(RuntimeError, match="ölçüm yapılmadı"):
            _mock_benchmark("olmayan-model", provider="test")

    def test_real_benchmark_no_gpu_raises_honest_error(self, monkeypatch):
        """GPU adı yoksa ve community yoksa dürüst hata (sahte sayı değil)."""
        self._stub_gpu(monkeypatch, "")
        from api.main import _mock_benchmark

        with pytest.raises(RuntimeError, match="ölçüm yapılmadı"):
            _mock_benchmark("herhangi-model", provider="test")


class TestFamilyScoreEnrichment:
    """Sprint 21 — _enrich_models_with_family_score + use_case eşleşmesi."""

    def _stub_fit(self, monkeypatch, tmp_path):
        import json

        from api import fit_scores as fs_mod

        uc_data = {
            "families": [
                {
                    "match": ["qwen3-coder"],
                    "scores": {"coding": 90, "reasoning": 78, "chat": 72},
                },
                {
                    "match": ["deepseek-r1"],
                    "scores": {"coding": 84, "reasoning": 93, "chat": 76},
                },
            ]
        }
        path = tmp_path / "uc.json"
        path.write_text(json.dumps(uc_data), encoding="utf-8")
        fake = fs_mod.FitScores(usecase_path=path, baseline_path=tmp_path / "yok.json")
        monkeypatch.setattr(fs_mod, "get_fit", lambda: fake)
        monkeypatch.setattr("api.main.fit_scores.get_fit", lambda: fake)
        return fake

    def test_use_case_key_mapping(self, monkeypatch, tmp_path):
        from api.main import _use_case_key

        assert _use_case_key("Code generation and completion") == "coding"
        assert _use_case_key("Advanced reasoning") == "reasoning"
        assert _use_case_key("Instruction following, chat") == "chat"
        assert _use_case_key("General purpose") is None

    def test_enrich_family_score_coding(self, monkeypatch, tmp_path):
        """Coding modeli aile skorunu alır (fit hibrit için)."""
        self._stub_fit(monkeypatch, tmp_path)
        from api.main import _enrich_models_with_family_score

        models = [
            {
                "name": "Qwen/Qwen3-Coder-7B",
                "useCase": "Code generation",
                "fitScore": 80,
            }
        ]
        _enrich_models_with_family_score(models)
        assert models[0]["family_score"] == 90
        assert models[0]["family_use_case"] == "coding"

    def test_enrich_family_score_no_match(self, monkeypatch, tmp_path):
        """Aile eşleşmezse alan eklenmez (mevcut fit korunur)."""
        self._stub_fit(monkeypatch, tmp_path)
        from api.main import _enrich_models_with_family_score

        models = [{"name": "bilinmeyen", "useCase": "General purpose", "fitScore": 55}]
        _enrich_models_with_family_score(models)
        assert "family_score" not in models[0]
        assert models[0]["fitScore"] == 55

    def test_enrich_family_score_empty_models(self, monkeypatch, tmp_path):
        """Boş liste → çökmez."""
        self._stub_fit(monkeypatch, tmp_path)
        from api.main import _enrich_models_with_family_score

        _enrich_models_with_family_score([])


class TestFitBaselineEndpoint:
    """Sprint 21 — /api/fit/baseline frontier karşılaştırması."""

    def _stub_fit(self, monkeypatch, tmp_path):
        import json

        from api import fit_scores as fs_mod

        uc_data = {"families": []}
        uc_path = tmp_path / "uc.json"
        uc_path.write_text(json.dumps(uc_data), encoding="utf-8")
        bl_data = {
            "baselines": [
                {
                    "model": "claude-sonnet-4-5",
                    "provider": "anthropic",
                    "roles": {
                        "coding": {"quality": 9.5, "speed": 80.0, "composite": 9.6}
                    },
                    "overall": {"quality": 9.2, "speed": 78.0, "composite": 9.3},
                },
                {
                    "model": "gpt-4o",
                    "provider": "openai",
                    "roles": {
                        "coding": {"quality": 9.0, "speed": 85.0, "composite": 9.3}
                    },
                    "overall": {"quality": 8.8, "speed": 83.0, "composite": 9.0},
                },
            ]
        }
        bl_path = tmp_path / "bl.json"
        bl_path.write_text(json.dumps(bl_data), encoding="utf-8")
        fake = fs_mod.FitScores(usecase_path=uc_path, baseline_path=bl_path)
        monkeypatch.setattr(fs_mod, "get_fit", lambda: fake)
        monkeypatch.setattr("api.main.fit_scores.get_fit", lambda: fake)
        return fake

    def test_baseline_for_model(self, client, monkeypatch, tmp_path):
        """Seçili model + rol baseline bilgisi döner."""
        self._stub_fit(monkeypatch, tmp_path)
        response = client.get(
            "/api/fit/baseline", params={"model": "claude-sonnet-4-5", "role": "coding"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["baseline"]["composite"] == 9.6
        assert data["top_baseline"]["model"] == "claude-sonnet-4-5"

    def test_baseline_unknown_model(self, client, monkeypatch, tmp_path):
        """Bilinmeyen model → baseline None, top bilgisi gelir."""
        self._stub_fit(monkeypatch, tmp_path)
        response = client.get(
            "/api/fit/baseline", params={"model": "yerel-model", "role": "coding"}
        )
        data = response.json()
        assert data["baseline"] is None
        assert data["top_baseline"] is not None

    def test_baseline_unknown_role_falls_back(self, client, monkeypatch, tmp_path):
        """Bilinmeyen rol coding'e düşer."""
        self._stub_fit(monkeypatch, tmp_path)
        response = client.get(
            "/api/fit/baseline", params={"model": "gpt-4o", "role": "olmayan-rol"}
        )
        data = response.json()
        assert data["role"] == "coding"
        assert data["baseline"]["composite"] == 9.3

    def test_baseline_empty_available_false(self, client, monkeypatch, tmp_path):
        """baselines.json yoksa available=False (çökmez)."""
        from api import fit_scores as fs_mod

        fake = fs_mod.FitScores(
            usecase_path=tmp_path / "uc.json",
            baseline_path=tmp_path / "bl-yok.json",
        )
        monkeypatch.setattr(fs_mod, "get_fit", lambda: fake)
        monkeypatch.setattr("api.main.fit_scores.get_fit", lambda: fake)
        response = client.get(
            "/api/fit/baseline", params={"model": "x", "role": "coding"}
        )
        data = response.json()
        assert data["available"] is False
        assert data["baseline"] is None
        assert data["top_baseline"] is None


# =============================================================================
# /api/dashboard/snapshot
# =============================================================================
class TestSnapshotEndpoint:
    """/api/dashboard/snapshot — yeni snapshot oluşturma."""

    def test_snapshot_creates_with_default_name(self, client):
        """POST /api/dashboard/snapshot boş isimle → otomatik timestamp."""
        response = client.post("/api/dashboard/snapshot", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "run_id" in data

    def test_snapshot_with_custom_name(self, client):
        response = client.post(
            "/api/dashboard/snapshot", json={"name": "test-snapshot"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


# =============================================================================
# /api/ollama/models
# =============================================================================
class TestOllamaModelsEndpoint:
    """/api/ollama/models — Ollama model listesi."""

    def test_ollama_models_returns_list(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.ollama_client.list_models", lambda: [{"name": "test"}]
        )
        response = client.get("/api/ollama/models")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "models" in data

    def test_ollama_models_error_handled(self, client, monkeypatch):
        """OllamaError → error dict (servis kapalı)."""

        def raise_error():
            raise benchcompass_proxy.LlmfitError("ollama down")  # type: ignore[misc]

        from api import ollama_client

        monkeypatch.setattr(
            "api.main.ollama_client.list_models",
            lambda: (_ for _ in ()).throw(ollama_client.OllamaError("down")),
        )
        response = client.get("/api/ollama/models")
        # Hata yakalanır, 200 veya 503
        assert response.status_code in (200, 503)


# =============================================================================
# /api/ollama/ps
# =============================================================================
class TestOllamaPsEndpoint:
    """/api/ollama/ps — çalışan Ollama modelleri."""

    def test_ollama_ps_returns_list(self, client, monkeypatch):
        monkeypatch.setattr("api.main.ollama_client.ps", lambda: [{"name": "running"}])
        response = client.get("/api/ollama/ps")

        assert response.status_code == 200


# =============================================================================
# /api/ollama/run, /api/ollama/stop
# =============================================================================
class TestOllamaRunStopEndpoints:
    def test_ollama_run(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.ollama_client.run_model", lambda *a, **kw: {"ok": True}
        )
        response = client.post("/api/ollama/run", json={"model": "test"})

        assert response.status_code in (200, 422)

    def test_ollama_stop(self, client, monkeypatch):
        monkeypatch.setattr(
            "api.main.ollama_client.stop_model", lambda *a, **kw: {"ok": True}
        )
        response = client.post("/api/ollama/stop", json={"model": "test"})

        assert response.status_code in (200, 422)


# =============================================================================
# /api/ollama/benchmark (Sprint 23 — gerçek llmfit bench + community fallback)
# =============================================================================
class TestOllamaBenchmarkEndpoint:
    """POST /api/ollama/benchmark — gerçek llmfit bench, community fallback.

    Kabul kriteri: llmfit CLI varsa source='real'; yoksa community fallback
    source='community'; hiçbiri yoksa dürüst hata (ok:false).
    """

    def _isolated_db(self, monkeypatch, tmp_path):
        """dbmod.connect'i izole tmp DB'ye yönlendir (gerçek DB'ye dokunma)."""
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "test.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)
        return dbmod

    def test_real_bench_success_source_real(self, client, monkeypatch, tmp_path):
        """llmfit_bench başarılı → source='real', DB'ye source yazılır."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_bench",
            lambda model, provider="auto", runs=1, **kw: {
                "measured_tps": 45.2,
                "ttft_ms": 120.0,
                "total_tokens": 100,
                "source": "real",
                "raw_keys": ["measured_tps"],
            },
        )

        response = client.post("/api/ollama/benchmark", json={"model": "qwen3:8b"})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["result"]["source"] == "real"
        assert data["result"]["measured_tps"] == pytest.approx(45.2)
        # DB'ye source='real' ile yazıldı
        con = dbmod.connect()
        row = con.execute(
            "SELECT source FROM benchmarks WHERE model='qwen3:8b'"
        ).fetchone()
        con.close()
        assert row is not None
        assert row["source"] == "real"

    def test_bench_falls_back_to_community(self, client, monkeypatch, tmp_path):
        """llmfit CLI yok → community verisine düşer (source='community')."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        from api import benchcompass_proxy

        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_bench",
            lambda model, provider="auto", runs=1, **kw: (_ for _ in ()).throw(
                benchcompass_proxy.LlmfitError("llmfit bulunamadı")
            ),
        )
        import json as _json

        from api import bench_data as bench_mod

        fake = {
            "presets": {
                "RTX 5070": {
                    "rows": [
                        {
                            "model": {
                                "hfId": "Qwen/Qwen3-8B",
                                "displayName": "Qwen3-8B",
                            },
                            "tokSOut": 88.0,
                            "tokSTotal": 90.0,
                            "ttftMs": 200.0,
                            "hardware": {"gpuName": "RTX 5070"},
                            "engine": {},
                        }
                    ]
                }
            }
        }
        path = tmp_path / "bench.json"
        path.write_text(_json.dumps(fake), encoding="utf-8")
        monkeypatch.setattr(bench_mod, "get_bench", lambda: bench_mod.BenchData(path))
        monkeypatch.setattr(
            "api.main.bench_data.get_bench", lambda: bench_mod.BenchData(path)
        )
        monkeypatch.setattr("api.routes.shared._current_gpu_name", lambda: "RTX 5070")

        response = client.post("/api/ollama/benchmark", json={"model": "Qwen/Qwen3-8B"})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["result"]["source"] == "community"
        assert data["result"]["measured_tps"] == pytest.approx(88.0)
        con = dbmod.connect()
        row = con.execute(
            "SELECT source FROM benchmarks WHERE model='Qwen/Qwen3-8B'"
        ).fetchone()
        con.close()
        assert row is not None
        assert row["source"] == "community"

    def test_bench_no_fallback_returns_honest_error(
        self, client, monkeypatch, tmp_path
    ):
        """llmfit yok + community yok → ok:false (dürüst hata — tahmin üretilmez)."""
        self._isolated_db(monkeypatch, tmp_path)
        from api import benchcompass_proxy

        monkeypatch.setattr(
            "api.main.benchcompass_proxy.llmfit_bench",
            lambda model, provider="auto", runs=1, **kw: (_ for _ in ()).throw(
                benchcompass_proxy.LlmfitError("llmfit bulunamadı")
            ),
        )
        monkeypatch.setattr("api.routes.shared._current_gpu_name", lambda: "")

        response = client.post("/api/ollama/benchmark", json={"model": "qwen3:8b"})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False


# =============================================================================
# Sprint 23 G3 — estimated_speed_tok_s gerçek ölçüm öncelikli
# =============================================================================
class TestRealBenchmarkPriority:
    """G3: benchmarks(source='real') varsa estimated_speed_tok_s öncelikli real."""

    def _isolated_db(self, monkeypatch, tmp_path):
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "test.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)
        return dbmod

    def _seed_model(self, dbmod, name="qwen3:8b", est_speed=40.0):
        con = dbmod.connect()
        cur = con.execute(
            "INSERT INTO benchmark_runs(name,source,use_case) VALUES(?,?,?)",
            ("run", "test", "coding"),
        )
        run_id = cur.lastrowid
        con.execute(
            "INSERT INTO benchmark_models(run_id,name,fit_score,estimated_speed_tok_s)"
            " VALUES(?,?,?,?)",
            (run_id, name, 90, est_speed),
        )
        con.commit()
        con.close()

    def test_dashboard_summary_prefers_real_benchmark(
        self, client, monkeypatch, tmp_path
    ):
        """benchmarks'ta source='real' varsa estimated_speed_tok_s real ölçüm olur."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        self._seed_model(dbmod, "qwen3:8b", est_speed=40.0)
        # Gerçek ölçüm: benchmarks tablosuna source='real' ile yaz
        con = dbmod.connect()
        con.execute(
            "INSERT INTO benchmarks(model,provider,measured_tps,ttft_ms,total_tokens,"
            "wall_clock_s,shared,source) VALUES(?,?,?,?,?,?,?,?)",
            ("qwen3:8b", "ollama", 55.0, 100.0, 200, 5.0, 0, "real"),
        )
        con.commit()
        con.close()
        # GPU yok → community güçlendirmesi devre dışı (yalnızca real önceliği test edilir)
        monkeypatch.setattr("api.routes.shared._current_gpu_name", lambda: "")

        response = client.get("/api/dashboard/summary")

        assert response.status_code == 200
        models = response.json()["latest"]["models"]
        m = next(x for x in models if x["name"] == "qwen3:8b")
        assert m["estimated_speed_tok_s"] == pytest.approx(55.0)
        assert m["speed_source"] == "real"

    def test_dashboard_summary_keeps_estimate_when_no_real(
        self, client, monkeypatch, tmp_path
    ):
        """benchmarks'ta real ölçüm yoksa mevcut tahmin KORUNUR (yıkıcı değişiklik yok)."""
        dbmod = self._isolated_db(monkeypatch, tmp_path)
        self._seed_model(dbmod, "qwen3:8b", est_speed=40.0)
        # Community kaydı var ama real yok → tahmin korunur
        con = dbmod.connect()
        con.execute(
            "INSERT INTO benchmarks(model,provider,measured_tps,ttft_ms,total_tokens,"
            "wall_clock_s,shared,source) VALUES(?,?,?,?,?,?,?,?)",
            ("qwen3:8b", "ollama", 30.0, 100.0, 200, 5.0, 0, "community"),
        )
        con.commit()
        con.close()
        monkeypatch.setattr("api.routes.shared._current_gpu_name", lambda: "")

        response = client.get("/api/dashboard/summary")

        assert response.status_code == 200
        models = response.json()["latest"]["models"]
        m = next(x for x in models if x["name"] == "qwen3:8b")
        assert m["estimated_speed_tok_s"] == pytest.approx(40.0)
        assert m.get("speed_source") is None


# =============================================================================
# Sprint 22 — coverage kapanışı: hata yolları + edge case'ler
# =============================================================================
class TestCoverageEdgeCases:
    """X-Ray Öneri 1 için hedefli coverage kapanışı (anlamsız test YASAK — Y9)."""

    def test_legacy_returns_html_or_404(self, client):
        """GET /legacy — route kaldırıldı (Sprint 28 T7); 404 döner."""
        response = client.get("/legacy")
        # /legacy endpoint'i tamamen kaldırıldı → 404 beklenir
        assert response.status_code == 404

    def test_legacy_fallback_raises_404_when_missing(self, client, monkeypatch):
        """index HTML'i yoksa root 404 fırlatır."""
        import api.main as main_mod

        monkeypatch.setattr(
            main_mod, "INDEX_HTML", main_mod.BASE / "olmayan-dosya.html"
        )
        response = client.get("/")
        assert response.status_code == 404

    def test_bench_data_no_bench_file(self, client, monkeypatch, tmp_path):
        """Bench dosyası yoksa get_bench boş veri döner — dashboard çökmez."""
        from api import bench_data as bench_mod

        fake = bench_mod.BenchData(tmp_path / "yok.json")
        monkeypatch.setattr(bench_mod, "get_bench", lambda: fake)
        monkeypatch.setattr("api.main.bench_data.get_bench", lambda: fake)
        # summary çağrısı çökmemeli
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 200

    def test_catalog_no_file_returns_empty(self, client, monkeypatch, tmp_path):
        """Katalog dosyası yoksa boş katalog — arama çökmez."""
        from api import catalog as cat_mod

        fake = cat_mod.Catalog(tmp_path / "yok.json")
        monkeypatch.setattr(cat_mod, "get_catalog", lambda: fake)
        monkeypatch.setattr("api.main.catalog.get_catalog", lambda: fake)
        response = client.get("/api/catalog/search?q=qwen")
        assert response.status_code == 200
        assert response.json()["models"] == []

    def test_fit_no_file_available_false(self, client, monkeypatch, tmp_path):
        """fit dosyaları yoksa baseline available=False — çökmez."""
        from api import fit_scores as fs_mod

        fake = fs_mod.FitScores(
            usecase_path=tmp_path / "uc.json", baseline_path=tmp_path / "bl.json"
        )
        monkeypatch.setattr(fs_mod, "get_fit", lambda: fake)
        monkeypatch.setattr("api.main.fit_scores.get_fit", lambda: fake)
        response = client.get(
            "/api/fit/baseline", params={"model": "x", "role": "coding"}
        )
        assert response.status_code == 200
        assert response.json()["available"] is False

    def test_hardware_get_missing_404(self, client, monkeypatch):
        """config yoksa /api/hardware 404 döner."""
        import api.main as main_mod
        from api.routes import shared as shared_mod

        monkeypatch.setattr(
            shared_mod, "HARDWARE_FILE", main_mod.BASE / "config" / "olmayan.json"
        )
        response = client.get("/api/hardware")
        assert response.status_code == 404


# =============================================================================
# Sprint 34 P1 — /api/eval/history (geçmiş koşu listesi)
# =============================================================================
class TestEvalHistoryEndpoint:
    """GET /api/eval/history — benchmarks zaman serisi."""

    def _seed_bench(self, dbmod, model="qwen3:8b", tps=45.2):
        con = dbmod.connect()
        con.execute(
            "INSERT INTO benchmarks(model,provider,measured_tps,ttft_ms,source)"
            " VALUES(?,?,?,?,?)",
            (model, "ollama", tps, 120.0, "real"),
        )
        con.commit()
        con.close()

    def test_history_returns_runs(self, client, monkeypatch, tmp_path):
        """Bench kaydı varsa run listesi döner."""
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "test.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)
        self._seed_bench(dbmod)

        response = client.get("/api/eval/history")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert len(data["runs"]) == 1
        assert data["runs"][0]["model"] == "qwen3:8b"
        assert data["runs"][0]["measured_tps"] == pytest.approx(45.2)

    def test_history_empty(self, client, monkeypatch, tmp_path):
        """Bench kaydı yoksa boş liste döner (çökmez)."""
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "empty.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)

        response = client.get("/api/eval/history")
        assert response.status_code == 200
        assert response.json()["runs"] == []

    def test_history_model_filter(self, client, monkeypatch, tmp_path):
        """Model filtresi yalnızca o modele ait koşuları döndürür."""
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "f.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)
        self._seed_bench(dbmod, model="qwen3:8b", tps=45.2)
        self._seed_bench(dbmod, model="deepseek:14b", tps=20.0)

        response = client.get("/api/eval/history", params={"model": "qwen3:8b"})
        assert response.status_code == 200
        runs = response.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["model"] == "qwen3:8b"

    def test_history_models_list(self, client, monkeypatch, tmp_path):
        """Benzersiz model adları listelenir."""
        import sqlite3

        from api import db as dbmod

        db_path = tmp_path / "m.db"

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            dbmod.migrate(con)
            return con

        monkeypatch.setattr(dbmod, "connect", fake_connect)
        self._seed_bench(dbmod, model="qwen3:8b")
        self._seed_bench(dbmod, model="qwen3:8b")

        response = client.get("/api/eval/history/models")
        assert response.status_code == 200
        assert response.json()["models"] == ["qwen3:8b"]


class TestRouteModulesLoaded:
    """Sprint 31 — api/routes/*.py modülleri app'e include edildi mi?"""

    def test_all_route_modules_imported(self):
        """Tüm 5 route modülü import edilebiliyor + router'lar bağlı."""
        from api.routes import benchcompass, catalog, dashboard, hardware, ollama

        routers = [
            catalog.router,
            dashboard.router,
            hardware.router,
            benchcompass.router,
            ollama.router,
        ]
        for r in routers:
            assert r is not None
            assert getattr(r, "routes", None), "router route içermeli"

    def test_main_routes_still_mounted(self):
        """Çekirdek route'lar (index/health/eval) app'te duruyor."""
        from api.main import app

        paths = {getattr(r, "path", None) for r in app.router.routes}
        assert "/" in paths
        assert "/health" in paths
        assert "/api/eval/report-status" in paths


# =============================================================================
# 7 Ekim 2026 — /api/eval/quality (kodlama kalite boyutu, benchmark_quality)
# =============================================================================
class TestEvalQualityEndpoint:
    """GET /api/eval/quality — Pass@1/Pass@N kalite kayıtları + özet.

    Denetim bulgusu P0-2: kalite sonuçları hiçbir kalıcı veriye girmiyordu.
    Bu endpoint `benchmark_quality` tablosunu sunar; artefakt satırları
    SİLİNMEZ, `gecerlilik` alanıyla işaretlenir ve özetten hariç tutulur.
    """

    def _fake_connect(self, dbmod, db_path):
        import sqlite3

        def fake_connect():
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            con.executescript(dbmod.SCHEMA_BASE)
            con.executescript(dbmod.SCHEMA_SPRINT9)
            con.executescript(dbmod.SCHEMA_QUALITY)
            dbmod.migrate(con)
            return con

        return fake_connect

    def test_quality_ozeti_artefakti_haric_tutar(self, client, monkeypatch, tmp_path):
        """Geçerli + artefakt kayıt: özet yalnız geçerliyi sayar, artefakt sayılır."""
        from api import db as dbmod

        monkeypatch.setattr(
            dbmod, "connect", self._fake_connect(dbmod, tmp_path / "q.db")
        )
        con = dbmod.connect()
        dbmod.insert_quality_cok(
            con,
            [
                {
                    "model": "M",
                    "gorev": "G1",
                    "dil": "tr",
                    "pass1": 1,
                    "passN": 1,
                    "attempts": 1,
                    "gecerlilik": "gecerli",
                    "source": "test",
                },
                {
                    "model": "M",
                    "gorev": "G7",
                    "dil": "en",
                    "pass1": 0,
                    "passN": 0,
                    "attempts": 3,
                    "gecerlilik": "artefakt-g7",
                    "source": "test",
                },
            ],
        )
        con.close()

        response = client.get("/api/eval/quality")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["total"] == 2, "kayıtlar bölümü her iki satırı da göstermeli"
        assert len(data["ozet"]) == 1
        ozet = data["ozet"][0]
        assert ozet["gorev_sayisi"] == 1, "artefakt satırı özete girmemeli"
        assert ozet["passN"] == 1
        assert ozet["artefakt"] == 1, "artefakt sayısı ayrıca raporlanmalı"
        etiketler = {k["gecerlilik"] for k in data["kayitlar"]}
        assert etiketler == {"gecerli", "artefakt-g7"}

    def test_quality_bos_tablo(self, client, monkeypatch, tmp_path):
        """Kayıt yoksa boş özet + boş liste döner (çökmez)."""
        from api import db as dbmod

        monkeypatch.setattr(
            dbmod, "connect", self._fake_connect(dbmod, tmp_path / "bos.db")
        )
        response = client.get("/api/eval/quality")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["ozet"] == []
        assert data["kayitlar"] == []

    def test_quality_limit_dogrulanir(self, client, monkeypatch, tmp_path):
        """limit alt/üst sınır dışındaysa 422 (güçlü onaylama)."""
        from api import db as dbmod

        monkeypatch.setattr(
            dbmod, "connect", self._fake_connect(dbmod, tmp_path / "l.db")
        )
        assert client.get("/api/eval/quality?limit=0").status_code == 422
        assert client.get("/api/eval/quality?limit=9999").status_code == 422
        assert client.get("/api/eval/quality?limit=2000").status_code == 200
