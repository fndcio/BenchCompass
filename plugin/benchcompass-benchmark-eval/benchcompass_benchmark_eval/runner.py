"""Değerlendirme akışı — model koşusu, sonuç birleştirme, SQLite yazım.

Bağımsız çalışma ilkesi: runner kendi verisiyle çalışır; parent proje
(blob DB vb.) yoksa atlanır.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, grading, harness


def evaluate_model(
    model: str, tasks: list[dict], speed_runs: int, do_speed: bool, do_quality: bool
) -> dict:
    """Tek model için hız + kalite ölçümü yapar."""
    result: dict[str, Any] = {"model": model, "speed": None, "quality": None}

    if do_speed:
        speeds = []
        for _ in range(speed_runs):
            try:
                speeds.append(harness.measure_speed(model))
            except Exception as e:  # noqa: BLE001 — tek tekrar başarısız olursa akış durmasın
                speeds.append({"error": str(e)})
        ok = [s for s in speeds if s.get("gen_tps")]
        result["speed"] = max(
            ok,
            key=lambda s: s["gen_tps"],
            default=(speeds[0] if speeds else {"error": "ölçüm yok"}),
        )
        result["speed_runs"] = speeds

    if do_quality:
        details = []
        for task in tasks:
            try:
                if task.get("type") == "vision":
                    img = harness.vision_image(task.get("image", "solid_red"))
                    text = harness.generate_vision(model, task["prompt"], img)
                else:
                    text = harness.generate(
                        model,
                        task["prompt"],
                        num_predict=config.DEFAULTS["quality_num_predict"],
                        temperature=config.DEFAULTS["temperature"],
                        think=config.DEFAULTS["think"],
                    )
                passed = grading.grade_task(task, text)
                details.append(
                    {
                        "id": task["id"],
                        "type": task.get("type"),
                        "pass": passed,
                        "answer": text[:160],
                    }
                )
            except Exception as e:  # noqa: BLE001
                details.append(
                    {
                        "id": task["id"],
                        "type": task.get("type"),
                        "pass": False,
                        "error": str(e),
                    }
                )
        summary = grading.summarize([d["pass"] for d in details])
        ci_low, ci_high = grading.wilson_ci(summary["passed"], summary["total"])
        result["quality"] = {
            **summary,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "by_lang": grading.summarize_by_lang(details, tasks),
            "details": details,
        }
    return result


def write_sqlite(run: dict) -> dict | None:
    """Sonucu parent benchmark_history.db 'benchmarks' tablosuna yazar.

    Entegre mod: parent DB varsa kaydedilir, yoksa None döner (standalone).
    """
    db_path = config.find_parent_sqlite()
    if db_path is None:
        return None
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        created = []
        for m in run.get("models", []):
            speed = m.get("speed") or {}
            if not speed.get("gen_tps"):
                continue
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO benchmarks(model, provider, measured_tps, ttft_ms, total_tokens,"
                " wall_clock_s, shared, error, created_at, source)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    m["model"],
                    "ollama",
                    speed.get("gen_tps"),
                    speed.get("ttft_ms"),
                    speed.get("eval_count"),
                    round((speed.get("total_ms") or 0) / 1000, 2),
                    0,
                    None,
                    now,
                    "plugin-eval",
                ),
            )
            created.append(m["model"])
        con.commit()
        con.close()
        return {"db": str(db_path), "inserted": len(created), "models": created}
    except sqlite3.Error as e:
        return {"db": str(db_path), "error": str(e), "inserted": 0}


def quant_comparison(results: list[dict]) -> list[dict]:
    """Aynı aileye ait farklı quant'ları gruplayıp karşılaştırma yapısı döndürür.

    B1 (çoklu quant): yalnızca en az 2 farklı quant'ı olan aileler dahil edilir.
    Her grup:
        {
            "family": "qwen3:8b",
            "entries": [
                {"model", "quant", "gen_tps", "prefill_tps", "ttft_ms", "score"},
                ...
            ]
        }
    """
    families: dict[str, list[dict]] = {}
    for r in results:
        families.setdefault(harness.model_family(r["model"]), []).append(r)

    groups: list[dict] = []
    for fam, rows in sorted(families.items()):
        distinct_quants = {harness.model_quant(r["model"]) for r in rows}
        if len([q for q in distinct_quants if q]) < 2:
            continue
        entries = []
        for r in sorted(rows, key=lambda x: harness.model_quant(x["model"]) or ""):
            s = r.get("speed") or {}
            q = r.get("quality") or {}
            entries.append(
                {
                    "model": r["model"],
                    "quant": harness.model_quant(r["model"]) or "default",
                    "gen_tps": s.get("gen_tps"),
                    "prefill_tps": s.get("prefill_tps"),
                    "ttft_ms": s.get("ttft_ms"),
                    "score": q.get("score"),
                }
            )
        groups.append({"family": fam, "entries": entries})
    return groups


def pairwise_comparison(results: list[dict]) -> list[dict]:
    """Tüm model çiftleri için McNemar eşli karşılaştırma (kalite detaylarından).

    Her kayıt: {model_a, model_b, n, b, c, discordant, p_value, significant,
    tasks} — tasks drill-down satırları (a_only/b_only öncelikli değil, id sırası).
    Kalite detayı olmayan modeller atlanır. Model sırası A<B leksikografik.
    """
    pairs: list[dict] = []
    qualified = [
        r
        for r in results
        if isinstance(r.get("quality"), dict)
        and isinstance(r["quality"].get("details"), list)
    ]
    qualified.sort(key=lambda r: str(r.get("model")))
    for i in range(len(qualified)):
        for j in range(i + 1, len(qualified)):
            ra, rb = qualified[i], qualified[j]
            cmp = grading.compare_details(
                ra["quality"]["details"], rb["quality"]["details"]
            )
            pairs.append(
                {
                    "model_a": ra["model"],
                    "model_b": rb["model"],
                    **cmp,
                }
            )
    return pairs


def context_stress_test(
    models: list[str],
    ctx_lengths: list[int],
    needle: str | None = None,
    question: str | None = None,
) -> dict:
    """B2: Tüm modeller için uzun-context stres testi (needle-in-haystack).

    Sonuç yapısı: {model_adı: [{ctx_tokens, prefill_tps, recall, ...}, ...]}
    """
    needle = needle or "7GOLDEN42"
    question = question or "What is the secret code hidden in the text?"
    results: dict[str, list[dict]] = {}
    for m in models:
        rows = []
        for ctx in ctx_lengths:
            try:
                rows.append(harness.context_stress(m, ctx, needle, question))
            except Exception as e:  # noqa: BLE001 — tek context başarısızsa akış durmasın
                rows.append({"ctx_tokens": ctx, "error": str(e)})
        results[m] = rows
    return results


# --- B4: RAG / embedding retrieval kalitesi ---------------------------------
RETRIEVAL_CORPUS = [
    {
        "id": "python",
        "text": (
            "Python is a high-level general-purpose programming language "
            "designed by Guido van Rossum and first released in 1991."
        ),
    },
    {
        "id": "sqlite",
        "text": (
            "SQLite is a C library that provides a lightweight, disk-based "
            "database engine that requires no separate server process."
        ),
    },
    {
        "id": "rust",
        "text": (
            "Rust is a multi-paradigm systems programming language focused on "
            "performance and memory safety without a garbage collector."
        ),
    },
    {
        "id": "ollama",
        "text": (
            "Ollama is a local inference server that runs large language models "
            "directly on your own hardware and exposes a REST API."
        ),
    },
]

RETRIEVAL_QUERIES = [
    {"query": "Which language was created by Guido van Rossum?", "expected": "python"},
    {
        "query": "Which lightweight database engine is disk-based and serverless?",
        "expected": "sqlite",
    },
    {
        "query": "What memory-safe systems programming language has no garbage collector?",
        "expected": "rust",
    },
]


def retrieval_test(
    models: list[str],
    corpus: list[dict] | None = None,
    queries: list[dict] | None = None,
) -> dict:
    """B4: embedding retrieval kalitesi — sorgunun doğru dokümanı en üstte mi?

    Dokümanlar model başına bir kez embed edilir; sorgu her seferinde ayrı.
    Sonuç: {model: {queries: [...], passed, total}} veya hata durumunda error.
    """
    corpus = corpus or RETRIEVAL_CORPUS
    queries = queries or RETRIEVAL_QUERIES
    out: dict[str, dict] = {}
    for m in models:
        try:
            doc_emb = [(harness.embed(m, d["text"]), d["id"]) for d in corpus]
        except Exception as e:  # noqa: BLE001 — embedding modeli değilse akış durmasın
            out[m] = {"error": str(e), "queries": [], "passed": 0, "total": 0}
            continue
        rows = []
        for q in queries:
            try:
                qv = harness.embed(m, q["query"])
                scored = [(harness.cosine(qv, dv), did) for dv, did in doc_emb]
                scored.sort(reverse=True)
                top = scored[0][1] if scored else None
                rows.append(
                    {
                        "query": q["query"],
                        "expected": q["expected"],
                        "top": top,
                        "pass": top == q["expected"],
                        "top_score": round(scored[0][0], 4) if scored else None,
                    }
                )
            except Exception as e:  # noqa: BLE001
                rows.append({"query": q["query"], "error": str(e), "pass": False})
        out[m] = {
            "queries": rows,
            "passed": sum(1 for r in rows if r.get("pass")),
            "total": len(rows),
        }
    return out


def hash_tasks(tasks: list[dict]) -> str:
    """Görev setinin deterministik SHA256 parmak izi."""
    raw = json.dumps(
        [
            {
                "id": str(t.get("id")),
                "prompt": str(t.get("prompt")),
                "expected": str(t.get("expected")),
            }
            for t in tasks
        ],
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def run_eval(
    models: list[str],
    tasks: list[dict],
    speed_runs: int | None = None,
    do_speed: bool = True,
    do_quality: bool = True,
    on_model_done=None,
    ctx_lengths: list[int] | None = None,
    do_retrieval: bool = False,
    seed: int = 42,
) -> dict:
    """Tüm modelleri değerlendirir; koşu özetini döndürür.

    on_model_done: her model bittiğinde (model_adı, model_sonucu, kısmi_koşu)
    çağrılır — uzun koşularda checkpoint kaydı için kullanılır.
    ctx_lengths: verilirse B2 context stres testi de koşulur (ör. [32000, 64000]).
    do_retrieval: verilirse B4 embedding retrieval kalitesi de ölçülür.
    """
    runs = speed_runs or config.DEFAULTS["speed_runs"]
    # P0-4: seed hesaplamaya BAĞLIDIR — görev sırası seed'den türetilir.
    # Aynı seed → aynı sıra → tekrarlanabilir koşu; kalite skorları sıra-duyarsızdır.
    # task_sha özgün (kanonik) listeden hesaplanır; sıra shuffle ile değişmez.
    ordered_tasks = list(tasks)
    random.Random(seed).shuffle(ordered_tasks)
    task_order = [str(t.get("id")) for t in ordered_tasks]
    results = []
    for m in models:
        res = evaluate_model(m, ordered_tasks, runs, do_speed, do_quality)
        results.append(res)
        if on_model_done is not None:
            on_model_done(m, res, results)
    run = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hardware": load_hardware(),
        "task_sha": hash_tasks(tasks),
        "seed": seed,
        "task_order": task_order,
        "n_runs": runs,
        "conditions": {
            "speed_runs": runs,
            "temperature": config.DEFAULTS["temperature"],
            "quality_num_predict": config.DEFAULTS["quality_num_predict"],
            "speed_num_predict": config.DEFAULTS["speed_num_predict"],
            "think": config.DEFAULTS["think"],
            "ollama_url": config.OLLAMA_URL,
        },
        "task_ids": [t["id"] for t in tasks],
        "tasks": tasks,  # rapor üreticilerin self-contained çalışabilmesi için
        "models": results,
        "quant_compare": quant_comparison(results),  # B1: çoklu quant grupları
        "pairwise": pairwise_comparison(results),  # Adım 3: McNemar çiftleri
    }
    if ctx_lengths:
        run["context_stress"] = context_stress_test(
            [r["model"] for r in results], ctx_lengths
        )
    if do_retrieval:
        run["retrieval"] = retrieval_test([r["model"] for r in results])
    return run


def save_results(run: dict, out: str | None = None) -> Path:
    """Koşu sonucunu data/results_<tarih>.json'a yazar."""
    date = datetime.now().strftime("%Y-%m-%d")
    path = Path(out) if out else config.DATA_DIR / f"results_{date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_hardware() -> dict:
    """data/hardware.json okur; yoksa boş dict."""
    path = config.DATA_DIR / "hardware.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
