"""Unit tests — Gerçek Dünya Test Paketi ham kanıt regresyonu
==========================================================================
``tools/real_world/`` altındaki değerlendirme betikleri (``real_world_suite.py``,
``real_world_suite_part2.py``, ``eval_all_models_suite.py``,
``eval_math_and_reasoning.py``, ``test_thinking_trap.py``,
``eval_bonsai_realworld.py``) canlı model/Ollama gerektirdiği için CI'da
koşulamaz. Ancak ürettikleri sonuç JSON'ları artık ``tests/fixtures/real_world/``
altında **izlenen** kanıt olarak yaşar (RC Faz 3 — scratch/ bağımlılığı bitti).

Bu modül **artefakt düzeyinde yapısal değişmezleri** kilitler: sayılar,
kimlikler ve özet↔detay tutarlılığı doğrudan commit'li dosya içeriğinden
türetilmiştir (Y25 — "uydurma iğne" yasağı). Bir JSON elle düzenlenir, kayıt
düşer/çoğalır veya özet alanı detaylarla çelişirse bu testler kırmızı olur.

Kapsam dışı bırakılanlar (dürüst boşluk listesi):
- Canlı yeniden ölçüm (model/GPU gerektirir) — bu testler sadece kanıtı korur.
- ``hiz_yeniden_olcum_2026-10-06.json`` içinde görev prompt'unun istediği
  ``trust`` alanı **gerçekte yok** (bkz. test_hiz_remeasurement docstring'i);
  hız/güven etiketi ``tests/unit/test_label_speed_trust.py`` kapsamındadır.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

import pytest

# =============================================================================
# Artefakt yolları ve commit'li beklenen kimlikler (kayıttan birebir)
# =============================================================================
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "real_world"
SCRATCH_DIR = REPO_ROOT / "scratch"

REAL_WORLD_MAIN = "real_world_results.json"
REAL_WORLD_PART2 = "real_world_results_part2.json"
REAL_WORLD_BONSAI = "real_world_results_bonsai.json"
EVAL_ALL_MODELS = "eval_all_models_matrix.json"
EVAL_MATH_REASONING = "eval_math_and_reasoning_results.json"
EVAL_BONSAI = "eval_bonsai_matrix.json"
THINKING_TRAP = "thinking_trap_results.json"
HIZ_OLCUM = "hiz_yeniden_olcum_2026-10-06.json"
EMBEDDING_OLCUM = "embeddinggemma2_olcum_2026-10-06.json"

# Kök tip sözleşmesi: dict → model sözlüğü/meta, list → kayıt dizisi.
ROOT_TYPES = {
    REAL_WORLD_MAIN: dict,
    REAL_WORLD_PART2: dict,
    REAL_WORLD_BONSAI: dict,
    EVAL_ALL_MODELS: list,
    EVAL_MATH_REASONING: list,
    EVAL_BONSAI: list,
    THINKING_TRAP: list,
    HIZ_OLCUM: dict,
    EMBEDDING_OLCUM: dict,
}

# real_world_results*.json görev anahtarları (dosyadan okundu).
CORE_TASK_KEYS = ("tool_use", "web_search", "long_refactor", "needle")
VISION_TASK = "vision"
PDF_TASK = "pdf"
EXTENDED_TASK_KEYS = CORE_TASK_KEYS + (VISION_TASK, PDF_TASK)

# 11 model: real_world_results.json anahtarları == eval_all_models_matrix
# "model" alanları == hiz sonuclar "model" alanları (bkz. test_cross_artifact...).
MAIN_MODELS = (
    "hf.co/ornith-ai/Ornith-1.5-35B-A3B-GGUF:Q4_K_M",
    "openbmb/minicpm-v4.5:latest",
    "ornith-9b:latest",
    "phi4-r-q4km:latest",
    "qwen3-coder:latest",
    "qwen3-vl:8b",
    "qwen3:8b",
    "rc-gemma4-udq4kxl:latest",
    "rc-orcarouter-qwen38-27b-iq2m:latest",
    "rc-qwen38-27b-uncensored-iq2m:latest",
    "rc-qwen35-nvfp4:latest",
)

# eval_all_models_matrix.json alias ↔ model eşlemesi (sıralama puan azalan).
MAIN_ALIASES = {
    "hf.co/ornith-ai/Ornith-1.5-35B-A3B-GGUF:Q4_K_M": "ornith-35b",
    "rc-qwen38-27b-uncensored-iq2m:latest": "uncensored-27b",
    "openbmb/minicpm-v4.5:latest": "minicpm-v4.5",
    "qwen3:8b": "qwen3-8b",
    "ornith-9b:latest": "ornith-9b",
    "rc-gemma4-udq4kxl:latest": "rc-gemma4",
    "qwen3-coder:latest": "qwen3-coder-18b",
    "rc-orcarouter-qwen38-27b-iq2m:latest": "orcarouter-27b",
    "rc-qwen35-nvfp4:latest": "qwen35-nvfp4",
    "phi4-r-q4km:latest": "phi4-r-9b",
    "qwen3-vl:8b": "qwen3-vl-8b",
}

PART2_MODELS = ("bonsai2-mtp", "hf-qwen3-asr", "qwen35-9b-gguf")
BONSAI_REAL_WORLD_MODEL = "bonsai-2-27b"

# eval matris detay kimlikleri (2 kategori x 4 görev).
MATRIX_CATEGORIES = ("matematik", "mantik", "kodlama", "arac_json")
MATRIX_DETAIL_IDS = ("M1", "M2", "T1", "T2", "C1", "C2", "J1", "J2")
MATH_REASONING_IDS = ("M1", "M2", "M3", "M4", "M5", "T1", "T2", "T3", "T4", "T5")

# Thinking trap: içerik BOŞ kalan senaryolar + reasoning'in kurtarıldığı tek vaka.
TRAP_EMPTY_SCENARIOS = (
    "(a3) /api/chat without think (text)",
    "(c1) /v1/chat/completions default (text)",
    "(c2) /v1/chat/completions enable_thinking:false",
)
TRAP_REASONING_CAPTURED = "(a3) /api/chat without think (text)"

# Gerçek Dünya ana dosyasında içeriği boş dönen (model, görev) çiftleri.
EMPTY_CONTENT_PAIRS = (
    ("openbmb/minicpm-v4.5:latest", "long_refactor"),
    ("qwen3-vl:8b", "long_refactor"),
    ("rc-gemma4-udq4kxl:latest", "web_search"),
)

# embeddinggemma2 ölçümü: dört bölüm aynı 6 varyantı taşır.
EMBEDDING_VARIANTS = (
    "embeddinggemma-2 (ham)",
    "embeddinggemma-2 (resmî prefix)",
    "embeddinggemma (v1, ham)",
    "embeddinggemma (v1, resmî prefix)",
    "qwen3-embedding:0.6b (ham)",
    "qwen3-embedding:0.6b (instruct)",
)
EMBEDDING_SECTIONS = ("hiz", "paket_a", "paket_b", "paket_c_mrl")
# paket_b: prefix kullanmayan ham embeddinggemma-2'nin yön nüansı kaybı (2/4).
EMBEDDING_PAKET_B_TOP1 = {
    "embeddinggemma-2 (ham)": "2/4",
    "embeddinggemma-2 (resmî prefix)": "4/4",
    "embeddinggemma (v1, ham)": "4/4",
    "embeddinggemma (v1, resmî prefix)": "4/4",
    "qwen3-embedding:0.6b (ham)": "3/4",
    "qwen3-embedding:0.6b (instruct)": "3/4",
}


# =============================================================================
# Yardımcılar
# =============================================================================
def _load(name: str):
    """Commit'li artefaktı oku — fixture dizini öncelikli, sonra SRC arşivleri."""
    candidates = (
        FIXTURE_DIR / name,
        SCRATCH_DIR / name,
        REPO_ROOT / "arsiv" / "experiments" / "2026-10" / name,
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        # Ham kanıt artefaktları FIXTURE dizininde izlenir; eski SRC ağacında
        # yalnız arşiv kopyası vardır. Hiçbiri yoksa test ortam önkoşulu
        # olmadığı için SKIP edilir (Y2 değil: assert yolu aynen korunur).
        pytest.skip(f"Kanıt artefaktı bu ağaçta yok: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _score(pair: str) -> int:
    """'6/8' → 6 (pay kısmı). Payda ayrıca doğrulanır."""
    assert isinstance(pair, str), f"skor string olmalı, geldi: {pair!r}"
    numerator, _, denominator = pair.partition("/")
    assert numerator.isdigit(), f"skor payı sayı değil: {pair!r}"
    assert denominator.isdigit(), f"skor paydası sayı değil: {pair!r}"
    return int(numerator)


def _score_denominator(pair: str) -> int:
    return int(pair.partition("/")[2])


def _matrix_records():
    return _load(EVAL_ALL_MODELS)


# =============================================================================
# 1) Parse + kök tip
# =============================================================================
def test_fixture_directory_holds_every_artifact():
    """Korur: kalıcı kanıt yolu ``tests/fixtures/real_world/`` — 9 dosya izlenir.

    Kanıt scratch/ veya arsiv/ altından okunmaz; oradaki kopyalar yalnızca
    eski SRC ağacı için yedektir. Fixture silinirse bu test kırmızı olur.
    """
    missing = sorted(name for name in ROOT_TYPES if not (FIXTURE_DIR / name).is_file())
    assert not missing, f"kalıcı kanıt dosyası eksik: {missing}"


def test_artifacts_parse_with_expected_root_types():
    """Korur: 9 kanıt dosyasının tamamı geçerli JSON ve kök tipi beklenen (dict/list)."""
    for name, expected in ROOT_TYPES.items():
        data = _load(name)
        assert isinstance(data, expected), (
            f"{name} kök tipi {expected.__name__} olmalı, geldi {type(data).__name__}"
        )
        assert data, f"{name} boş — kanıt yok"

    hiz = _load(HIZ_OLCUM)
    assert set(hiz) == {"meta", "sonuclar"}, f"hiz kök anahtarları: {sorted(hiz)}"
    assert isinstance(hiz["sonuclar"], list) and hiz["sonuclar"]


# =============================================================================
# 2) real_world_results.json — model kimlikleri + görev anahtarları
# =============================================================================
def test_real_world_main_models_and_task_keys():
    """Korur: ana dosyada 11 model ve her kayıtta flags + 6 görev anahtarı var."""
    data = _load(REAL_WORLD_MAIN)
    assert set(data) == set(MAIN_MODELS), f"model kümesi kaydı: {sorted(data)}"

    for model, record in data.items():
        assert set(record) == {"flags", "tests"}, f"{model} kayıt anahtarları: {record}"
        flags = record["flags"]
        assert isinstance(flags, dict) and flags, f"{model} flags boş"
        assert isinstance(flags.get("temperature"), (int, float)), f"{model} sıcaklık"
        assert flags.get("num_ctx") in (4096, 8192), (
            f"{model} num_ctx: {flags.get('num_ctx')}"
        )

        tests = record["tests"]
        assert set(tests) == set(EXTENDED_TASK_KEYS), (
            f"{model} görev anahtarları kaydı: {sorted(tests)}"
        )
        for task, entry in tests.items():
            assert isinstance(entry, dict), f"{model}/{task} kaydı dict değil"
            assert isinstance(entry.get("wall_clock_s"), (int, float)), (
                f"{model}/{task}"
            )
            assert entry["wall_clock_s"] >= 0, f"{model}/{task} negatif süre"


# =============================================================================
# 3) real_world_results.json — kayıt şekli (hata mı, ham yanıt mı)
# =============================================================================
def test_real_world_main_entry_shapes_and_error_census():
    """Korur: her görev kaydı ya hata ya ham Ollama yanıtı; hata/boş içerik sayımı sabit."""
    data = _load(REAL_WORLD_MAIN)
    errors: Counter = Counter()
    empty_content: set = set()

    for model, record in data.items():
        for task, entry in record["tests"].items():
            keys = set(entry)
            if keys == {"error", "wall_clock_s"}:
                assert isinstance(entry["error"], str) and entry["error"].strip()
                errors[entry["error"]] += 1
                continue

            # Ham yanıt: en az content + süre + token sayısı taşır.
            assert {"message", "wall_clock_s", "eval_count"} <= keys, (
                f"{model}/{task} beklenmeyen kayıt şekli: {sorted(keys)}"
            )
            message = entry["message"]
            assert message.get("role") == "assistant", f"{model}/{task} rol"
            content = message.get("content")
            assert isinstance(content, str), f"{model}/{task} content str değil"
            assert entry["eval_count"] > 0, f"{model}/{task} eval_count"
            if not content.strip():
                empty_content.add((model, task))

    assert errors == Counter(
        {"Model does not support vision (skipped).": 9, "timed out": 5}
    ), f"hata dağılımı kaydı: {dict(errors)}"
    # Sessiz bozulma göstergesi: boş içerik dönen yanıt kümesi büyürse kırmızı.
    assert empty_content == set(EMPTY_CONTENT_PAIRS), (
        f"içeriği boş yanıt kümesi kaydı: {sorted(empty_content)}"
    )


# =============================================================================
# 4) part2 + bonsai dosyaları
# =============================================================================
def test_real_world_part2_and_bonsai_records():
    """Korur: part2'de 3 model (4 görev), bonsai'de 1 model (6 görev), kümeler ayrık."""
    part2 = _load(REAL_WORLD_PART2)
    assert set(part2) == set(PART2_MODELS), f"part2 model kümesi: {sorted(part2)}"
    for model, record in part2.items():
        assert set(record) == {"flags", "tests"}, f"{model} kayıt anahtarları"
        assert record["flags"].get("api") == "openai_compat", f"{model} api alanı"
        assert set(record["tests"]) == set(CORE_TASK_KEYS), (
            f"{model} görev anahtarları: {sorted(record['tests'])}"
        )
        for task, entry in record["tests"].items():
            assert set(entry) == {"error", "wall_clock_s"}, f"{model}/{task} hata kaydı"
            assert entry["error"] == "Model failed on both ports", f"{model}/{task}"

    bonsai = _load(REAL_WORLD_BONSAI)
    assert set(bonsai) == {BONSAI_REAL_WORLD_MODEL}, (
        f"bonsai model kümesi: {sorted(bonsai)}"
    )
    bonsai_record = bonsai[BONSAI_REAL_WORLD_MODEL]
    assert set(bonsai_record["tests"]) == set(EXTENDED_TASK_KEYS)
    assert bonsai_record["flags"].get("api") == "openai", "bonsai api alanı"
    assert bonsai_record["tests"][VISION_TASK]["error"] == (
        "Model does not support vision (skipped)."
    )
    for task in CORE_TASK_KEYS + (PDF_TASK,):
        content = bonsai_record["tests"][task]["message"]["content"]
        assert isinstance(content, str) and content.strip(), f"bonsai/{task} boş içerik"

    # Üç dosya aynı modeli iki kez kaydetmemeli (birleşik kanıt = 15 model).
    all_ids = [*_load(REAL_WORLD_MAIN), *part2, *bonsai]
    assert len(all_ids) == len(set(all_ids)) == 15, (
        f"gerçek dünya model sayısı: {len(all_ids)}"
    )


# =============================================================================
# 5) eval_all_models_matrix.json — alanlar + özet tutarlılığı
# =============================================================================
def test_eval_all_models_matrix_fields_and_score_consistency():
    """Korur: 11 kayıt, zorunlu alanlar var; toplam_puan 0..8 ve 'x/8' ile kategorilerle tutarlı."""
    records = _matrix_records()
    assert len(records) == 11, f"matris kayıt sayısı: {len(records)}"

    scores = []
    for record in records:
        assert {"model", "alias", "toplam", "toplam_puan", "ort_tps"} <= set(record), (
            f"eksik alan: {sorted(record)}"
        )
        assert set(MATRIX_CATEGORIES) <= set(record), (
            f"{record['alias']} kategori alanı eksik"
        )

        total = record["toplam_puan"]
        assert isinstance(total, int) and 0 <= total <= 8, (
            f"{record['alias']} puan: {total}"
        )
        assert _score(record["toplam"]) == total, (
            f"{record['alias']} toplam ↔ toplam_puan"
        )
        assert _score_denominator(record["toplam"]) == 8, f"{record['alias']} payda"
        assert record["ort_tps"] > 0, f"{record['alias']} ort_tps: {record['ort_tps']}"

        category_sum = 0
        for category in MATRIX_CATEGORIES:
            numerator = _score(record[category])
            assert _score_denominator(record[category]) == 2, (
                f"{record['alias']}/{category} payda 2 değil"
            )
            assert 0 <= numerator <= 2, f"{record['alias']}/{category}: {numerator}"
            category_sum += numerator
        assert category_sum == total, (
            f"{record['alias']} kategori toplamı {category_sum} != toplam_puan {total}"
        )
        scores.append(total)

    # Kayıt dosyası puan azalan sırada tutuluyor (sıralama bozulursa kırmızı).
    assert scores == sorted(scores, reverse=True), f"puan sırası bozuk: {scores}"
    assert (max(scores), min(scores)) == (8, 0), f"uç puanlar: {scores}"


# =============================================================================
# 6) eval_all_models_matrix.json — detay ↔ özet
# =============================================================================
def test_eval_all_models_matrix_details_match_summary():
    """Korur: her kayıtta 8 detay (M/T/C/J) ve kategori başına geçen sayısı özetle aynı."""
    for record in _matrix_records():
        details = record["detaylar"]
        assert len(details) == 8, f"{record['alias']} detay sayısı: {len(details)}"
        assert tuple(sorted(d["id"] for d in details)) == tuple(
            sorted(MATRIX_DETAIL_IDS)
        ), f"{record['alias']} detay kimlikleri"
        assert Counter(d["kat"] for d in details) == Counter(
            {category: 2 for category in MATRIX_CATEGORIES}
        ), f"{record['alias']} kategori dağılımı"

        passed: Counter = Counter()
        for detail in details:
            assert isinstance(detail["pass"], bool), (
                f"{record['alias']}/{detail['id']} pass"
            )
            assert detail["tps"] > 0, f"{record['alias']}/{detail['id']} tps"
            assert detail["tokens"] > 0, f"{record['alias']}/{detail['id']} tokens"
            if detail["pass"]:
                passed[detail["kat"]] += 1

        for category in MATRIX_CATEGORIES:
            assert passed[category] == _score(record[category]), (
                f"{record['alias']}/{category}: detay {passed[category]} != "
                f"özet {record[category]}"
            )


# =============================================================================
# 7) eval_bonsai_matrix.json
# =============================================================================
def test_eval_bonsai_matrix_single_record_consistency():
    """Korur: bonsai matrisi tek kayıt (6/8) ve detayları özetle tutarlı; mantık 0/2."""
    records = _load(EVAL_BONSAI)
    assert len(records) == 1, f"bonsai matris kayıt sayısı: {len(records)}"
    record = records[0]
    assert record["alias"] == "bonsai-2-27b", f"bonsai alias: {record['alias']}"
    assert record["toplam_puan"] == _score(record["toplam"]) == 6, "bonsai toplam"
    assert record["mantik"] == "0/2", f"bonsai mantik: {record['mantik']}"
    assert record["ort_tps"] > 0

    passed: Counter = Counter()
    for detail in record["detaylar"]:
        assert isinstance(detail["pass"], bool)
        if detail["pass"]:
            passed[detail["kat"]] += 1
    for category in MATRIX_CATEGORIES:
        assert passed[category] == _score(record[category]), (
            f"bonsai/{category}: detay {passed[category]} != özet {record[category]}"
        )


# =============================================================================
# 8) eval_math_and_reasoning_results.json
# =============================================================================
def test_eval_math_and_reasoning_score_consistency():
    """Korur: 5 kayıt, skor_toplam 'x/10' ile 10 görevin geçen sayısı ve ort_tps tutarlı."""
    records = _load(EVAL_MATH_REASONING)
    assert len(records) == 5, f"math+reasoning kayıt sayısı: {len(records)}"

    for record in records:
        assert {
            "model",
            "alias",
            "skor_toplam",
            "matematik",
            "mantik",
            "ort_tps",
        } <= set(record)
        assert _score_denominator(record["skor_toplam"]) == 10, (
            f"{record['alias']} payda"
        )
        assert record["ort_tps"] > 0, f"{record['alias']} ort_tps: {record['ort_tps']}"
        assert _score(record["matematik"]) + _score(record["mantik"]) == _score(
            record["skor_toplam"]
        ), f"{record['alias']} matematik+mantik != skor_toplam"

        details = record["detaylar"]
        assert len(details) == 10, f"{record['alias']} detay sayısı: {len(details)}"
        assert tuple(sorted(d["id"] for d in details)) == MATH_REASONING_IDS, (
            f"{record['alias']} detay kimlikleri"
        )

        passed: Counter = Counter()
        for detail in details:
            assert detail["tur"] in ("matematik", "mantik"), f"{detail['id']} tur"
            assert isinstance(detail["gecti"], bool), f"{detail['id']} gecti"
            assert detail["beklenen"].strip(), f"{detail['id']} beklenen boş"
            assert detail["cevap_ozet"].strip(), f"{detail['id']} cevap_ozet boş"
            assert detail["tps"] > 0 and detail["tokens"] > 0, f"{detail['id']} hız"
            if detail["gecti"]:
                passed[detail["tur"]] += 1

        for category in ("matematik", "mantik"):
            assert passed[category] == _score(record[category]), (
                f"{record['alias']}/{category}: detay {passed[category]} != özet"
            )


# =============================================================================
# 9) Çapraz artefakt kimlik bütünlüğü
# =============================================================================
def test_cross_artifact_model_identity():
    """Korur: 11 model kimliği matris/hız/gerçek-dünya dosyalarında birebir aynı; alias'lar tekil."""
    matrix_models = {record["model"] for record in _matrix_records()}
    assert len(matrix_models) == 11, (
        f"matris model kimliği tekil değil: {len(matrix_models)}"
    )

    hiz_models = {row["model"] for row in _load(HIZ_OLCUM)["sonuclar"]}
    real_world_models = set(_load(REAL_WORLD_MAIN))

    assert matrix_models == set(MAIN_MODELS), (
        f"matris model kümesi: {sorted(matrix_models)}"
    )
    assert hiz_models == matrix_models, (
        f"hız ↔ matris farkı: {hiz_models ^ matrix_models}"
    )
    assert real_world_models == matrix_models, (
        f"gerçek dünya ↔ matris farkı: {real_world_models ^ matrix_models}"
    )

    alias_map = {record["model"]: record["alias"] for record in _matrix_records()}
    assert alias_map == MAIN_ALIASES, f"alias eşlemesi kaydı: {alias_map}"
    assert len(set(alias_map.values())) == 11, "alias'lar tekil değil"


# =============================================================================
# 10) thinking_trap_results.json
# =============================================================================
def test_thinking_trap_scenarios_and_content_invariants():
    """Korur: 8 senaryo; content_empty ↔ content_len==0; boş küme ve reasoning kaydı sabit."""
    records = _load(THINKING_TRAP)
    assert len(records) == 8, f"tuzak senaryo sayısı: {len(records)}"
    names = [record["name"] for record in records]
    assert len(set(names)) == 8, f"senaryo adları tekil değil: {names}"

    empty_scenarios = set()
    for record in records:
        assert {
            "content_empty",
            "finish_reason",
            "reasoning_len",
            "content_len",
        } <= set(record), f"{record['name']} eksik alan"
        assert isinstance(record["content_empty"], bool), (
            f"{record['name']} content_empty"
        )
        assert record["finish_reason"] == "length", (
            f"{record['name']} finish_reason: {record['finish_reason']}"
        )
        # Tüm koşumlar 256 token'lık num_predict tavanına takıldı.
        assert record["eval_count"] == 256, f"{record['name']} eval_count"
        assert record["content_len"] >= 0 and record["reasoning_len"] >= 0
        assert record["tps"] > 0 and record["wall_clock"] > 0, f"{record['name']} hız"
        assert record["has_think_tag"] is False, f"{record['name']} has_think_tag"

        # Boş içerik iddiası uzunlukla çelişmemeli.
        assert record["content_empty"] == (record["content_len"] == 0), (
            f"{record['name']}: content_empty={record['content_empty']} "
            f"content_len={record['content_len']}"
        )
        if record["content_empty"]:
            empty_scenarios.add(record["name"])

    assert empty_scenarios == set(TRAP_EMPTY_SCENARIOS), (
        f"içeriği boş senaryolar kaydı: {sorted(empty_scenarios)}"
    )
    # Tuzağın özü: /api/chat thinking'i reasoning'e yazar (kurtarılabilir), /v1
    # completions yolu ise hem content hem reasoning'i kaybeder (0/0).
    by_name = {record["name"]: record for record in records}
    affected = by_name[TRAP_REASONING_CAPTURED]
    assert affected["reasoning_len"] > 0 and affected["content_len"] == 0
    for name in TRAP_EMPTY_SCENARIOS:
        if name == TRAP_REASONING_CAPTURED:
            continue
        assert by_name[name]["reasoning_len"] == 0, (
            f"{name}: /v1 yolu reasoning kaydı beklenmedik şekilde dolu"
        )


# =============================================================================
# 11) hiz_yeniden_olcum_2026-10-06.json
# =============================================================================
def test_hiz_remeasurement_consistency():
    """Korur: 11 model, tg > 0 ve tg == iki koşumun ortalaması (tolerans 0.1); meta dolu.

    Not: görev prompt'unda geçen ``trust == 'good'`` alanı bu artefaktta YOK —
    dosya yalnızca ``model/tg/wall/runs`` taşır. Alan uydurulmadı; hız/güven
    etiketi ayrı kapsamda (tests/unit/test_label_speed_trust.py) doğrulanır.
    """
    data = _load(HIZ_OLCUM)
    meta = data["meta"]
    assert {"tarih", "protokol", "not", "kapsam_disi"} <= set(meta), (
        f"meta alanları: {sorted(meta)}"
    )
    assert all(str(meta[key]).strip() for key in meta), "meta alanı boş"

    rows = data["sonuclar"]
    assert len(rows) == 11, f"hız ölçüm satır sayısı: {len(rows)}"
    assert {row["model"] for row in rows} == set(MAIN_MODELS), "hız ölçüm model kümesi"

    for row in rows:
        assert row["tg"] > 0, f"{row['model']} tg: {row['tg']}"
        assert row["wall"] > 0, f"{row['model']} wall: {row['wall']}"
        assert len(row["runs"]) == 2, f"{row['model']} koşum sayısı: {row['runs']}"
        assert all(run > 0 for run in row["runs"]), (
            f"{row['model']} runs: {row['runs']}"
        )
        assert row["tg"] == pytest.approx(statistics.fmean(row["runs"]), abs=0.1), (
            f"{row['model']}: tg {row['tg']} != runs ortalaması {row['runs']}"
        )


# =============================================================================
# 12) embeddinggemma2_olcum_2026-10-06.json
# =============================================================================
def test_embeddinggemma2_sections_and_prefix_regression():
    """Korur: 6 varyantlı dört bölüm, determinizm=1, MRL kesitleri 5/5 ve prefix etkisi kaydı."""
    data = _load(EMBEDDING_OLCUM)
    meta = data["meta"]
    assert {"tarih", "v2", "protokol", "v2_determinizm_cos", "vram_son"} <= set(meta), (
        f"meta alanları: {sorted(meta)}"
    )
    assert meta["v2_determinizm_cos"] == 1, f"determinizm: {meta['v2_determinizm_cos']}"

    for section in EMBEDDING_SECTIONS:
        assert set(data[section]) == set(EMBEDDING_VARIANTS), (
            f"{section} varyant kümesi: {sorted(data[section])}"
        )

    for variant in EMBEDDING_VARIANTS:
        hiz = data["hiz"][variant]
        assert hiz["dok_sn"] > 0 and hiz["tek_sorgu_ms_ort"] > 0, f"{variant} hız"
        assert len(hiz["dok_sn_3kosum"]) == 3, f"{variant} koşum sayısı"
        assert all(run > 0 for run in hiz["dok_sn_3kosum"]), f"{variant} koşumlar"

        paket_a = data["paket_a"][variant]
        assert paket_a["top1"] == "5/5" and paket_a["mrr"] == 1.0, f"{variant} paket_a"
        assert len(paket_a["detay"]) == 5, f"{variant} paket_a detay"
        assert all(item["rank"] == 1 for item in paket_a["detay"]), f"{variant} rank"

        paket_b = data["paket_b"][variant]
        assert paket_b["top1"] == EMBEDDING_PAKET_B_TOP1[variant], (
            f"{variant} paket_b top1: {paket_b['top1']}"
        )
        ok_count = sum(1 for item in paket_b["detay"] if item["sonuc"] == "OK")
        assert ok_count == _score(paket_b["top1"]), (
            f"{variant} paket_b detay {ok_count} != özet {paket_b['top1']}"
        )

        mrl = data["paket_c_mrl"][variant]
        expected_dim = 1024 if variant.startswith("qwen3-embedding") else 768
        assert mrl["yerel_dim"] == expected_dim, (
            f"{variant} yerel_dim: {mrl['yerel_dim']}"
        )
        for cut in ("512", "256", "128"):
            assert mrl[cut]["top1"] == "5/5" and mrl[cut]["mrr"] == 1.0, (
                f"{variant} MRL {cut}"
            )

    # Prefix etkisi: ham embeddinggemma-2 yön nüansında 2/4'e düşer, resmî prefix 4/4.
    assert _score(data["paket_b"]["embeddinggemma-2 (ham)"]["top1"]) < _score(
        data["paket_b"]["embeddinggemma-2 (resmî prefix)"]["top1"]
    ), "prefix etkisi kaydı kaybolmuş"
