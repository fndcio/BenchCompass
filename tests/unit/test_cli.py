"""tests/unit/test_cli.py - BenchCompass CLI testleri."""

from __future__ import annotations

import pytest

from api.cli import main


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """--help parametresi ile yardım metni döner."""
    with pytest.raises(SystemExit) as exc:
        main.__wrapped__ if hasattr(main, "__wrapped__") else None
        import sys

        sys.argv = ["benchcompass", "--help"]
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "BenchCompass" in captured.out
    assert "serve" in captured.out
    assert "collect" in captured.out
    assert "check" in captured.out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    """--version parametresi ile versiyon metni döner."""
    import sys

    sys.argv = ["benchcompass", "--version"]
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "0.28.0-rc.2" in captured.out


def test_cli_collect_backend_help(capsys: pytest.CaptureFixture[str]) -> None:
    """collect --help komutunda --backend seçeneği yer alır."""
    import sys

    sys.argv = ["benchcompass", "collect", "--help"]
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--backend" in captured.out


# ---------------------------------------------------------------------------
# share (P1-4) — _share gövdesi: DB okuma + sanitizasyon + dry-run URL yolları
# ---------------------------------------------------------------------------
def _izole_benchmark_db(tmp_path, monkeypatch):
    """_share'in DB okumasını izole tmp SQLite'a yönlendirir."""
    from api import db as dbmod

    monkeypatch.setattr(dbmod, "DB", tmp_path / "izole.db")
    con = dbmod.connect()
    con.close()
    return dbmod


def test_cli_share_dry_run_pii_temiz(tmp_path, monkeypatch, capsys) -> None:
    """share --dry-run: DB'den son ölçümü okur, sanitizasyon yazar, göndermez."""
    import sys

    dbmod = _izole_benchmark_db(tmp_path, monkeypatch)
    # Son ölçüm kaydı: _share bu satırı okumalı (74-78 dalı)
    con = dbmod.connect()
    con.execute(
        "INSERT INTO benchmarks(model, provider, measured_tps) VALUES(?, ?, ?)",
        ("qwen3:8b-test", "ollama", 45.0),
    )
    con.commit()
    con.close()

    sys.argv = ["benchcompass", "share", "--dry-run"]
    main()

    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    # DB'den okunan model görünmeli (74-78 dalı koştu)
    assert "qwen3" in out.lower()
    # GPU adı tier'a anonimleşmiş olmalı
    assert "High-End GPU" in out
    # PII sızıntısı yok
    assert "developer" not in out


def test_cli_share_url_yolu(tmp_path, monkeypatch, capsys) -> None:
    """dry-run'sız share: GitHub Issue URL'i üretilir (network YOK, string üretimi)."""
    import sys

    _izole_benchmark_db(tmp_path, monkeypatch)
    sys.argv = ["benchcompass", "share"]
    main()

    out = capsys.readouterr().out
    assert "Paylaşım bağlantısı" in out
    # URL sanitizasyonlu payload ile üretilir — PII taşımaz
    assert "developer" not in out
