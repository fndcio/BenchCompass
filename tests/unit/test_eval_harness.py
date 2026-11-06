"""
Unit tests for tools/eval_harness — kodlama değerlendirme motoru (minimum set).

Motor dis denetim sonrasi scratch/coding_eval'den tools/eval_harness'a tasindi
(v0.27.0 borcu): bugune kadar 0 test + lint disiydi. Burada yalnizca saf
fonksiyonlar test edilir; ag/LLM bagimli yollar mock'suz KOŞULMAZ.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# tools/ geliştirici dizinidir, yayınlama senkronuna girmez (Local-First).
# SRC dışı (DST/public) ağaçta koşulurında sessizce atla.
pytest.importorskip("tools.eval_harness")

from tools.eval_harness import deep_eval as D  # noqa: E402
from tools.eval_harness import harness as H  # noqa: E402
from tools.eval_harness import stage_b2 as B2  # noqa: E402
from tools.eval_harness.stage_b2 import igne_dogru_mu, sentetik_repo
from tools.eval_harness.verify_report_claims import RESULTS


# ---------------------------------------------------------------------------
# Veri yollari — tasima sonrasi bütünlük
# ---------------------------------------------------------------------------
def test_data_paths_point_to_scratch_coding_eval():
    """Ham kanıt taşınmadı: raw/ ve results/ scratch/coding_eval altında kalmalı."""
    assert H.RAW.exists() and (H.RAW / "bonsai2_mtp").exists()
    assert H.SONUC.exists()
    assert Path(RESULTS).parts[-3:] == ("scratch", "coding_eval", "results")


# ---------------------------------------------------------------------------
# kod_cikar — model yanıtından kod bloğu çıkarımı
# ---------------------------------------------------------------------------
def test_kod_cikar_python_blok():
    """Tek python bloğu döner, çevre metin atılır."""
    yazi = "İşte çözüm:\n```python\nx = 1\n```\nAçıklama."
    assert H.kod_cikar(yazi) == "x = 1"


def test_kod_cikar_coklu_blok_birlesir():
    """Birden çok blok çift satırsonu ile birleşir."""
    yazi = "```python\na = 1\n```\norta\n```py\nb = 2\n```"
    assert H.kod_cikar(yazi) == "a = 1\n\nb = 2"


def test_kod_cikar_bloksuz_ham_donmez():
    """Kod bloğu yoksa metin olduğu gibi (kırpılmış) döner — boş string değil."""
    assert H.kod_cikar("  sadece metin  ") == "sadece metin"


# ---------------------------------------------------------------------------
# tekrar_orani — döngüsel üretim tespiti (3/4/8-gram)
# ---------------------------------------------------------------------------
def test_tekrar_orani_kisa_metin_sifir():
    """Token sayısı n-gram boyundan azsa oran 0.0 — tavan bozulmaz."""
    assert H.tekrar_orani("tek iki")["gram3"] == 0.0


def test_tekrar_orani_dongusel_metin_yuksek():
    """Aynı 2 kelimelik döngü sürekli üretilirse gram8 tavana yaklaşır.

    'a b ' kalıbı tekrar eder: en sık 8-gram penceresi toplam token oranını
    domine eder (0.5 üstü = döngü şüphesi, harness eşiğiyle uyumlu sinyal).
    """
    metin = "a b " * 50
    assert H.tekrar_orani(metin)["gram8"] >= 0.5


def test_tekrar_orani_benzersiz_metin_dusuk():
    """Benzersiz tokenli metinde tekrar oranı düşük kalır."""
    metin = " ".join(f"kelime{i}" for i in range(100))
    assert H.tekrar_orani(metin)["gram8"] < 0.1


# ---------------------------------------------------------------------------
# sentetik_repo — B2 context-needle senaryo üreticisi
# ---------------------------------------------------------------------------
def test_sentetik_repo_uzunluk_hedefe_yaklasir():
    """Üretilen repo hedef token sayısının en az %90'ına ulaşır (yaklaşım/2.5)."""
    repo = sentetik_repo(500)
    tahmini_token = len(repo) / 2.5
    assert tahmini_token >= 450


def test_sentetik_repo_gizli_kural_icerir():
    """İğne (apply_discount/BSAVE12) HER hedef boyutta tam bir kez yerleşmelidir.

    Regresyon: eski koşul (i == hedef_token // 30) hiç tutmuyordu — iğne
    repoya hiç girmiyor, üretim boyutu 12510 dahil. Bu yüzden 2 Ekim B2
    needle ölçümü geçersiz: "fonksiyon yok" diyen doğru modeli yanlış
    işaretlendi (bkz. kodlama raporu v4 düzeltme notu).
    """
    for hedef in (300, 5009, 7828, 12510):
        repo = sentetik_repo(hedef)
        assert repo.count("def apply_discount") == 1, (
            f"hedef={hedef}: iğne fonksiyonu tam 1 kez olmalı"
        )
        assert repo.count("BSAVE12") == 2, (
            f"hedef={hedef}: iğne içindeki 2 BSAVE12 geçişi (yorum+kod) beklenir"
        )


# ---------------------------------------------------------------------------
# igne_dogru_mu — P0-1 (denetim raporu 2026-10-05) buluşsal düzeltmesi
# ---------------------------------------------------------------------------
def test_igne_kesilen_cevap_dogru_sayilmaz():
    """finish=length ile kesilen cevaptaki '88' alıntısı ARTIK doğru sayılmaz.

    Regresyon: bonsai2/freetoken'ın 5 Ekim '✅'ları tam bu hata yüzünden
    temiz kanıt sayılmıyordu (rapor P0-1; kanıt raw/bonsai2_mtp/igne_12510.txt
    — 'Let's verify mentally' ile kesiliyor, içinden '88' geçiyor).
    """
    kesilen = (
        "We need answer in Turkish likely. User asks: find apply_discount, "
        "what exactly does apply_discount(100, 'BSAVE12') return? The rule "
        "shows 0.88 factor. Let's verify mentally: 100 * 0.88 = 88.0 so the"
    )
    assert igne_dogru_mu(kesilen, "length") is False


def test_igne_temiz_88_gecer():
    assert igne_dogru_mu("88.0", "stop") is True
    assert igne_dogru_mu("apply_discount(100, 'BSAVE12') → 88", "stop") is True


def test_igne_alt_dizi_yanlislari_elenir():
    """'188.0' içindeki '88' ve '0.88' artık geçerli sayılmaz (alt-dizi bug'ı)."""
    assert igne_dogru_mu("188.0", "stop") is False
    assert igne_dogru_mu("factor is 0.88", "stop") is False
    assert igne_dogru_mu("12.0", "stop") is False


def test_igne_bos_cevap_gecersiz():
    assert igne_dogru_mu("", "stop") is False
    assert igne_dogru_mu("fonksiyon yok", "stop") is False


def test_igne_aciklama_ile_gecer():
    """Nihai cevap 88.0 ise aradaki 'BSAVE12'/'0.88' alıntıları engel değil."""
    cevap = (
        "apply_discount(100, 'BSAVE12') calls round(price * 0.88, 2) "
        "because code is BSAVE12, so it returns 88.0"
    )
    assert igne_dogru_mu(cevap, "stop") is True


# ---------------------------------------------------------------------------
# P1-2: G3 prompt sızıntısı — gizli test beklentisi prompt'a yazılmaz
# ---------------------------------------------------------------------------
def test_g3_prompt_gizli_test_beklentisi_sizdirmaz():
    """P1-2 (denetim raporu 2026-10-05): eski prompt 'len(values) - window + 1'
    beklentisini birebir söylüyordu — gizli testler okuma sınavına dönüştü.

    Yeni protokol: sözleşme GÖRÜNÜR testlerle verilir; sızıntı cümlesi yoktur.
    """
    for dil in ("en", "tr"):
        prompt = H.TASKS["G3"][dil]
        assert "window + 1" not in prompt, f"G3_{dil}: sızıntı cümlesi geri geldi"
        assert "test_full_window_only" in prompt, (
            f"G3_{dil}: sözleşme görünür testlerle verilmeli"
        )


# ---------------------------------------------------------------------------
# P1-5: meta disiplini — harness_sha + üstüne-yazma arşivi
# ---------------------------------------------------------------------------
def test_harness_sha_uzunluk_ve_tutarlilik():
    sha = H.harness_sha()
    assert len(sha) == 12
    assert sha == H.harness_sha()


def test_sonuc_yaz_ustune_yazmadan_once_arsivler(tmp_path):
    """Sonuç üstüne yazılmadan önce results/arsiv/'e tarihli kopya alınmalı."""
    yol = tmp_path / "ornek.json"
    H.sonuc_yaz(yol, {"v": 1})
    H.sonuc_yaz(yol, {"v": 2})
    arsivler = list((tmp_path / "arsiv").glob("ornek__*.json"))
    assert len(arsivler) == 1
    assert json.loads(arsivler[0].read_text(encoding="utf-8"))["v"] == 1
    assert json.loads(yol.read_text(encoding="utf-8"))["v"] == 2


# ---------------------------------------------------------------------------
# G7 (6 Ekim 2026 denetim bulgusu): prompt "yalnizca duzeltilmis fonksiyonu
# dondur" der, test modulu IKI isim import eder -> collection ImportError ile
# TUM modeller "basarisiz" gorunuyordu. Bu blok artefakti kalici kapatir.
# ---------------------------------------------------------------------------
def _g7_sandbox(tmp_path: Path, model_kodu: str) -> Path:
    """G7 için model çıktısını kompoze edip gerçek pytest sandbox'ı kurar."""
    sandbox = tmp_path / "g7"
    sandbox.mkdir()
    (sandbox / "solution.py").write_text(
        D.H.modul_kompoze("G7", model_kodu), encoding="utf-8"
    )
    (sandbox / "test_visible.py").write_text(
        D.H.TASKS["G7"]["visible"], encoding="utf-8"
    )
    (sandbox / "test_hidden.py").write_text(D.H.TASKS["G7"]["hidden"], encoding="utf-8")
    return sandbox


def test_modul_kompoze_taban_yoksa_cikti_aynen_doner():
    """G1/G3/G6'da taban modül yok — kompozisyon çıktıyı DEĞİŞTİRMEMELİ."""
    kod = "def f():\n    return 1\n"
    assert H.modul_kompoze("G1", kod) == kod
    assert H.modul_kompoze("G3", kod) == kod
    assert H.modul_kompoze("G6", kod) == kod


def test_g7_kompoze_modul_test_sozlesmesini_karsilar():
    """Regresyon: model YALNIZCA düzeltilmiş fonksiyonu döndürse bile test
    modülünün import ettiği `create_session` modülde bulunmalı."""
    sadece_duzeltme = "def validate_session(token):\n    return None\n"
    modul = D.H.modul_kompoze("G7", sadece_duzeltme)
    ns: dict = {}
    exec(compile(modul, "solution.py", "exec"), ns)  # noqa: S102
    assert "create_session" in ns, "taban modül create_session sağlamıyor"
    assert "validate_session" in ns, "model çıktısı modüle girmemiş"
    # Sonraki tanım kazanır: modelin sürümü tabanı ezmeli.
    assert ns["validate_session"]("yok") is None


def test_g7_gizli_test_oracle_hatali_tabanda_duser(tmp_path):
    """ORACLE: taban (hatalı) `validate_session` testleri GEÇMEMELİ.

    Bu test, gizli/görünür testlerin gerçekten ayırt edici olduğunun kanıtıdır;
    yanlış yazılmış bir test tüm modelleri sessizce "fail" gösterirdi.
    """
    sandbox = _g7_sandbox(tmp_path, "")
    v_ok, v_log = D.H.pytest_kos(sandbox, "test_visible.py")
    assert v_ok is False, f"hatalı taban görünür testleri geçti: {v_log}"


def test_g7_gizli_test_oracle_referansta_gecer(tmp_path):
    """ORACLE: referans düzeltme hem görünür hem gizli testleri GEÇMELİ."""
    sandbox = _g7_sandbox(tmp_path, D.G7_REFERANS)
    v_ok, v_log = D.H.pytest_kos(sandbox, "test_visible.py")
    h_ok, h_log = D.H.pytest_kos(sandbox, "test_hidden.py")
    assert v_ok, f"referans görünürde düştü: {v_log}"
    assert h_ok, f"referans gizlide düştü: {h_log}"


def test_g7_taban_modul_testsiz_kalmasin():
    """G7 taban modülü ve oracle tanımlı olmalı (artefakt geri gelmesin)."""
    assert "base" in D.H.TASKS["G7"], "G7 taban modülü kaydı silinmiş"
    assert "def create_session" in D.H.TASKS["G7"]["base"]
    assert "time.time() - s['start'] > s['ttl']" in D.G7_REFERANS


# ---------------------------------------------------------------------------
# P1-3 duzeltmesi: derinlik katsayisi tek kaynak + modul bazli provenance
# ---------------------------------------------------------------------------
def test_derinlik_katsayisi_uretim_ve_olcumde_ayni():
    """Ölçülen derinlik üretici hedefiyle uyuşmalı.

    Regresyon: üretici /2.5, ölçüm /4 kullanıyordu → 12510 hedefi 7889 olarak
    raporlanıyordu (1.6× sapma); denetimde "12.5K etiketi tutarsız" bulgusu.
    """
    for hedef in (300, 5000, 12510):
        repo = B2.sentetik_repo(hedef)
        olcum = round(len(repo) / B2.KARAKTER_TOKEN_ORANI)
        assert olcum >= hedef * 0.95, (
            f"hedef={hedef}: ölçülen derinlik {olcum} hedefin altında"
        )


def test_modul_sha_modul_bazli_ve_12_hane():
    """Provenance: her modül kendi SHA'sını yazar (harness.py sabit değil)."""
    assert len(H.modul_sha("harness.py")) == 12
    assert H.harness_sha() == H.modul_sha("harness.py")
    farkli = [H.modul_sha(x) for x in ("harness.py", "stage_b2.py", "deep_eval.py")]
    assert len(set(farkli)) == 3, "modüller aynı SHA'yı yazıyor — provenance yanıltıcı"
    assert H.modul_sha("olmayan_dosya.py") == "yok"


def test_pytest_kos_collection_error_basarisiz_doner(tmp_path):
    """Toplama (collection) hatası 'geçti' sayılmamalı — ImportError yolu."""
    sandbox = tmp_path / "ce"
    sandbox.mkdir()
    (sandbox / "solution.py").write_text("x = 1\n", encoding="utf-8")
    (sandbox / "test_visible.py").write_text(
        "from solution import yok\n\n\ndef test_x():\n    assert True\n",
        encoding="utf-8",
    )
    ok, log = H.pytest_kos(sandbox, "test_visible.py")
    assert ok is False
    assert "yok" in log or "ImportError" in log or "error" in log.lower()


def test_tam_tur_ve_hedefli_ayrimi_gercek_kosularda_korunur():
    """Tam tur kanonik, hedefli koşu ayrı dosya — ikisi çakışmamalı."""
    gor = ("G1", "G3", "G6", "G7")
    assert {
        D.hedef_dosya_adi("m", gor, ("tr", "en")),
        D.hedef_dosya_adi("m", ("G7",), ("tr", "en")),
    } == {
        "m_deep.json",
        "m_deep_hedefli.json",
    }


# ---------------------------------------------------------------------------
# P2 cilası (denetim raporu 2026-10-05 §3-8): fence regex, sıra, seed
# ---------------------------------------------------------------------------
def test_kod_cikar_tek_satirlik_fence():
    """Regresyon: `\\n` şartı yüzünden tek satırlık fence HİÇ yakalanmıyordu →
    ham metin (fence işaretleriyle) solution.py'ye yazılıp collection error
    üretiyordu."""
    assert H.kod_cikar("```python x = 1```") == "x = 1"
    assert H.kod_cikar("```py f(1)```") == "f(1)"
    assert H.kod_cikar("İşte:\n```return 42```\nson") == "return 42"


def test_kod_cikar_crlf_satir_sonu():
    """Windows satır sonu (\\r\\n) ile gelen blok da çıkarılmalı."""
    assert H.kod_cikar("```python\r\nx = 1\r\n```") == "x = 1"


def test_kod_cikar_bilinmeyen_dil_ham_metne_duser():
    """Bilinmeyen dil etiketli ÇOK SATIRLI fence KASITLI olarak çıkarılmaz:
    sessizce yanlış kod üretmek yerine ham metne düşer."""
    yazi = "```javascript\nvar x = 1;\n```"
    assert H.kod_cikar(yazi) == yazi.strip()


def test_kod_cikar_bilinmeyen_dil_tek_satirda_sessiz_gecmemeli():
    """Tek satırlık bilinmeyen etiket gövdede kalır → Python testinde syntax
    error = dürüst başarısızlık; asla geçerli kod gibi sessizce GEÇMEMELİ."""
    cikti = H.kod_cikar("```javascript var x = 1;```")
    assert "javascript" in cikti, "etiket gövdeden sessizce atılmamalı"
    assert cikti != "var x = 1;"


def test_kosu_sirasi_varsayilan_sirali():
    """--karistir kapalıyken sıra deterministik ve eski kayıtlarla uyumlu."""
    assert D.kosu_sirasi(("G1", "G3"), ("tr", "en")) == [
        ("G1", "tr"),
        ("G1", "en"),
        ("G3", "tr"),
        ("G3", "en"),
    ]


def test_kosu_sirasi_karistir_deterministik_ve_kume_korunur():
    """Aynı seed → aynı sıra; küme korunur; karıştırma gerçekten etkili."""
    g, d = ("G1", "G3", "G6", "G7"), ("tr", "en")
    a1 = D.kosu_sirasi(g, d, karistir=True, seed=7)
    a2 = D.kosu_sirasi(g, d, karistir=True, seed=7)
    assert a1 == a2, "aynı seed aynı sırayı vermeli (tekrarlanabilirlik)"
    assert sorted(a1) == sorted(D.kosu_sirasi(g, d)), "küme değişmemeli"
    assert a1 != D.kosu_sirasi(g, d), "karıştırma sırayı değiştirmeli"


def test_seed_uret_cagrisina_iletilir_ve_kayda_gecer(monkeypatch, tmp_path):
    """`deneme_kos` seed'i ağ sınırına (uret_ollama) iletmeli ve kayda geçmeli.

    Yalnız dış bağımlılık (Ollama/HTTP) izole edilir; harness mantığı gerçek
    (pytest_kos gerçekten koşar).
    """
    yakalanan: dict = {}

    def sahte_uret_ollama(
        model_id, prompt, max_tokens, temp=0.0, num_ctx=None, seed=None
    ):
        yakalanan.update({"seed": seed, "temp": temp})
        return {
            "icerik": "```python\nx = 1\n```",
            "tg": 1.0,
            "tg_kaynagi": "eval_duration",
            "ttft": 0.1,
            "tokens": 3,
            "finish": "stop",
            "thinking": "kapali",
        }

    monkeypatch.setattr(D.H, "uret_ollama", sahte_uret_ollama)
    kayit = D.deneme_kos(
        "ollama", "http://yok", "m", "G1", "tr", tmp_path, 2, temp=0.7, seed=42
    )
    assert yakalanan["seed"] == 42, "seed isteğe iletilmedi"
    assert yakalanan["temp"] == 0.7
    assert kayit["seed"] == 42, "seed kayda geçmedi"
    assert isinstance(kayit["visible"], bool) and isinstance(kayit["hidden"], bool)
