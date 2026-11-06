"""tests/unit/test_release_sync_regression.py — Vitrin Senkronizasyon ve Sanitizasyon Regresyon Testi.

sync_to_github_release mantığının:
1. Model ağırlıklarını (*.gguf, *.bin, *.safetensors) ve logları asla kopyalamadığını,
2. Kişisel yolları (developer, ai_workspace) başarıyla sanitize ettiğini doğrular (ADR-0012, Y24/Y25).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# Bu test SRC'ye özgüdür: sync script'i yayına çıkmaz (EXCLUDED_FROM_PUBLISH).
# DST/public ağacında modül yoksa koleksiyon hatası vermek yerine atla.
_sync = pytest.importorskip("scripts.sync_to_github_release")
sanitize_file = _sync.sanitize_file


def test_sanitize_file_removes_personal_paths(tmp_path: Path) -> None:
    test_file = tmp_path / "test_doc.md"
    original_text = (
        "Model konumu: c:\\Users\\developer\\Desktop\\\llmfit-persistent-center/model.bin\n"
        "Geliştirici: developer, proje: n"
    )
    test_file.write_text(original_text, encoding="utf-8")

    sanitize_file(test_file)

    sanitized_text = test_file.read_text(encoding="utf-8")
    assert "developer" not in sanitized_text
    assert "ai_workspace" not in sanitized_text
    assert "c:\\Users\\developer" not in sanitized_text


def test_ignore_patterns_block_large_models(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()

    # Sahte dosyalar
    (src_dir / "code.py").write_text("print('hello')", encoding="utf-8")
    (src_dir / "model.gguf").write_bytes(b"GGUF_TEST_BYTES")
    (src_dir / "weights.safetensors").write_bytes(b"SAFETENSORS_BYTES")
    (src_dir / "run.log").write_text("Log text", encoding="utf-8")

    # sync_to_github_release'deki ignore pattern'leri
    ignores = shutil.ignore_patterns(
        "__pycache__",
        "*.gguf",
        "*.safetensors",
        "*.bin",
        "*.ftw",
        "*.pt",
        "*.log",
    )

    shutil.copytree(src_dir, dst_dir, ignore=ignores)

    assert (dst_dir / "code.py").exists()
    assert not (dst_dir / "model.gguf").exists()
    assert not (dst_dir / "weights.safetensors").exists()
    assert not (dst_dir / "run.log").exists()


def test_vitrin_readme_changelog_and_hardware_template_survive_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tam senkron vitrin README/CHANGELOG'unu ve anonim donanım şablonunu ezmemeli.

    Regresyon: 6 Kasım 2026 öncesi senkron SRC README/CHANGELOG'unu DST'ye kopyalıyordu;
    public-plan'a göre vitrin sürümleri bilinçli olarak farklıdır (iç sprint/kapı
    ayrıntısı yayınlanmaz). Kırık davranış tespit edildi, koruma listesine alındı.
    """
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "config").mkdir(parents=True)
    (dst / "config").mkdir(parents=True)
    (src / ".github" / "workflows").mkdir(parents=True)
    (dst / ".github" / "workflows").mkdir(parents=True)

    (src / "README.md").write_text(
        "# SRC README\nAGENTS.md sprint detayı\n", encoding="utf-8"
    )
    (src / "CHANGELOG.md").write_text("# SRC CHANGELOG\n", encoding="utf-8")
    (src / "LICENSE").write_text("MIT — SRC çoklu telif\n", encoding="utf-8")
    (src / "config" / "hardware_profile.json").write_text(
        '{"active_profile": "gercek-donanim"}', encoding="utf-8"
    )
    (src / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI (G1-G7)\n", encoding="utf-8"
    )
    (src / ".github" / "workflows" / "e2e-nightly.yml").write_text(
        "name: E2E Nightly\n", encoding="utf-8"
    )
    (dst / "README.md").write_text("# BenchCompass vitrin\n", encoding="utf-8")
    (dst / "CHANGELOG.md").write_text("## [0.28.0]\n", encoding="utf-8")
    (dst / "LICENSE").write_text("MIT — fndcio\n", encoding="utf-8")
    (dst / "config" / "hardware_profile.json").write_text(
        '{"active_profile": "anonim-sablon"}', encoding="utf-8"
    )
    (dst / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\n", encoding="utf-8"
    )

    class _Basarili:
        returncode = 0

    monkeypatch.setattr(_sync, "SRC", src)
    monkeypatch.setattr(_sync, "DST", dst)
    monkeypatch.setattr(
        _sync,
        "subprocess",
        type(
            "_SahteSubprocess", (), {"run": staticmethod(lambda *a, **k: _Basarili())}
        ),
    )

    _sync.sync_and_sanitize()

    assert (dst / "README.md").read_text(encoding="utf-8") == "# BenchCompass vitrin\n"
    assert (dst / "CHANGELOG.md").read_text(encoding="utf-8") == "## [0.28.0]\n"
    assert (dst / "LICENSE").read_text(encoding="utf-8") == "MIT — fndcio\n"
    assert "anonim-sablon" in (dst / "config" / "hardware_profile.json").read_text(
        encoding="utf-8"
    )
    assert ".github" not in _sync.SYNC_DIRS
    assert (dst / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    ) == "name: CI\n"
    assert not (dst / ".github" / "workflows" / "e2e-nightly.yml").exists()
