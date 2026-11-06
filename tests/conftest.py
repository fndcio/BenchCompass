"""
Pytest merkezi fixture'ları — BenchCompass
==========================================================================
AGENTS.md §6: 3 katmanlı test mimarisi için izolasyon fixture'ları.

Önemli fixture'lar:
- tmp_root         : İzole geçici kök dizin (data/, config/, logs/). Hiçbir test
                     gerçek kullanıcı dizinine dokunmaz (AGENTS.md Local-First).
- isolated_config  : config/hardware_profile.json ve config/provider.json'ı
                     tmp_root'a kopyalar. Çıplak config okuma YASAK.
- no_network       : socket'i raise eden monkeypatch. Kazara network çağrısını yakalar.
- pytest_collection_modifyitems (autouse): tests/e2e/ yollarını otomatik `e2e`
                     marker'ı ile işaretler (AGENTS.md Y4 — "not e2e" filtresi zorunlu).

LLMFit flat layout: pythonpath = ["."] sayesinde `from api.compat import ...`
importları çalışır (pyproject.toml'da tanımlı).
"""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest


# =============================================================================
# Gerçek DB + config izolasyonu (Sprint 27 düzeltmesi)
# =============================================================================
# G10: per-test sonucunu session özetinde saymak için item stash anahtarı.
_OUTCOME_STASH = "_g10_outcome"


@pytest.fixture(autouse=True)
def _isolate_real_state(monkeypatch, tmp_path):
    """Gerçek benchmark_history.db ve config/*.json'a ASLA dokunulmaz.

    - ``api.db.DB`` → her teste izole temp DB (db.py::connect bağlantı anında okur)
    - ``api.main.HARDWARE_FILE`` / ``PROVIDER_FILE`` → izole temp kopyalar
      (``/api/provider``, ``/api/hardware`` PUT/POST endpoint'leri gerçek
      config'i kirletemez)

    ``:memory:`` / ``fake_connect`` gibi bilinçli bağlantı fixture'ları bunu
    override edebilir (zararsız).
    """
    from api import db as dbmod
    from api import main as main_mod
    from api.routes import shared as shared_mod

    monkeypatch.setattr(dbmod, "DB", tmp_path / "test_benchmark_history.db")

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    for name in ("hardware_profile.json", "provider.json"):
        src = main_mod.CONFIG_DIR / name
        if src.exists():
            shutil.copy2(src, cfg_dir / name)
    # Route modülleri shared.X üzerinden okur → hem main hem shared patch'lenir
    # (Sprint 31: yardımcılar api/routes/shared.py'ye taşındı).
    monkeypatch.setattr(main_mod, "HARDWARE_FILE", cfg_dir / "hardware_profile.json")
    monkeypatch.setattr(main_mod, "PROVIDER_FILE", cfg_dir / "provider.json")
    monkeypatch.setattr(shared_mod, "HARDWARE_FILE", cfg_dir / "hardware_profile.json")
    monkeypatch.setattr(shared_mod, "PROVIDER_FILE", cfg_dir / "provider.json")
    yield


# =============================================================================
# Proje kök dizini (fixture'ların ortak referansı)
# =============================================================================
@pytest.fixture(scope="session")
def project_root() -> Path:
    """LLMFit proje kök dizini (tests/ bir üstü)."""
    return Path(__file__).resolve().parent.parent


# =============================================================================
# İzolasyon fixture'ları
# =============================================================================
@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """İzole geçici kök dizin — data/, config/, logs/ alt klasörleriyle.

    Her test kendi tmp_root'unu alır; gerçek kullanıcı dizinine DOKUNULMAZ
    (AGENTS.md Local-First — benchmark_history.db'ye asla dokunulmaz).
    """
    root = tmp_path / "test_root"
    for sub in ("data", "config", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def isolated_config(tmp_root: Path, project_root: Path) -> Path:
    """config/ dosyalarını tmp_root'a kopyalar.

    AGENTS.md: gerçek config/hardware_profile.json'a çıplak erişim YASAK.
    Testler tmp_root/config altındaki kopya üzerinde çalışır.

    Donanım profili ve provider config'ini kopyalar. Eğer kaynak dosya yoksa
    minimal bir placeholder oluşturur (CI gibi ortamlarda config olmayabilir).
    """
    src_config = project_root / "config"
    dst_config = tmp_root / "config"
    dst_config.mkdir(parents=True, exist_ok=True)

    for cfg_name in ("hardware_profile.json", "provider.json"):
        src = src_config / cfg_name
        dst = dst_config / cfg_name
        if src.exists():
            shutil.copy2(src, dst)
        # Placeholder (CI ortamı — config dosyası yok)
        elif cfg_name == "provider.json":
            dst.write_text(
                json.dumps(
                    {"provider": "auto", "ollama_host": "http://localhost:11434"}
                ),
                encoding="utf-8",
            )
        elif cfg_name == "hardware_profile.json":
            dst.write_text(
                json.dumps(
                    {
                        "active_profile": "test-profile",
                        "profiles": [
                            {
                                "id": "test-profile",
                                "device_name": "Test Machine",
                                "vram_gb": 12.0,
                                "ram_gb": 32.0,
                            }
                        ],
                        "tier_thresholds": {
                            "vram_full_margin": 2.0,
                            "ram_full_margin": 4.0,
                            "vram_caution_margin": -1.5,
                        },
                    }
                ),
                encoding="utf-8",
            )

    return dst_config


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch):
    """socket.create_connection ve socket.socket'u raise eden monkeypatch.

    AGENTS.md Local-First: Kazara network çağrısını yakalar. Bir test bu
    fixture ile çağrılırsa ve network'e dokunmaya çalışırsa → fail.
    """

    def _raise(*_args, **_kwargs):
        raise OSError(
            "no_network fixture: network erişimi engellendi (AGENTS.md Local-First)"
        )

    monkeypatch.setattr(socket, "create_connection", _raise)
    monkeypatch.setattr(socket, "socket", _raise)
    return monkeypatch


# =============================================================================
# LLMFit'e özel fixture'lar
# =============================================================================
@pytest.fixture()
def omen_hardware():
    """Standart test donanımı: HP Omen Max 16 (12GB VRAM, 32GB RAM).

    AGENTS.md §1.6: Tier formulu tek yerde (api/compat.py). Testler bu
    donanımı kullanarak tier hesaplamasını doğrular.
    """
    from api.schemas import HardwareProfileEntry

    return HardwareProfileEntry(
        id="omen-max-16",
        device_name="HP Omen Max 16 (test)",
        gpu="RTX 5070 Ti Laptop",
        vram_gb=12.0,
        ram_gb=32.0,
        cpu="AMD Ryzen AI 9",
    )


@pytest.fixture()
def default_thresholds():
    """Standart tier eşikleri (Bölüm 2.2 varsayılanları)."""
    from api.schemas import TierThresholds

    return TierThresholds()


# =============================================================================
# Auto-marker: tests/e2e/ → `e2e`, integration dosyaları → `integration`
# AGENTS.md Y4: "not e2e" filtresi ZORUNLU. Bu autouse fixture hatırlatıcıdır.
# =============================================================================
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Toplanan testlere otomatik marker ekle.

    - tests/e2e/ altındaki dosyalar → `e2e` marker
    - integration içeren dosyalar → `integration` marker
    Böylece `pytest -m "not e2e"` yanlışlıkla E2E'yi çalıştırmaz.
    """
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "/e2e/" in path or path.endswith("_e2e.py"):
            item.add_marker(pytest.mark.e2e)
        if "integration" in path.lower():
            item.add_marker(pytest.mark.integration)


# =============================================================================
# Opsiyonel CLI flag'ler
# =============================================================================
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="E2E testlerini dahil et (varsayılan: pytest -m 'not e2e' ile atlanır).",
    )
    parser.addoption(
        "--run-real-llmfit",
        action="store_true",
        default=False,
        help="Gerçek llmfit CLI'si gerektiren testleri çalıştır (varsayılan: atla).",
    )
    parser.addoption(
        "--run-ollama",
        action="store_true",
        default=False,
        help="Ollama servisi gerektiren testleri çalıştır (varsayılan: atla).",
    )


# =============================================================================
# G10 — Bileşen 1: Test sonuç kaydedici (data/test-intelligence/history.jsonl)
# AGENTS.md §5 G10: sonuç/süre/head append-only kaydedilir; kaydedici hata
# verirse test sürecini ASLA bozmaz (try/except sarmalı — Y3 suppress değil,
# koşulu değiştirmez).
# =============================================================================
def _record_test_history(session: pytest.Session, exitstatus: int) -> None:
    """Session özetini history.jsonl'e yazar; hata → sessizce geç."""
    try:
        from scripts.test_history import (
            append_record,
            build_session_record,
            git_head,
            history_path,
            prune_history,
        )

        passed = failed = skipped = 0
        for item in session.items:
            outcome = item.stash.get(_OUTCOME_STASH, "unknown")
            if outcome == "passed":
                passed += 1
            elif outcome == "failed":
                failed += 1
            elif outcome == "skipped":
                skipped += 1
        rec = build_session_record(
            exitstatus=exitstatus,
            passed=passed,
            failed=failed,
            skipped=skipped,
            nodeids=passed + failed + skipped,
            head=git_head(),
        )
        append_record(history_path(), rec)
        # Büyüme valfi: her session sonunda nodeid başına son 50 kayıt tutulur
        # (docs/process/test-zekasi-altyapisi.md — dosya sınırsız büyümez).
        prune_history(history_path())
    except Exception:  # noqa: BLE001 — kaydedici test sonucunu asla bozmaz
        pass


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _record_test_history(session, exitstatus)


def pytest_runtest_logreport(report) -> None:
    """Per-test kaydı: yalnızca test başarı durumu değiştiğinde (outcome)."""
    if not report.when == "call":
        return
    try:
        from scripts.test_history import (
            append_record,
            git_head,
            history_path,
            make_test_record,
        )

        item = getattr(report, "item", None)
        if item is not None:
            item.stash[_OUTCOME_STASH] = report.outcome
        rec = make_test_record(
            nodeid=str(report.nodeid),
            outcome=str(report.outcome),
            duration=float(report.duration or 0.0),
            head=git_head(),
        )
        append_record(history_path(), rec)
    except Exception:  # noqa: BLE001 — kaydedici test sonucunu asla bozmaz
        pass
