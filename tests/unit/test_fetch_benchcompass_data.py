"""
Unit tests — scripts/fetch_benchcompass_data.py (Sprint 19 gerçek veri indirici)
==========================================================================
Ağ erişimi OLMAYAN saf mantık testleri: download_one (local dosya yazımı),
check (durum raporu). Gerçek URL istekleri test edilmez (no_network fixture).
"""

from __future__ import annotations

import json

from scripts import fetch_benchcompass_data as fetcher


def test_download_one_writes_file(tmp_path, monkeypatch):
    """download_one içerik yazar ve bayt boyutu döner (ağ isteği mock'lu)."""
    monkeypatch.setattr(fetcher, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        fetcher,
        "_http_get",
        lambda *a, **kw: b'{"models": [{"name": "test"}]}',
    )

    size = fetcher.download_one("test.json", "https://example.com/x")

    assert size == len(b'{"models": [{"name": "test"}]}')
    assert (tmp_path / "test.json").read_bytes() == b'{"models": [{"name": "test"}]}'


def test_download_one_creates_data_dir(tmp_path, monkeypatch):
    """data/ dizini yoksa download_one oluşturur."""
    nested = tmp_path / "nested" / "data"
    monkeypatch.setattr(fetcher, "DATA_DIR", nested)
    monkeypatch.setattr(fetcher, "_http_get", lambda *a, **kw: b"abc")

    fetcher.download_one("f.json", "https://example.com/f")

    assert nested.is_dir()
    assert (nested / "f.json").exists()


def test_check_reports_missing(tmp_path):
    """data/ yoksa check boş dict döner (hata değil)."""
    monkeypatch_data = tmp_path / "nonexistent-data"
    monkeypatch_data.unlink(missing_ok=True)
    # DATA_DIR'i geçici olarak değiştir
    import scripts.fetch_benchcompass_data as m

    orig = m.DATA_DIR
    m.DATA_DIR = monkeypatch_data
    try:
        assert m.check() == {}
    finally:
        m.DATA_DIR = orig


def test_check_reports_record_count(tmp_path, monkeypatch):
    """JSON liste dosyası kayıt sayısını raporlar."""
    target = tmp_path / "data"
    target.mkdir(exist_ok=True)
    (target / "hf_models.json").write_text(
        json.dumps([{"name": "a"}, {"name": "b"}]), encoding="utf-8"
    )
    (target / "benchmark_cache.json").write_text(json.dumps([1]), encoding="utf-8")
    (target / "use_case_benchmarks.json").write_text(
        json.dumps({"families": []}), encoding="utf-8"
    )
    (target / "baselines.json").write_text(
        json.dumps({"baselines": []}), encoding="utf-8"
    )

    monkeypatch.setattr(fetcher, "DATA_DIR", target)

    status = fetcher.check()

    assert status["hf_models.json"]["record_count"] == 2
    assert status["benchmark_cache.json"]["record_count"] == 1
    assert "keys" in status["use_case_benchmarks.json"]


def test_check_reports_parse_error(tmp_path, monkeypatch):
    """Bozuk JSON parse_error flag döndürür."""
    target = tmp_path / "data"
    target.mkdir(exist_ok=True)
    (target / "hf_models.json").write_text("not json {{{", encoding="utf-8")

    monkeypatch.setattr(fetcher, "DATA_DIR", target)

    status = fetcher.check()
    assert status["hf_models.json"]["parse_error"] is True


def test_sources_have_expected_files():
    """SOURCES listesi 4 beklenen dosyayı içerir (katalog + benchmark)."""
    names = [rel for rel, _, _ in fetcher.SOURCES]
    assert "hf_models.json" in names
    assert "benchmark_cache.json" in names
    assert "use_case_benchmarks.json" in names
    assert "baselines.json" in names
    # URL'ler raw.githubusercontent üzerinden resmî repo'ya işaret eder
    urls = [url for _, url, _ in fetcher.SOURCES]
    assert all("raw.githubusercontent.com/AlexsJones/llmfit/main" in u for u in urls)
