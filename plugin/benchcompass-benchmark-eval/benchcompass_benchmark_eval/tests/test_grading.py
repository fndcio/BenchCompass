"""Grading kuralları testleri (network yok)."""

import pytest

from benchcompass_benchmark_eval import grading


@pytest.fixture
def suites():
    return grading.load_suites(None)


def test_suite_counts(suites):
    ids = {t["id"] for t in suites}
    assert len(ids) == len(suites), "görev id'leri benzersiz olmalı"
    tr_count = len([t for t in suites if t.get("lang") == "tr"])
    assert tr_count >= 20  # B3: tam Türkçe suite (20+ görev)
    assert len(suites) == 24 + tr_count  # 24 EN + TR


def test_num_grade_takes_last_number():
    task = {"type": "num", "expected": "70"}
    assert grading.grade_task(task, "144 / 12 = 12\n12 + 58 = 70\n70")


def test_num_grade_ignores_reasoning():
    task = {"type": "num", "expected": "391"}
    text = "I will compute 17*23. <think>17 times 20 is 340</think> the answer is 391."
    assert grading.grade_task(task, text)


def test_num_grade_wrong():
    task = {"type": "num", "expected": "9"}
    assert not grading.grade_task(task, "x = 11")


def test_word_grade_expected():
    task = {"type": "word", "expected": "tokyo"}
    assert grading.grade_task(task, "The capital is Tokyo.")


def test_word_grade_accept_list():
    task = {
        "type": "word",
        "expected": "1/8",
        "accept": ["1/8", "0.125", "eighth", "dfrac{1}{8}", "frac{1}{8}"],
    }
    assert grading.grade_task(task, r"\boxed{\dfrac{1}{8}}")
    assert grading.grade_task(task, "0.125")
    assert not grading.grade_task(task, "1/4")


def test_turkish_unicode_casefolding_and_latex():
    task_city = {"type": "word", "expected": "istanbul", "accept": ["istanbul"]}
    assert grading.grade_task(task_city, "Türkiye'nin en kalabalık şehri İstanbul'dur.")
    assert grading.grade_task(task_city, "İstanbul")

    task_frac = {"type": "word", "expected": "1/8", "accept": ["1/8", "sekizde bir"]}
    assert grading.grade_task(task_frac, r"Olasılık $$\frac{1}{8}$$ olarak hesaplanır.")

    task_light = {"type": "word", "expected": "ışık", "accept": ["ışık"]}
    assert grading.grade_task(task_light, "Işık.")


def test_code_grade_pass():
    task = {
        "type": "code",
        "prompt": "fizzbuzz",
        "test": 'assert fizzbuzz(15)[:6] == [1,2,"Fizz",4,"Buzz","Fizz"]',
    }
    code = "def fizzbuzz(n):\n    out = []\n    for i in range(1, n+1):\n        if i % 15 == 0: out.append('FizzBuzz')\n        elif i % 3 == 0: out.append('Fizz')\n        elif i % 5 == 0: out.append('Buzz')\n        else: out.append(i)\n    return out"
    assert grading.grade_task(task, code)


def test_code_grade_fail_on_wrong():
    task = {"type": "code", "test": "assert nth_fib(10) == 55"}
    code = "def nth_fib(n):\n    return n"  # yanlış
    assert not grading.grade_task(task, code)


def test_code_grade_extracts_from_markdown_and_think():
    task = {"type": "code", "test": "assert nth_fib(10) == 55"}
    text = (
        "<think>let me think</think>\n```python\ndef nth_fib(n):\n"
        "    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n"
        "    return a\n```\nBu çözümdür."
    )
    assert grading.grade_task(task, text)


def test_code_grade_ignores_print_output():
    task = {"type": "code", "test": "assert fizzbuzz(3) == [1,2,'Fizz']"}
    code = "def fizzbuzz(n):\n    return [i%15==0 and 'FizzBuzz' or i%3==0 and 'Fizz' or i%5==0 and 'Buzz' or i for i in range(1,n+1)]\nprint(fizzbuzz(15))"
    assert grading.grade_task(task, code)


def test_extract_last_number():
    assert grading.extract_last_number("a 12 b 34 c") == "34"
    assert grading.extract_last_number("<think>340</think> answer 391") == "391"
    assert grading.extract_last_number("yok") is None


def test_extract_code_empty_when_no_def():
    assert grading.extract_code("Burada kod yok") is None or "def " not in (
        grading.extract_code("Burada kod yok") or ""
    )


def test_strip_think_unclosed_tag_fast():
    """Kesik <think> bloğu (kapanış etiketi yok) backtracking yapmadan temizlenir."""
    text = "<think>uzun reasoning başladı ama kesildi..." * 5000
    import time

    t0 = time.perf_counter()
    cleaned = grading._strip_think(text)
    elapsed = time.perf_counter() - t0
    assert "<think>" not in cleaned
    assert (
        elapsed < 2.0
    )  # eski .*?</think> regex'i burada saniyelerce/yıllarca asılı kalırdı


def test_strip_think_balanced():
    text = "<think>düşün</think>Cevap 42"
    assert grading._strip_think(text) == "Cevap 42"


def test_code_grade_infinite_loop_bounded():
    """Model kodunda sonsuz döngü varsa exec asılmaz, başarısız sayılır."""
    import time

    task = {"type": "code", "test": "assert fizzbuzz(3) == [1,2,'Fizz']"}
    code = "def fizzbuzz(n):\n    return [1,2,'Fizz']\n\nwhile True:\n    pass"
    t0 = time.perf_counter()
    assert not grading.grade_task(task, code)
    assert time.perf_counter() - t0 < 10.0


# --- B3: dil bazlı skor kırılımı ---
def test_summarize_by_lang_splits_tr_en():
    tasks = [
        {"id": "ar1", "lang": "en"},
        {"id": "tr1", "lang": "tr"},
        {"id": "tr2", "lang": "tr"},
        {"id": "tr3", "lang": "tr"},
    ]
    details = [
        {"id": "ar1", "pass": True},
        {"id": "tr1", "pass": True},
        {"id": "tr2", "pass": False},
        {"id": "tr3", "pass": True},
    ]
    out = grading.summarize_by_lang(details, tasks)

    assert out["en"] == {"total": 1, "passed": 1, "failed": 0, "score": 100.0}
    assert out["tr"] == {"total": 3, "passed": 2, "failed": 1, "score": 66.7}


def test_summarize_by_lang_default_en_for_unknown():
    tasks = [{"id": "x1"}]
    details = [{"id": "x1", "pass": True}]
    out = grading.summarize_by_lang(details, tasks)
    assert out["en"]["passed"] == 1


def test_wilson_ci_bounds():
    # 0 n için 0, 0
    assert grading.wilson_ci(0, 0) == (0.0, 0.0)
    # 10/10 için alt sınır > 0, üst sınır = 100
    low, high = grading.wilson_ci(10, 10)
    assert 65.0 < low < 75.0
    assert high == 100.0
    # 5/10 için orta nokta ~50%
    low5, high5 = grading.wilson_ci(5, 10)
    assert low5 < 50.0 < high5


# ---------------------------------------------------------------------------
# Adım 3 — McNemar (ADR-0015, Y26 oracle)
# ---------------------------------------------------------------------------
# Oracle: doğru çözüm (aynı sonuçlar) → p=1.0; yanlış çözüm (güçlü fark/KAYIP)
# → p<0.05 reddi. Kenarlar: n=0, discordant=0.


def test_mcnemar_oracle_same_no_difference():
    """Aynı sonuçlar (discordant=0) → p=1.0, anlamlı değil."""
    a = [True, False, True, False] * 5
    mc = grading.mcnemar_test(a, list(a))
    assert mc["discordant"] == 0
    assert mc["p_value"] == 1.0
    assert mc["significant"] is False


def test_mcnemar_oracle_strong_difference():
    """Güçlü fark (9v1 discordant) → p<0.05, anlamlı."""
    # 9 görev A-geçti/B-kaldı, 1 görev A-kaldı/B-geçti, 10 görev ikisi de geçti
    a = [True] * 9 + [False] + [True] * 10
    b = [False] * 9 + [True] + [True] * 10
    mc = grading.mcnemar_test(a, b)
    assert mc["b"] == 9
    assert mc["c"] == 1
    assert mc["discordant"] == 10
    # Exact: 2*P(X<=1 | Binom(10,0.5)) = 2*11/1024 ≈ 0.0215
    assert mc["p_value"] < 0.05
    assert mc["significant"] is True


def test_mcnemar_edge_empty_and_mismatch():
    """n=0 → p=1.0; uzunluk uyumsuzluğu ValueError."""
    mc = grading.mcnemar_test([], [])
    assert mc["p_value"] == 1.0
    assert mc["n"] == 0
    with pytest.raises(ValueError):
        grading.mcnemar_test([True], [True, False])


def test_compare_details_drilldown_categories():
    """Drill-down: 4 kategori + ortak-id eşleme."""
    da = [
        {"id": "t1", "pass": True},
        {"id": "t2", "pass": True},
        {"id": "t3", "pass": False},
        {"id": "t4", "pass": False},
    ]
    db = [
        {"id": "t1", "pass": True},
        {"id": "t2", "pass": False},
        {"id": "t3", "pass": True},
        {"id": "t4", "pass": False},
    ]
    out = grading.compare_details(da, db)
    assert out["n"] == 4
    assert out["discordant"] == 2
    cats = {r["id"]: r["category"] for r in out["tasks"]}
    assert cats == {
        "t1": "both_pass",
        "t2": "a_only",
        "t3": "b_only",
        "t4": "both_fail",
    }


def test_code_grade_fence_siz_import_korur():
    """cd5 dersi (2026-10-07 bulgu, 2026-11-05 düzeltme): fence'siz yanıtta modül
    düzeyi import satırları blok ayıklamada düşüyordu -> dogru cozum NameError ile
    FAIL sayiliyordu (Saluki cd5 kaniti: SONUCLAR_23 §9.5).

    Oracle (Y26): dogru cozum (import'lu) GECMELI; import'un dusuruldugu bilesim
    (eski sozlesme davranisinin simülasyonu) DUSMELI.
    """
    task = {
        "type": "code",
        "prompt": "defaultdict ile komsuluk listesi kur",
        "test": "assert solve([(1, 2), (2, 3)]) == {1: [2], 2: [3]}",
    }
    text = (
        "Elbette, iste cozum:\n"
        "from collections import defaultdict\n"
        "\n"
        "def solve(edges):\n"
        "    g = defaultdict(list)\n"
        "    for u, v in edges:\n"
        "        g[u].append(v)\n"
        "    return g\n"
    )
    # extract_code import satirini korumali
    kod = grading.extract_code(text)
    assert kod is not None
    assert "from collections import defaultdict" in kod
    assert "def solve(edges):" in kod
    # dogru cozum gecmeli (yeni sozlesme)
    assert grading.grade_task(task, text)
    # eski sozlesme simülasyonu: import'suz bilesim NameError ile dusmeli
    import_siz = "\n".join(ln for ln in text.splitlines() if not ln.startswith("from"))
    assert not grading.grade_task(task, import_siz)
