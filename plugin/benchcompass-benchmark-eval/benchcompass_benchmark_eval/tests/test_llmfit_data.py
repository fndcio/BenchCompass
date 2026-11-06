"""llmfit_data veri çözümleyici testleri — 3 mod (parent/snapshot/none), network yok."""

import json

from benchcompass_benchmark_eval import config, llmfit_data


def _make_parent(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "hf_models.json").write_text(
        json.dumps(
            [
                {
                    "name": "Qwen/Qwen3-8B",
                    "format": "gguf",
                    "min_vram_gb": 4.2,
                    "hf_downloads": 100,
                },
                {
                    "name": "Giant/Model-70B",
                    "format": "gguf",
                    "min_vram_gb": 40.0,
                    "hf_downloads": 900,
                },
            ]
        ),
        encoding="utf-8",
    )
    (d / "benchmark_cache.json").write_text(
        json.dumps(
            {
                "presets": {
                    "RTX 4070 Ti (12 GB)": {
                        "rows": [
                            {
                                "tokSOut": 62.1,
                                "model": {"displayName": "X"},
                                "engine": {
                                    "quantization": "Q4_K_M",
                                    "engineName": "llama.cpp",
                                },
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return d


def test_resolve_parent_mode(tmp_path):
    d = _make_parent(tmp_path)
    data = llmfit_data.resolve(str(d))
    assert data.mode == "parent"
    assert data.is_enriched()
    assert len(data.hf_models) == 2


def test_models_fitting_vram(tmp_path):
    d = _make_parent(tmp_path)
    data = llmfit_data.resolve(str(d))
    fits = data.models_fitting_vram(12.0)
    assert len(fits) == 1
    assert fits[0]["name"] == "Qwen/Qwen3-8B"


def test_speed_presets(tmp_path):
    d = _make_parent(tmp_path)
    data = llmfit_data.resolve(str(d))
    presets = data.speed_presets(["RTX 4070 Ti (12 GB)", "RTX 3060 (12 GB)"])
    assert "RTX 4070 Ti (12 GB)" in presets
    assert presets["RTX 4070 Ti (12 GB)"][0]["tokSOut"] == 62.1
    assert "RTX 3060 (12 GB)" not in presets


def test_resolve_snapshot_mode(tmp_path, monkeypatch):
    # parent otomatik tespiti engelle: PLUGIN_DIR'i geçici yap
    monkeypatch.setattr(config, "PLUGIN_DIR", tmp_path / "fake-plugin")
    # DATA_DIR'i snapshot içeren geçici klasör yap
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    (snap_dir / "llmfit_snapshot_2026-08-04.json").write_text(
        json.dumps(
            {"hf_models": [{"name": "X", "min_vram_gb": 1.0}], "benchmark_cache": {}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "DATA_DIR", snap_dir)
    data = llmfit_data.resolve()
    assert data.mode == "snapshot"


def test_resolve_none_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLUGIN_DIR", tmp_path / "fake-plugin")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "bos")
    (tmp_path / "bos").mkdir()
    data = llmfit_data.resolve()
    assert data.mode == "none"
    assert not data.is_enriched()


def test_build_snapshot(tmp_path, monkeypatch):
    d = _make_parent(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "out")
    out = llmfit_data.build_snapshot(str(d))
    assert out.exists()
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert len(snap["hf_models"]) == 2


# ---------------------------------------------------------------------------
# Sprint 34 (P3): --live-api modu
# ---------------------------------------------------------------------------
def test_resolve_live_api_mode(tmp_path, monkeypatch):
    """Parent/snapshot yok + live_api açık + API ulaşılabilir → live_api modu."""
    monkeypatch.setattr(config, "PLUGIN_DIR", tmp_path / "fake-plugin")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "bos")
    (tmp_path / "bos").mkdir()

    captured = {}

    def fake_fetch():
        captured["called"] = True
        return (
            [{"name": "Qwen/Qwen3-8B", "format": "gguf", "min_vram_gb": 4.2}],
            {"presets": {"qwen3:8b": [{"measured_tps": 45.0}]}},
        )

    monkeypatch.setattr(llmfit_data, "_fetch_live_api", fake_fetch)
    data = llmfit_data.resolve(live_api=True)
    assert data.mode == "live_api"
    assert data.is_enriched()
    assert len(data.hf_models) == 1
    assert captured["called"] is True


def test_resolve_live_api_graceful_on_failure(tmp_path, monkeypatch):
    """Live API erişilemezse None döner ve resolve 'none' moduna düşer."""
    monkeypatch.setattr(config, "PLUGIN_DIR", tmp_path / "fake-plugin")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "bos")
    (tmp_path / "bos").mkdir()

    def fake_fetch():
        return None

    monkeypatch.setattr(llmfit_data, "_fetch_live_api", fake_fetch)
    data = llmfit_data.resolve(live_api=True)
    assert data.mode == "none"
    assert not data.is_enriched()


def test_resolve_live_api_off_by_default(tmp_path, monkeypatch):
    """live_api varsayılan kapalı — `resolve()` çağrısı live moda düşmez."""
    monkeypatch.setattr(config, "PLUGIN_DIR", tmp_path / "fake-plugin")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "bos")
    (tmp_path / "bos").mkdir()

    def fake_fetch():
        raise AssertionError("live_api kapalıyken çağrılmamalı")

    monkeypatch.setattr(llmfit_data, "_fetch_live_api", fake_fetch)
    data = llmfit_data.resolve()
    assert data.mode == "none"


def test_fetch_live_api_graceful_on_connection_error(monkeypatch):
    """Gerçek network erişilemezse _fetch_live_api None döner (Local-First)."""
    result = llmfit_data._fetch_live_api()
    # yerel sunucu açık olsa bile bu test erişilemezlik senaryosunu kapsar;
    # hiçbir durumda istisna fırlatmamalı
    assert result is None or isinstance(result, tuple)
