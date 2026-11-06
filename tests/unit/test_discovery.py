"""tests/unit/test_discovery.py — Zero-Config Model Keşfi Endpoint ve Önbellek Testi.

Kapsam genişletmesi (CI Coverage onarımı): whitelist güvenlik kuralı ve tam
tarama yolu (INSERT + fit_level üç dalı + önbellek hit + silinen temizlik)
İZOLE SQLite + sahte GGUF dosyalarıyla doğrulanır — gerçek C:\AI_Models
dizinine dokunulmaz (Y18).
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from api import db as dbmod
from api.main import app
from api.routes import discovery

client = TestClient(app)


def _izole_db(tmp_path, monkeypatch) -> None:
    """Gerçek benchmark_history.db'ye dokunmadan izole şema kurar.

    BASE_SCAN_DIR da boş tmp'ye yönlendirilir — endpoint testleri gerçek
    C:\AI_Models taramasına düşmez (ilk koşumda 300s+ timeout'un kök nedeni).
    """
    monkeypatch.setattr(dbmod, "DB", tmp_path / "izole.db")
    bos_kok = tmp_path / "bos_tarama"
    bos_kok.mkdir()
    monkeypatch.setattr(discovery, "BASE_SCAN_DIR", bos_kok)
    con = dbmod.connect()
    con.close()


def test_get_local_models_endpoint(tmp_path, monkeypatch) -> None:
    _izole_db(tmp_path, monkeypatch)
    response = client.get("/api/models/local-fs")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert "total_models" in data
    assert "hardware" in data
    assert isinstance(data["models"], list)
    if data["total_models"] > 0:
        model = data["models"][0]
        assert "file_name" in model
        assert "size_gb" in model
        assert "fit_level" in model
        assert "vram_required_gb" in model


def test_rescan_local_models_endpoint(tmp_path, monkeypatch) -> None:
    _izole_db(tmp_path, monkeypatch)
    response = client.post("/api/models/local-fs/rescan")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert "message" in data
    assert isinstance(data["models"], list)


# ---------------------------------------------------------------------------
# Whitelist güvenlik kuralı
# ---------------------------------------------------------------------------
def test_is_path_allowed_whitelist() -> None:
    """Var olan whitelist kökü ('data') altındaki yol kabul, dışındaki red."""
    # Pozitif: repo kökündeki data/ whitelist'te (cwd = repo kökü, pytest rootdir)
    assert discovery._is_path_allowed(Path("data") / "hf_models.json") is True
    # Negatif: whitelist dışı sistem dizini
    assert discovery._is_path_allowed(Path("C:/Windows/System32/evil.gguf")) is False


# ---------------------------------------------------------------------------
# Tam tarama yolu — izole BASE_SCAN_DIR + sahte GGUF dosyaları
# ---------------------------------------------------------------------------
SAHTE_META = {
    "architecture": "llama",
    "quant_type": "Q4_K_M",
    "context_length": 4096,
    "general_name": "sahne-model",
    "tensor_count": 42,
    "error": None,
}


def _sahte_gguf_dizini(tmp_path, monkeypatch, vram: float = 0.001268):
    """3 sahte .gguf dosyası + izole tarama kökü + mock metadata kurar.

    Boyutlar MB seviyesinde tutulur (GB truncate NTFS'te sparse değil → gerçek
    yazma = dakikalar; ilk koşumda timeout'un kök nedeni). vram orantılı
    sahtelenir: PERFECT ≤ 1.15×size, WARNING ≤ 1.25×vram bantları üç dalı da
    tetikler.
    """
    _izole_db(tmp_path, monkeypatch)
    scan_dir = tmp_path / "gguf_kok"
    scan_dir.mkdir()
    mb = 1024 * 1024
    boyutlar = {
        "m_perfect.gguf": 1 * mb,  # needed=0.001124 ≤ vram → PERFECT
        "m_warning.gguf": int(1.3 * mb),  # needed=0.001495 ≤ 1.25×vram → WARNING
        "m_large.gguf": 2 * mb,  # needed=0.002248 > 1.25×vram → TOO_LARGE
    }
    for ad, boyut in boyutlar.items():
        (scan_dir / ad).write_bytes(b"\x00" * boyut)
    monkeypatch.setattr(discovery, "BASE_SCAN_DIR", scan_dir)
    monkeypatch.setattr(discovery, "read_gguf_metadata", lambda p: dict(SAHTE_META))
    monkeypatch.setattr(discovery, "get_hardware_specs", lambda: {"vram_gb": vram})
    return scan_dir, boyutlar


def test_scan_tam_yol_insert_ve_fit_seviyeleri(tmp_path, monkeypatch) -> None:
    """Tarama: header parse → INSERT → kayıt alanları + sıralama sözleşmesi.

    Not: MB boyutlu dosyalar round(size/1GiB, 2) ile size_gb=0.0'a yuvarlanır →
    fit bantları (PERFECT/WARNING/TOO_LARGE) burada ayrışmaz; o dallar
    `test_fit_level_bantlari` ile SAF yoldan kapatılır (GB truncate yazma
    tuzağına düşmeden).
    """
    _sahte_gguf_dizini(tmp_path, monkeypatch)

    res = discovery.scan_and_sync_local_models(force_rescan=False)
    assert len(res) == 3
    adlar = {r["file_name"] for r in res}
    assert adlar == {"m_perfect.gguf", "m_warning.gguf", "m_large.gguf"}

    # MB dosyalar → size_gb 0.0 → _fit_level(0.0, vram) hep PERFECT
    assert all(r["fit_level"] == "PERFECT" for r in res)

    # Sıralama sözleşmesi: size_gb azalan
    boyutlar = [r["size_gb"] for r in res]
    assert boyutlar == sorted(boyutlar, reverse=True)

    # DB'ye gerçekten yazıldı mı?
    con = dbmod.connect()
    kayit = con.execute(
        "SELECT architecture, quant_type FROM local_models_cache WHERE file_name = ?",
        ("m_perfect.gguf",),
    ).fetchone()
    con.close()
    assert kayit["architecture"] == "llama"
    assert kayit["quant_type"] == "Q4_K_M"


# ---------------------------------------------------------------------------
# _fit_level — saf bant testleri (dosyasız; üç dal + sınır)
# ---------------------------------------------------------------------------
def test_fit_level_bantlari() -> None:
    """Üç bant + sınır değerleri: PERFECT/WARNING/TOO_LARGE ayrımı."""
    f = discovery._fit_level
    # PERFECT: gereksinim VRAM içinde
    assert f(10.0, 12.0) == "PERFECT"
    assert f(12.0, 12.0) == "PERFECT"  # sınır: tam eşit
    # WARNING: %15 paylı gereksinim %25 banda sığar
    assert f(13.0, 12.0) == "WARNING"
    assert f(15.0, 12.0) == "WARNING"  # sınır: tam 1.25×vram
    # TOO_LARGE: banda da sığmaz
    assert f(15.1, 12.0) == "TOO_LARGE"
    assert f(24.0, 12.0) == "TOO_LARGE"


def test_scan_ikinci_kos_cache_hit_kullanir(tmp_path, monkeypatch) -> None:
    """mtime+size eşleşen dosyada header parse ATLANIR (önbellek hit)."""
    _sahte_gguf_dizini(tmp_path, monkeypatch)
    ilk = discovery.scan_and_sync_local_models(force_rescan=False)
    assert len(ilk) == 3

    # İkinci koşta parse çağrılmamalı — sayaçlı mock
    cagri_sayaci = {"n": 0}

    def sayac_meta(p):
        cagri_sayaci["n"] += 1
        return dict(SAHTE_META)

    monkeypatch.setattr(discovery, "read_gguf_metadata", sayac_meta)
    ikinci = discovery.scan_and_sync_local_models(force_rescan=False)
    assert len(ikinci) == 3
    assert cagri_sayaci["n"] == 0, "değişmemiş dosyada header parse atlanmalı"


def test_scan_silinen_dosya_cache_temiizler(tmp_path, monkeypatch) -> None:
    """Dosyası silinen kayıt taramada önbellekten düşer."""
    scan_dir, _ = _sahte_gguf_dizini(tmp_path, monkeypatch)
    assert len(discovery.scan_and_sync_local_models()) == 3

    (scan_dir / "m_perfect.gguf").unlink()
    res = discovery.scan_and_sync_local_models()
    adlar = {r["file_name"] for r in res}
    assert "m_perfect.gguf" not in adlar

    con = dbmod.connect()
    kalan = con.execute(
        "SELECT COUNT(*) FROM local_models_cache WHERE file_name = ?",
        ("m_perfect.gguf",),
    ).fetchone()[0]
    con.close()
    assert kalan == 0


def test_scan_meta_hatali_dosya_atlanir(tmp_path, monkeypatch) -> None:
    """Header parse hata döndürürse dosya sonuçlara/DB'ye girmez."""
    _izole_db(tmp_path, monkeypatch)
    scan_dir = tmp_path / "gguf_kok"
    scan_dir.mkdir()
    p = scan_dir / "bozuk.gguf"
    p.write_bytes(b"\x00" * (1024 * 1024))  # 1 MB — GB truncate yazma tuzağına düşme
    monkeypatch.setattr(discovery, "BASE_SCAN_DIR", scan_dir)
    monkeypatch.setattr(
        discovery, "read_gguf_metadata", lambda p: {"error": "bozuk header"}
    )
    monkeypatch.setattr(discovery, "get_hardware_specs", lambda: {"vram_gb": 12.0})

    res = discovery.scan_and_sync_local_models()
    assert res == []
    con = dbmod.connect()
    n = con.execute("SELECT COUNT(*) FROM local_models_cache").fetchone()[0]
    con.close()
    assert n == 0


def test_scan_force_rescan_cachei_sifirlar(tmp_path, monkeypatch) -> None:
    """force_rescan=True cache'i siler ve yeniden tam parse yapar."""
    scan_dir, _ = _sahte_gguf_dizini(tmp_path, monkeypatch)
    assert len(discovery.scan_and_sync_local_models()) == 3

    con = dbmod.connect()
    before = con.execute("SELECT COUNT(*) FROM local_models_cache").fetchone()[0]
    con.close()
    assert before == 3

    # İçeriği değişmiş dosya + force → yeniden parse
    time.sleep(0.02)  # mtime çözünürlüğü
    p = scan_dir / "m_warning.gguf"
    p.write_bytes(b"\x01" * (int(1.3 * 1024 * 1024) + 512))
    cagri = {"n": 0}

    def sayac(p):
        cagri["n"] += 1
        return dict(SAHTE_META)

    monkeypatch.setattr(discovery, "read_gguf_metadata", sayac)
    res = discovery.scan_and_sync_local_models(force_rescan=True)
    assert len(res) == 3
    assert cagri["n"] == 3, "force_rescan tüm dosyaları yeniden parse etmeli"
