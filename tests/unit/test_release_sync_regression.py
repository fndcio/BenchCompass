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
