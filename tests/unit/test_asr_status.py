"""tests/unit/test_asr_status.py — ASR Ses Modelleri Teşhis Paneli Testleri.

0.28.0-rc.2 denetim kapanışı: şema-ötesi davranış kapsamı eklendi —
runtime tespit sıralaması (dürüst motor etiketleri), tarama dizinleri
(Ollama dahil), sonuç sınırı ve tarama hatasının yutulmaması.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import api.routes.asr as asr_mod
from api.main import app

client = TestClient(app)


def test_asr_status_endpoint() -> None:
    """GET /api/asr/status ve /api/telemetry/asr dürüst teşhis raporu döner."""
    for path in ("/api/asr/status", "/api/telemetry/asr"):
        res = client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "runtime_available" in data
        assert "runtime_engine" in data
        assert "missing_prerequisites" in data
        assert "detected_models" in data
        assert "candidate_count" in data
        assert "total_size_mb" in data
        assert "recommendation" in data
        # Denetim kapanışı alanları: sınır bayrağı + tarama hatası yutulmaz
        assert "truncated" in data
        assert "scan_error" in data
        assert isinstance(data["missing_prerequisites"], list)
        assert isinstance(data["detected_models"], list)


# ---------------------------------------------------------------------------
# _detect_asr_runtime — dürüst motor etiketleme sırası
# ---------------------------------------------------------------------------
def _patch_runtime_env(monkeypatch, which_bins: set[str], specs: set[str]):
    """shutil.which ve importlib.util.find_spec'i sahte ortama bağlar."""
    monkeypatch.setattr(
        asr_mod.shutil,
        "which",
        lambda name: f"/fake/{name}" if name in which_bins else None,
    )
    monkeypatch.setattr(
        asr_mod.importlib.util,
        "find_spec",
        lambda name: object() if name in specs else None,
    )


def test_runtime_whisper_cli_binary_first(monkeypatch) -> None:
    """whisper-cli ikilisi en yüksek öncelik — whisper.cpp etiketi alır."""
    _patch_runtime_env(
        monkeypatch, {"whisper-cli", "whisper", "ffmpeg"}, {"faster_whisper"}
    )
    engine, available, ffmpeg = asr_mod._detect_asr_runtime()
    assert engine == "whisper.cpp (whisper-cli)"
    assert available is True
    assert ffmpeg is True


def test_runtime_whisper_cli_is_openai_whisper_not_cpp(monkeypatch) -> None:
    """pip openai-whisper'ın 'whisper' komutu whisper.cpp DEĞİLDİR (denetim düzeltmesi)."""
    _patch_runtime_env(monkeypatch, {"whisper", "ffmpeg"}, set())
    engine, available, ffmpeg = asr_mod._detect_asr_runtime()
    assert engine == "openai-whisper (cli)"
    assert available is True
    assert ffmpeg is True


def test_runtime_faster_whisper_module(monkeypatch) -> None:
    _patch_runtime_env(monkeypatch, set(), {"faster_whisper"})
    engine, available, _ = asr_mod._detect_asr_runtime()
    assert engine == "faster-whisper (python)"
    assert available is True


def test_runtime_transformers_torch(monkeypatch) -> None:
    """transformers+torch kuruluysa ASR runtime'ı mevcut sayılır (CHANGELOG vaadi)."""
    _patch_runtime_env(monkeypatch, set(), {"transformers", "torch"})
    engine, available, _ = asr_mod._detect_asr_runtime()
    assert engine == "transformers/pytorch (python)"
    assert available is True


def test_runtime_none(monkeypatch) -> None:
    _patch_runtime_env(monkeypatch, set(), set())
    engine, available, ffmpeg = asr_mod._detect_asr_runtime()
    assert engine == "none"
    assert available is False
    assert ffmpeg is False


# ---------------------------------------------------------------------------
# _asr_search_dirs — Ollama dizini keşfi
# ---------------------------------------------------------------------------
def test_search_dirs_include_ollama_default(monkeypatch) -> None:
    """OLLAMA_MODELS yoksa ~/.ollama/models varsayılan depo olarak taranır."""
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    dirs = asr_mod._asr_search_dirs()
    assert (Path.home() / ".ollama" / "models") in dirs


def test_search_dirs_env_override(monkeypatch, tmp_path) -> None:
    """OLLAMA_MODELS tanımlıysa önceliklidir."""
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "custom-ollama"))
    dirs = asr_mod._asr_search_dirs()
    assert (tmp_path / "custom-ollama") in dirs
    assert (Path.home() / ".ollama" / "models") not in dirs


# ---------------------------------------------------------------------------
# _scan_asr_models — eşleşme, limit, hata dürüstlüğü
# ---------------------------------------------------------------------------
def test_scan_finds_whisper_files_only(monkeypatch, tmp_path) -> None:
    model_dir = tmp_path / "depot"
    model_dir.mkdir()
    (model_dir / "whisper-large-v3.bin").write_bytes(b"x" * 2048)
    (model_dir / "llama-weights.gguf").write_bytes(b"y" * 512)
    (model_dir / "asr-model.pt").write_bytes(b"z" * 1024)
    monkeypatch.setattr(asr_mod, "_asr_search_dirs", lambda: [model_dir])

    detected, truncated, scan_error = asr_mod._scan_asr_models()

    assert truncated is False
    assert scan_error is None
    names = sorted(m["name"] for m in detected)
    assert names == ["asr-model.pt", "whisper-large-v3.bin"]
    whisper = next(m for m in detected if m["name"] == "whisper-large-v3.bin")
    assert whisper["size_mb"] == round(2048 / (1024**2), 2)
    assert whisper["format"] == "bin"


def test_scan_result_limit_truncates(monkeypatch, tmp_path) -> None:
    """Sonut sınırı aşılırsa truncated=True — liste sessizce kesilmez."""
    model_dir = tmp_path / "depot"
    model_dir.mkdir()
    for i in range(5):
        (model_dir / f"whisper-{i:02d}.bin").write_bytes(b"x" * 16)
    monkeypatch.setattr(asr_mod, "_asr_search_dirs", lambda: [model_dir])
    monkeypatch.setattr(asr_mod, "_SCAN_MAX_RESULTS", 2)

    detected, truncated, scan_error = asr_mod._scan_asr_models()

    assert len(detected) == 2
    assert truncated is True
    assert scan_error is None


def test_scan_error_is_surfaced_not_swallowed(monkeypatch) -> None:
    """Tarama hatası yutulmaz: scan_error alanına taşınır (Y3/Y5)."""

    class _BrokenDir:
        def exists(self) -> bool:
            return True

        def rglob(self, pattern: str):
            raise OSError("izin yok")

    monkeypatch.setattr(asr_mod, "_asr_search_dirs", lambda: [_BrokenDir()])

    detected, truncated, scan_error = asr_mod._scan_asr_models()

    assert detected == []
    assert truncated is False
    assert scan_error is not None
    assert "izin yok" in scan_error
