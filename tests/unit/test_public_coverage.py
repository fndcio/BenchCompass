"""Vitrin kapsam artırma (kapsam < fail_under düzeltmesi)."""

import subprocess
from types import SimpleNamespace

import api.system_info as si


def test_detect_gpu_vram_nvidia_smi(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="NVIDIA Test GPU, 12288, 4096\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = si.detect_gpu_vram()
    assert out["detected"] is True
    assert out["gpu_name"] == "NVIDIA Test GPU"
    assert out["vram_total_mb"] == 12288.0


def test_detect_gpu_vram_fallback(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi yok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = si.detect_gpu_vram()
    assert out["detected"] is False
    assert out["source"] == "hardware_profile_fallback"


def test_get_hardware_specs():
    specs = si.get_hardware_specs()
    assert "os" in specs
    assert "gpu" in specs


def test_detect_gpu_vram_empty_output_fallback(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = si.detect_gpu_vram()
    assert out["detected"] is False


def test_detect_gpu_vram_short_parts_fallback(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="onlyone\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = si.detect_gpu_vram()
    assert out["detected"] is False


def test_detect_gpu_vram_bad_profile_fallback(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    bad = tmp_path / "hardware_profile.json"
    bad.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(si, "HARDWARE_FILE", bad)
    out = si.detect_gpu_vram()
    assert out["detected"] is False
    assert out["source"] == "hardware_profile_fallback"
