"""
Unit testler — benchmark_quality katmanı (7 Ekim 2026, kullanıcı onaylı
additive tablo).

Denetim bulgusu: kodlama değerlendirmesinin kalite boyutu (Pass@1/Pass@N,
visible/hidden) hiçbir kalıcı veriye girmiyordu; `benchmarks` yalnız hız tutar.
Bu testler şemayı, idempotentliği ve özet fonksiyonunun uydurma yapmadığını
kilitler. Gerçek `benchmark_history.db`'ye DOKUNULMAZ (in-memory SQLite).
"""

from __future__ import annotations

import sqlite3

import pytest

from api import db as dbmod


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(dbmod.SCHEMA_QUALITY)
    yield c
    c.close()


def test_sema_kolonlari_beklenen_kumeyi_icerir(con):
    kolonlar = {r["name"] for r in con.execute("PRAGMA table_info(benchmark_quality)")}
    beklenen = {
        "id",
        "model",
        "gorev",
        "dil",
        "deneme",
        "visible",
        "hidden",
        "pass1",
        "passN",
        "attempts",
        "tg",
        "tg_kaynagi",
        "tokens",
        "finish",
        "thinking",
        "harness_sha",
        "seed",
        "source",
        "gecerlilik",
        "notlar",
        "created_at",
    }
    assert beklenen <= kolonlar


def test_sema_idempotent(con):
    """İki kez executescript hata vermez, veri kaybettirmez."""
    con.execute(
        "INSERT INTO benchmark_quality (model, gorev, dil, passN) VALUES ('m','G1','tr',1)"
    )
    con.commit()
    con.executescript(dbmod.SCHEMA_QUALITY)
    assert con.execute("SELECT COUNT(*) FROM benchmark_quality").fetchone()[0] == 1


def test_insert_ve_fetch_roundtrip(con):
    kid = dbmod.insert_quality(
        con,
        {
            "model": "rc-gemma4-udq4kxl:latest",
            "gorev": "G7",
            "dil": "en",
            "deneme": 1,
            "visible": 1,
            "hidden": 1,
            "pass1": 1,
            "passN": 1,
            "attempts": 1,
            "tg": 58.9,
            "tg_kaynagi": "eval_duration",
            "tokens": 84,
            "finish": "stop",
            "thinking": "kapali",
            "harness_sha": "abc123def456",
            "seed": None,
            "source": "rc_gemma4_deep_hedefli",
            "gecerlilik": "gecerli",
            "notlar": None,
        },
    )
    assert kid > 0
    kayit = dbmod.fetch_quality(con)[0]
    assert kayit["gorev"] == "G7"
    assert kayit["passN"] == 1
    assert kayit["visible"] == 1 and kayit["hidden"] == 1
    assert kayit["tg_kaynagi"] == "eval_duration"
    assert kayit["harness_sha"] == "abc123def456"
    assert kayit["gecerlilik"] == "gecerli"


def test_eksik_alanlar_null_kalir(con):
    """Uydurma YASAK: verilmeyen alan NULL olur, 0'a düşmez."""
    dbmod.insert_quality(con, {"model": "m", "gorev": "G1"})
    kayit = dbmod.fetch_quality(con)[0]
    assert kayit["pass1"] is None and kayit["passN"] is None
    assert kayit["tg"] is None and kayit["seed"] is None


def test_toplu_insert_ve_ozet(con):
    dbmod.insert_quality_cok(
        con,
        [
            {
                "model": "A",
                "gorev": "G1",
                "dil": "tr",
                "pass1": 1,
                "passN": 1,
                "attempts": 1,
                "tg": 50.0,
            },
            {
                "model": "A",
                "gorev": "G7",
                "dil": "en",
                "pass1": 0,
                "passN": 1,
                "attempts": 3,
                "tg": 40.0,
            },
            {
                "model": "B",
                "gorev": "G1",
                "dil": "tr",
                "pass1": 0,
                "passN": 0,
                "attempts": 3,
                "tg": 30.0,
            },
        ],
    )
    ozet = {r["model"]: r for r in dbmod.quality_summary(con)}
    assert ozet["A"]["gorev_sayisi"] == 2
    assert ozet["A"]["pass1"] == 1 and ozet["A"]["passN"] == 2
    assert ozet["A"]["ort_deneme"] == 2.0
    assert ozet["B"]["passN"] == 0
    # Sıralama: Pass@N azalan, eşitlikte ortalama deneme artan
    assert [r["model"] for r in dbmod.quality_summary(con)] == ["A", "B"]


def test_ozet_artefakt_satirlarini_haric_tutar(con):
    """Artefakt satırlar özet metriklerine girmez ama SAYILIR.

    Regresyon riski: WHERE ile filtrelemek artefakt sayacını da sıfırlıyordu
    (koşullu toplamaya geçildi). Geçersiz ölçüm geçerli veriyle karışmamalı.
    """
    dbmod.insert_quality_cok(
        con,
        [
            {
                "model": "M",
                "gorev": "G1",
                "dil": "tr",
                "pass1": 1,
                "passN": 1,
                "attempts": 1,
                "gecerlilik": "gecerli",
            },
            {
                "model": "M",
                "gorev": "G7",
                "dil": "en",
                "pass1": 0,
                "passN": 0,
                "attempts": 3,
                "gecerlilik": "artefakt-g7",
            },
        ],
    )
    ozet = dbmod.quality_summary(con)
    assert len(ozet) == 1
    assert ozet[0]["gorev_sayisi"] == 1 and ozet[0]["passN"] == 1
    assert ozet[0]["artefakt"] == 1
    assert dbmod.fetch_quality(con) and len(dbmod.fetch_quality(con)) == 2


def test_ozet_kategorileri_karistirmaz(con):
    """Metodoloji karışımı YASAK: Pass@1/Pass@N YALNIZ kodlama görevlerinden.

    `benchmark_quality` üç tür ölçüm taşır (kodlama görevi, B2 iğne senaryosu,
    n örnekli varyans koşusu); bunları tek başlıkta toplamak yanlış skor üretir.
    """
    dbmod.insert_quality_cok(
        con,
        [
            {
                "model": "M",
                "gorev": "G1",
                "dil": "tr",
                "pass1": 1,
                "passN": 1,
                "attempts": 1,
                "gecerlilik": "gecerli",
            },
            {
                "model": "M",
                "gorev": "G7",
                "dil": "en",
                "pass1": 0,
                "passN": 1,
                "attempts": 2,
                "gecerlilik": "gecerli",
            },
            {
                "model": "M",
                "gorev": "B2-needle-12510",
                "pass1": 1,
                "passN": 1,
                "attempts": 1,
                "gecerlilik": "gecerli",
            },
            {
                "model": "M",
                "gorev": "G6-n3",
                "dil": "tr",
                # Varyans satırında passN = başarı SAYISI, attempts = örneklem (n)
                "pass1": 1,
                "passN": 1,
                "attempts": 3,
                "gecerlilik": "gecerli",
            },
        ],
    )
    ozet = dbmod.quality_summary(con)[0]
    assert ozet["gorev_sayisi"] == 4, "toplam kayıt sayısı korunmalı"
    # Kodlama metrikleri YALNIZ G1+G7'den
    assert ozet["kodlama_gorev"] == 2
    assert ozet["pass1"] == 1 and ozet["passN"] == 2
    assert ozet["ort_deneme"] == 1.5
    # İğne ve varyans AYRI raporlanır
    assert ozet["needle_senaryo"] == 1 and ozet["needle_passN"] == 1
    # Varyans paydası SATIR değil ÖRNEKLEM: 1 başarı / 3 örnek
    assert ozet["varyans_kosu"] == 3 and ozet["varyans_passN"] == 1


def test_ozet_guvenilir_hiz_yalniz_beyan_edilen_kaynaktan(con):
    """char_tahmin kaynaklı sahte hız (433 tok/s) 'guvenilir' ortalamaya girmemeli.

    `timings` (llama.cpp /completion timings.predicted_per_second) sunucunun
    ölçtüğü decode süresidir → eval_duration/usage ile aynı sınıfta güvenilir.
    """
    dbmod.insert_quality_cok(
        con,
        [
            {
                "model": "fork-char",
                "gorev": "G1",
                "tg": 433.0,
                "tg_kaynagi": "char_tahmin",
                "gecerlilik": "gecerli",
            },
            {
                "model": "ollama",
                "gorev": "G1",
                "tg": 56.0,
                "tg_kaynagi": "eval_duration",
                "gecerlilik": "gecerli",
            },
            {
                "model": "fork-timings",
                "gorev": "G1",
                "tg": 51.1,
                "tg_kaynagi": "timings",
                "gecerlilik": "gecerli",
            },
        ],
    )
    ozet = {r["model"]: r for r in dbmod.quality_summary(con)}
    assert ozet["fork-char"]["ort_tg"] == 433.0
    assert ozet["fork-char"]["ort_tg_guvenilir"] is None, (
        "char_tahmin güvenilir sayılmamalı"
    )
    assert ozet["ollama"]["ort_tg_guvenilir"] == 56.0
    assert ozet["fork-timings"]["ort_tg_guvenilir"] == 51.1, (
        "timings (llama.cpp /completion) güvenilir sayılmalı"
    )


def test_bos_toplu_insert_sifir_doner(con):
    assert dbmod.insert_quality_cok(con, []) == 0
    assert dbmod.quality_summary(con) == []


def test_migrate_eski_kalite_tablosuna_kolon_ekler():
    """7 Ekim öncesi yaratılmış (gecerlilik'siz) tablo migrate ile güncellenir.

    `CREATE TABLE IF NOT EXISTS` mevcut tabloya kolon eklemez; bu yüzden
    additive ALTER yolu (QUALITY_COLUMNS) şart. Idempotent olmalı.
    """
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE benchmark_models (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE benchmarks (id INTEGER PRIMARY KEY, model TEXT);
        CREATE TABLE benchmark_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            gorev TEXT NOT NULL,
            dil TEXT,
            pass1 INTEGER,
            passN INTEGER,
            source TEXT
        );
        """
    )
    eklenen = dbmod.migrate(c)
    assert "benchmark_quality.gecerlilik" in eklenen
    assert "benchmark_quality.notlar" in eklenen
    kolonlar = {r["name"] for r in c.execute("PRAGMA table_info(benchmark_quality)")}
    assert {"gecerlilik", "notlar"} <= kolonlar
    # Idempotent: ikinci çağrı hiçbir şey eklemez
    assert dbmod.migrate(c) == []
    c.close()
