"""Integration testler: api/routes/asr.py — ASR teşhis endpoint'leri.

0.28.0-rc.2 denetim kapanışı: Özellik 5 için 3 katmanlı test mimarisinin
(AGENTS.md §6) entegrasyon katmanı. Gerçek FastAPI uygulaması + TestClient;
model taraması tmp dizine yönlendirilir (kullanıcı dizini taranmaz).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import api.routes.asr as asr_mod
from api.main import app

client = TestClient(app)

_REQUIRED_FIELDS = (
    "ok",
    "runtime_available",
    "runtime_engine",
    "ffmpeg_available",
    "missing_prerequisites",
    "detected_models",
    "candidate_count",
    "total_size_mb",
    "truncated",
    "scan_error",
    "recommendation",
)


def test_asr_status_schema_both_aliases(monkeypatch, tmp_path) -> None:
    """İki alias path de aynı tam şemayı döner (yeni alanlar dahil)."""
    monkeypatch.setattr(asr_mod, "_asr_search_dirs", lambda: [tmp_path / "yok"])
    for path in ("/api/asr/status", "/api/telemetry/asr"):
        res = client.get(path)
        assert res.status_code == 200
        data = res.json()
        for field in _REQUIRED_FIELDS:
            assert field in data, f"{path} yanıtında {field} eksik"
        assert data["candidate_count"] == 0
        assert data["truncated"] is False
        assert data["scan_error"] is None


def test_asr_status_reports_detected_models(monkeypatch, tmp_path) -> None:
    """Taranan tmp deposundaki whisper dosyaları sayı/boyut olarak raporlanır."""
    depot = tmp_path / "ollama-models"
    depot.mkdir()
    (depot / "whisper-small.bin").write_bytes(b"x" * (2 * 1024**2))

    monkeypatch.setattr(asr_mod, "_asr_search_dirs", lambda: [depot])
    data = client.get("/api/asr/status").json()

    assert data["candidate_count"] == 1
    assert data["total_size_mb"] == 2.0
    assert data["detected_models"][0]["name"] == "whisper-small.bin"


def test_asr_status_scan_error_visible_in_response(monkeypatch) -> None:
    """Tarama hatası HTTP 200 içinde dürüstçe raporlanır (ok alanı kalır)."""

    class _BrokenDir:
        def exists(self) -> bool:
            return True

        def rglob(self, pattern: str):
            raise OSError("disk hatası")

    monkeypatch.setattr(asr_mod, "_asr_search_dirs", lambda: [_BrokenDir()])
    data = client.get("/api/asr/status").json()

    assert data["ok"] is True
    assert data["scan_error"] is not None
    assert "disk hatası" in data["scan_error"]
