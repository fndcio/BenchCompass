"""Görev değerlendirme kuralları (network yok — saf fonksiyonlar).

Görev tipleri:
  - num : yanıttan SON sayısal cevap çıkarılır (reasoning sonrası nihai cevap)
  - word: expected veya accept listesinden birinin yanıtta geçmesi aranır
  - code: python kodu exec + birim test geçişi
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from . import config


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _strip_think(text: str) -> str:
    """Reasoning bloklarını (deepseek-r1 vb.) yanıttan temizler.

    Backtracking-güvenli: `<think>` / `</think>` etiketlerini ayırıcı olarak
    kullanır. Kesik (kapanış etiketi olmayan) `<think>` bloklarını da temizler
    — `.*?</think>` regex'i kesik bloklarda catastrophic backtracking yapar.
    """
    parts = re.split(r"(<think>|</think>)", text)
    out: list[str] = []
    depth = 0
    for part in parts:
        if part == "<think>":
            depth += 1
        elif part == "</think>":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(part)
    return "".join(out)


def extract_last_number(text: str) -> str | None:
    """Metinden SON sayısal cevabı çıkarır (binlik ayracı temizlenmiş)."""
    text = _strip_think(text)
    nums = re.findall(r"-?\d[\d.,]*", text.replace(",", ""))
    return nums[-1].replace(".", "") if nums else None


def extract_code(text: str) -> str | None:
    """Yanıttan Python fonksiyon/class kodunu çıkarır.

    Backtracking-güvenli: fenced blok (```) ayıklaması regex yerine index bazlı
    `str.find` ile yapılır — kapanış fence'i olmayan büyük yanıtlarda
    `.*?``` regex'i O(n^2) davranıp asılabilir.
    """
    text = _strip_think(text)
    fence = "```"
    start = text.find(fence)
    if start != -1:
        body_start = text.find("\n", start)
        body_start = (body_start + 1) if body_start != -1 else (start + len(fence))
        end = text.find(fence, body_start)
        code = text[body_start:end] if end != -1 else text[body_start:]
    else:
        code = text
    # `def ...` / `class ...` bloklarını satır bazlı ayıkla (güvenli, O(n))
    lines = code.splitlines()
    blocks: list[str] = []
    cur: list[str] = []
    ust_seviye_importlar: list[str] = []
    for ln in lines:
        # Modül düzeyi import satırları koru (cd5 dersi, 2026-10-07): fence'siz
        # yanıtta `from x import y` satırları düşüyor → doğru çözüm NameError
        # ile FAIL oluyordu. Yalnız kanonik form: `import m` / `from m import ...`
        if re.match(r"^(?:import\s+[\w.]+|from\s+[\w.]+\s+import\s+\S.*)$", ln):
            ust_seviye_importlar.append(ln)
            continue
        if re.match(r"^(?:def|class)\s+\w+", ln):
            if cur:
                blocks.append("\n".join(cur))
            cur = [ln]
        elif cur:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))
    if blocks:
        parcalar: list[str] = []
        if ust_seviye_importlar:
            parcalar.append("\n".join(dict.fromkeys(ust_seviye_importlar)))
        parcalar.append("\n".join(blocks))
        code = "\n\n".join(parcalar)
    return code.strip()


# ---------------------------------------------------------------------------
# Görev yükleme
# ---------------------------------------------------------------------------


def load_suite(name: str) -> list[dict]:
    """tasks/<name>.json dosyasından görev listesi yükler."""
    path = config.TASKS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Görev suite'i bulunamadı: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks", data)
    if not isinstance(tasks, list):
        raise ValueError(f"Suite formatı hatalı (tasks listesi bekleniyordu): {path}")
    return tasks


def load_suites(names: list[str] | None) -> list[dict]:
    """Birden çok suite'i birleştirir; görev id'leri benzersiz kalır."""
    names = names or config.DEFAULT_SUITES
    merged: dict[str, dict] = {}
    for n in names:
        for t in load_suite(n):
            merged[t["id"]] = t
    return list(merged.values())


# ---------------------------------------------------------------------------
# Değerlendirme
# ---------------------------------------------------------------------------


def _normalize_text_for_matching(text: str) -> str:
    """Metin eşleştirme için normalizasyon (Türkçe Unicode casefolding, LaTeX kesir ve noktalama).

    - LaTeX kesirleri (örn. \\frac{1}{8}, \\dfrac{1}{8}) -> 1/8 yapar.
    - Türkçe büyük İ -> i ve I -> ı dönüşümlerini yaparak Unicode birleşik nokta (\\u0307)
      hatalarını engeller.
    - Genel lowercase ve uçlardaki noktalama işaretlerini temizler.
    """
    text = _strip_think(text)
    # LaTeX kesir normalizasyonu
    text = re.sub(r"\\(?:d)?frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", text)
    # Türkçe Unicode casefolding (İ -> i, I -> ı)
    text = text.replace("İ", "i").replace("I", "ı").replace("\u0307", "")
    return text.lower().strip()


def grade_task(task: dict, response_text: str) -> bool:
    """Bir görevi yanıt metnine göre değerlendirir (True = geçti)."""
    cleaned = _strip_think(response_text)
    ttype = task.get("type")
    if ttype == "num":
        got = extract_last_number(cleaned)
        return got == extract_last_number(str(task.get("expected", "")))
    if ttype in ("word", "vision"):
        low = _normalize_text_for_matching(cleaned)
        accept = task.get("accept") or [task.get("expected")]
        if isinstance(accept, str):
            accept = [accept]
        return any(_normalize_text_for_matching(str(a)) in low for a in accept if a)
    if ttype == "code":
        return _grade_code(task, cleaned)
    return False


_EXEC_TIMEOUT_S = 5  # model kodunda sonsuz döngü olursa asılmayalım


def _grade_code(task: dict, cleaned: str) -> bool:
    """Kod görevi: kodu çıkar, güvenli unit test exec et (zaman aşımlı)."""
    code = extract_code(cleaned)
    test = task.get("test", "")
    if not code or not test or ("def " not in code and "class " not in code):
        return False

    import contextlib
    import io
    import threading

    ns: dict[str, Any] = {"__builtins__": __builtins__}
    sink = io.StringIO()
    state: dict[str, bool] = {"ok": False, "done": False}

    def _worker() -> None:
        try:
            # exec çıktısı (modelin koyduğu print vb.) logu kirletmesin
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                exec(code, ns, ns)  # noqa: S102 — yerel basit unit test sandbox'ı
                exec(test, ns, ns)  # noqa: S102
            state["ok"] = True
        except Exception:
            state["ok"] = False
        finally:
            state["done"] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=_EXEC_TIMEOUT_S)
    # Zaman aşımı -> model kodu sonsuz döngüde asıldı, başarısız say
    return state["ok"] if state["done"] else False


# ---------------------------------------------------------------------------
# Sonuç özeti yardımcıları (rapor üreticiler için)
# ---------------------------------------------------------------------------


def summarize(grades: list[bool]) -> dict:
    """Geçti/kaldı listesinden özet skor üretir."""
    total = len(grades)
    passed = sum(1 for g in grades if g)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "score": round(passed / total * 100, 1) if total else 0.0,
    }


def summarize_by_lang(details: list[dict], tasks: list[dict]) -> dict:
    """Dil bazında skor kırar (B3: Türkçe ayrı skor).

    Her görevin ``lang`` alanına göre {dil: summarize(...)} döndürür.
    Örnek: ``{"en": {"score": 84.0, ...}, "tr": {"score": 91.7, ...}}``
    """
    lang_of: dict[str, str] = {t["id"]: t.get("lang", "en") for t in tasks}
    per_lang: dict[str, list[bool]] = {}
    for d in details:
        lang = lang_of.get(str(d.get("id") or ""), "en")
        per_lang.setdefault(lang, []).append(bool(d.get("pass")))
    return {lang: summarize(grades) for lang, grades in sorted(per_lang.items())}


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval — kucuk ve buyuk orneklemler icin guven araligi (yuzde).

    Ornek: wilson_ci(10, 10) -> (72.2, 100.0)
    """
    if n == 0:
        return 0.0, 0.0
    z = 1.96 if confidence == 0.95 else 2.576
    p_hat = successes / n
    center = (p_hat + z**2 / (2 * n)) / (1 + z**2 / n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    ci_low = round(max(0.0, center - margin) * 100, 1)
    ci_high = round(min(1.0, center + margin) * 100, 1)
    return ci_low, ci_high


# ---------------------------------------------------------------------------
# McNemar eşli karşılaştırma (Adım 3, 06.11.2026 — ADR-0015)
# ---------------------------------------------------------------------------
# Wilson tek modelin marjinal skorunun CI'sıdır; iki modelin eşli
# (aynı görev kümesi) farkının anlamlılığını ölçmez. McNemar testi yalnız
# discordant (uyumsuz) çiftlere bakar: A-geçti/B-kaldı (b) ve A-kaldı/B-geçti (c).
# Exact binom hesabı stdlib `math.comb` ile yapılır; scipy YOK (Y22: ağır
# bağımlılık §9.2 ister — tek fonksiyon için değmez). Küçük n'de (discordant<25)
# exact kullanılır, büyük n'de aynı formül çakışması için yine exact (n<=500
# pratik sınır; 500+ discordant'ta normal yaklaşıma bakılır — bkz. _mcnemar_p).
_MCNEMAR_EXACT_MAX = 500


def _mcnemar_p(b: int, c: int) -> float:
    """İki yönlü exact binom p-değeri (discordant b+c üzerinden).

    H0: b ~ Binom(n, 0.5). İki yönlü p = 2*P(X <= min(b, c)) (1 ile sınırlı).
    """
    n = b + c
    if n == 0:
        return 1.0
    if n > _MCNEMAR_EXACT_MAX:
        # Normal yaklaşıma (continuity correction): z = (|b-c|-1)/sqrt(n)
        z = (abs(b - c) - 1) / math.sqrt(n)
        # erfc tabanlı iki yönlü p: erf(z/sqrt(2)) -> 1-erf
        p = math.erfc(z / math.sqrt(2.0))
        return min(1.0, max(0.0, p))
    k_min = min(b, c)
    total = 0.5**n
    tail = sum(math.comb(n, k) * total for k in range(0, k_min + 1))
    return min(1.0, 2.0 * tail)


def mcnemar_test(a_pass: list[bool], b_pass: list[bool]) -> dict:
    """Eşli McNemar testi (exact, stdlib).

    Args:
        a_pass: Model A'nın görev bazında geç/kal listesi (True=geçti).
        b_pass: Model B'nin aynı görevlerdeki geç/kal listesi.

    Returns:
        {n, b, c, discordant, p_value, significant (p<0.05), note}
        b = A-geçti/B-kaldı, c = A-kaldı/B-geçti, discordant = b+c.
    """
    if len(a_pass) != len(b_pass):
        raise ValueError("McNemar eşli listeler aynı uzunlukta olmalı")
    b = sum(1 for a, bb in zip(a_pass, b_pass) if a and not bb)
    c = sum(1 for a, bb in zip(a_pass, b_pass) if not a and bb)
    p = _mcnemar_p(b, c)
    return {
        "n": len(a_pass),
        "b": b,
        "c": c,
        "discordant": b + c,
        "p_value": round(p, 6),
        "significant": p < 0.05,
    }


def compare_details(details_a: list[dict], details_b: list[dict]) -> dict:
    """İki modelin per-görev detaylarından McNemar + drill-down üretir.

    details anahtarları: {"id": str, "pass": bool}. Eşleme `id` ile yapılır;
    ortak id'ler sıralanarak eşli liste kurulur. Drill-down satırları:
    [{id, a_pass, b_pass, category}] — category: both_pass/both_fail/a_only/b_only.
    """
    pass_a = {str(d.get("id") or ""): bool(d.get("pass")) for d in details_a}
    pass_b = {str(d.get("id") or ""): bool(d.get("pass")) for d in details_b}
    common = sorted(set(pass_a) & set(pass_b))
    a_list = [pass_a[k] for k in common]
    b_list = [pass_b[k] for k in common]
    mc = mcnemar_test(a_list, b_list)
    rows: list[dict] = []
    for task_id, a_ok, b_ok in zip(common, a_list, b_list):
        if a_ok and b_ok:
            cat = "both_pass"
        elif not a_ok and not b_ok:
            cat = "both_fail"
        elif a_ok and not b_ok:
            cat = "a_only"
        else:
            cat = "b_only"
        rows.append({"id": task_id, "a_pass": a_ok, "b_pass": b_ok, "category": cat})
    return {**mc, "tasks": rows}
