"""JSON sonuçlarından detaylı Markdown raporu üretir.

Deterministik: aynı girdi -> aynı çıktı. llmfit verisi varsa community
karşılaştırması eklenir; yoksa atlanır.

Kullanım:
    python -m benchcompass_benchmark_eval.scripts.generate_md --input data/results_2026-08-04.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import config, history, llmfit_data

# İyileştirme önerileri (statik, rapora gömülür) — sonraki geliştirmelerde
# genişletilebilir. Veri koda gömülmemesi ilkesine uygun olarak gelecekte
# ayrı bir JSON'a taşınabilir.
IMPROVEMENTS = [
    {
        "oncelik": "Kısa vade",
        "madde": "Görev suite'i sağlamlaştır",
        "detay": (
            "ar6 ((2^5)*3+14-8) gibi çoklu modelin ortaklaşa hatalı yanıt verdiği "
            "belirsiz maddeleri gözden geçir; her göreve net cevap biçimi ve "
            "parse talimatı ekle."
        ),
    },
    {
        "oncelik": "Kısa vade",
        "madde": "Çoklu quant karşılaştırma",
        "detay": (
            "Aynı modelin Q4_K_M vs Q8_0 vs QAT quant'larını ölç; hız/doğruluk "
            "trade-off'unu tek raporda göster."
        ),
    },
    {
        "oncelik": "Orta vade",
        "madde": "Context stres testi",
        "detay": (
            "32K/64K/128K context'te prefill hızı ve uzun metin hatırlama kalitesini "
            "ölç; KV cache quant etkisini raporla."
        ),
    },
    {
        "oncelik": "Orta vade",
        "madde": "Tam Türkçe suite",
        "detay": (
            "suite_tr.json'u 20+ göreve çıkar; Türkçe dil doğruluğu ve talimat "
            "takibi için ayrı skor ekle."
        ),
    },
    {
        "oncelik": "Orta vade",
        "madde": "Vision ve RAG görevleri",
        "detay": (
            "Görüntülü modeller (minicpm-v, Qwen3-VL) için vision görevleri, "
            "embedding modeller için retrieval kalite testleri ekle."
        ),
    },
    {
        "oncelik": "Uzun vade",
        "madde": "Community karşılaştırma panosu",
        "detay": (
            "llmfit benchmark_cache presets'leriyle (RTX 4070 Ti/3060 12GB) "
            "kendi ölçümlerini yan yana göster; sapma analizi yap."
        ),
    },
    {
        "oncelik": "Uzun vade",
        "madde": "Geçmiş arşivi ve otomatik koşu",
        "detay": (
            "SQLite 'benchmarks' tablosundan zaman serisi çiz; planlı koşularla "
            "model güncellemelerinin performans etkisini takip et."
        ),
    },
]


def _fmt(v: Any, suffix: str = "") -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}{suffix}"
    return f"{v}{suffix}"


def _task_matrix(tasks: list[dict]) -> str:
    lines = [
        "| ID | Tip | Dil | Zorluk | Kategori | Beklenen |",
        "|---|---|---|---|---|---|",
    ]
    for t in tasks:
        lines.append(
            f"| {t['id']} | {t.get('type')} | {t.get('lang', 'en')} | "
            f"{t.get('difficulty', '-')} | {t.get('category', '-')} | "
            f"{str(t.get('expected', ''))[:40]} |"
        )
    return "\n".join(lines)


def _per_model_table(run: dict) -> str:
    lines = [
        "| Model | Boyut | tok/s | prefill tok/s | TTFT (ms) | Kalite | EN | TR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in run.get("models", []):
        s = m.get("speed") or {}
        q = m.get("quality") or {}
        by_lang = q.get("by_lang") or {}
        lines.append(
            f"| {m['model']} | {_fmt(m.get('size_gb'), ' GB')} | {_fmt(s.get('gen_tps'))} "
            f"| {_fmt(s.get('prefill_tps'))} | {_fmt(s.get('ttft_ms'))} | "
            f"{q.get('passed', 0)}/{q.get('total', 0)} | "
            f"{_fmt(by_lang.get('en', {}).get('score'), '%')} | "
            f"{_fmt(by_lang.get('tr', {}).get('score'), '%')} |"
        )
    return "\n".join(lines)


def _task_passes(run: dict) -> str:
    """Per-model per-task geçti/kaldı matrisi."""
    models = run.get("models", [])
    if not models:
        return "_(veri yok)_"
    task_ids = run.get("task_ids", [])
    header = "| Model | " + " | ".join(task_ids) + " |"
    sep = "|" + "---|" * (len(task_ids) + 1)
    lines = [header, sep]
    for m in models:
        q = m.get("quality") or {}
        by_id = {d["id"]: d.get("pass") for d in q.get("details", [])}
        cells = []
        for tid in task_ids:
            p = by_id.get(tid)
            cells.append("✅" if p is True else ("❌" if p is False else "•"))
        lines.append(f"| {m['model']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _retrieval_section(run: dict) -> str:
    """B4: embedding retrieval kalitesi tablosu."""
    data = run.get("retrieval") or {}
    if not data:
        return "_(bu koşuda retrieval testi çalıştırılmadı — `--retrieval` ile tetiklenir)_"
    out = ["| Model | Doğruluk | Detay |", "|---|---|---|"]
    for model, r in data.items():
        if r.get("error"):
            out.append(f"| {model} | hata | {r['error'][:80]} |")
            continue
        detail = "; ".join(
            f"'{q['query'][:40]}{'…' if len(q['query']) > 40 else ''}' -> {q.get('top')}"
            for q in r["queries"]
        )
        out.append(f"| {model} | {r['passed']}/{r['total']} | {detail} |")
    return "\n".join(out)


def _context_stress_section(run: dict) -> str:
    """B2: context stres sonuçları (prefill tok/s + recall) tablosu."""
    data = run.get("context_stress") or {}
    if not data:
        return (
            "_(bu koşuda context stres testi çalıştırılmadı — "
            "`--context-stress 32k,64k,128k` ile tetiklenir)_"
        )
    ctx_cols: list[int] = []
    for rows in data.values():
        for r in rows:
            c = r.get("ctx_tokens")
            if c is not None and c not in ctx_cols:
                ctx_cols.append(c)
    ctx_cols.sort()
    header = "| Model | " + " | ".join(f"{c // 1000}K" for c in ctx_cols) + " |"
    sep = "|" + "---|" * (len(ctx_cols) + 1)
    out = [header, sep]
    for model, rows in data.items():
        by_ctx = {r.get("ctx_tokens"): r for r in rows}
        cells = []
        for c in ctx_cols:
            r = by_ctx.get(c) or {}
            if r.get("error"):
                cells.append("hata")
                continue
            prefill = r.get("prefill_tps")
            recall = r.get("recall")
            recall_s = (
                "hatırladı"
                if recall is True
                else ("hatırlamadı" if recall is False else "veri yok")
            )
            prefill_s = f"{prefill:.0f}" if prefill else "-"
            cells.append(f"{prefill_s} tok/s · {recall_s}")
        out.append(f"| {model} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def _quant_section(run: dict) -> str:
    """B1: Çoklu quant karşılaştırma tablosu (veri yoksa kısa not)."""
    groups = run.get("quant_compare") or []
    if not groups:
        return "_(bu koşuda aynı modelin birden çok quant'ı ölçülmedi — `--models qwen3:8b-q4_K_M qwen3:8b-q8_0` ile tetiklenir)_"
    out = []
    for g in groups:
        out.append(f"### {g['family']}")
        lines = ["| Quant | tok/s | prefill tok/s | TTFT (ms) | Kalite skoru |"]
        lines.append("|---|---|---|---|---|")
        best = max(g["entries"], key=lambda e: e.get("gen_tps") or 0)
        for e in g["entries"]:
            mark = " ← en hızlı" if e is best else ""
            lines.append(
                f"| {e['quant']} | {_fmt(e.get('gen_tps'))} | "
                f"{_fmt(e.get('prefill_tps'))} | {_fmt(e.get('ttft_ms'))} | "
                f"{_fmt(e.get('score'), '%')}{mark} |"
            )
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _match_community(local_model: str, preset_rows: list[dict]) -> list[dict]:
    """Ollama model adını community preset satırlarıyla gevşek eşleştirir.

    Boşluk/tire/alt çizgi yok sayılır: ``llama3:8b`` -> "llama3" + "8" içeren
    displayName/hfId satırları (ör. "Llama 3 8B Instruct").
    """

    def _norm(s: str) -> str:
        return re.sub(r"[\s\-_]", "", str(s).lower())

    base = _norm(local_model.split(":", 1)[0])
    tag = local_model.split(":", 1)[-1]
    m = re.search(r"(\d+(?:\.\d+)?)b", tag, re.IGNORECASE)
    size = m.group(1) if m else ""
    out = []
    for r in preset_rows:
        mm = r.get("model") or {}
        name = _norm(mm.get("displayName") or mm.get("hfId") or "")
        if base and base in name and (not size or size in name):
            out.append(r)
    return out


def _community_panel_section(run: dict, llmfit: llmfit_data.LlmfitData) -> str:
    """B5: community karşılaştırma panosu — kendi ölçüm vs community."""
    if not llmfit.is_enriched():
        return "_(llmfit verisi çözümlenemedi — bağımsız mod, bu bölüm atlandı)_"
    presets = llmfit.speed_presets(["RTX 4070 Ti (12 GB)", "RTX 3060 (12 GB)"])
    if not presets:
        return "_(benchmark_cache preset bulunamadı)_"
    out = []
    for name, rows in presets.items():
        rows = [r for r in rows if r.get("tokSOut")]
        rows.sort(key=lambda r: r.get("tokSOut") or 0, reverse=True)
        out.append(f"### Community: {name}")
        local_rows = []
        for m in run.get("models", []):
            s = m.get("speed") or {}
            if not s.get("gen_tps"):
                continue
            matches = _match_community(m["model"], rows)
            if matches:
                best = max(matches, key=lambda r: r.get("tokSOut") or 0)
                local_rows.append((m["model"], s["gen_tps"], best))
        if local_rows:
            lines = [
                "| Yerel model | Yerel tok/s | Community tok/s | Fark (%) |",
                "|---|---|---|---|",
            ]
            for model, lv, cr in local_rows:
                cv = cr.get("tokSOut")
                diff = (lv / cv - 1) * 100 if cv else None
                cm = cr.get("model") or {}
                lines.append(
                    f"| {model} | {lv:.1f} | {cv:.1f} "
                    f"({str(cm.get('displayName') or cm.get('hfId'))[:28]}) | "
                    f"{_fmt(diff, '%')} |"
                )
            out.append("\n".join(lines))
        else:
            out.append("_(eşleşen model yok)_")
    return "\n\n".join(out)


def _history_section(run: dict) -> str:
    """B5: SQLite geçmiş/zaman serisi özeti (per-model trend)."""
    series = history.load_history()
    if not series:
        return (
            "_(parent benchmark_history.db bulunamadı veya ölçüm yok — "
            "standalone mod, bu bölüm atlandı)_"
        )
    summ = history.summarize_history(series)
    lines = ["| Model | Ölçüm | Son tok/s | Trend |", "|---|---|---|---|"]
    for model, info in sorted(summ.items()):
        lines.append(
            f"| {model} | {info['measurements']} | {_fmt(info['last_tps'])} | "
            f"{info['trend']} |"
        )
    return "\n".join(lines)


def _community_section(llmfit: llmfit_data.LlmfitData) -> str:
    if not llmfit.is_enriched():
        return "_(llmfit verisi çözümlenemedi — bağımsız mod, bu bölüm atlandı)_"
    out = []
    for name, rows in llmfit.speed_presets(
        ["RTX 4070 Ti (12 GB)", "RTX 3060 (12 GB)"]
    ).items():
        out.append(f"### {name}")
        rows = [r for r in rows if r.get("tokSOut")]
        rows.sort(key=lambda r: r.get("tokSOut") or 0, reverse=True)
        for r in rows[:8]:
            m = r.get("model", {})
            name_model = m.get("displayName") or m.get("hfId") or "?"
            out.append(
                f"- **{name_model}** · {r.get('tokSOut'):.1f} tok/s · "
                f"{r.get('engine', {}).get('quantization', '?')} · "
                f"{r.get('engine', {}).get('engineName', '?')} · TTFT {_fmt(r.get('ttftMs'))}ms"
            )
    return "\n".join(out)


def _standard_task_bridge() -> str:
    """P0-5: standart görev köprüsü satırları — TEK KAYNAK config.STANDARD_TASK_MAP.

    Değerler burada sabitlenmez; config değişirse rapor otomatik izler (DRY/Y27).
    """
    return "\n".join(
        f"- **{key}**: {value}" for key, value in config.STANDARD_TASK_MAP.items()
    )


def generate_md(input_path: str | Path) -> Path:
    """results JSON'dan reports/index.md üretir ve yolunu döndürür."""
    inp = Path(input_path)
    run = json.loads(inp.read_text(encoding="utf-8"))
    hw = run.get("hardware") or {}
    cond = run.get("conditions") or {}
    llmfit = llmfit_data.resolve()

    task_ids = run.get("task_ids", [])
    tasks = run.get("tasks", [])
    models = run.get("models", [])
    speed_rows: list[tuple[str, float]] = []
    for m in models:
        v = (m.get("speed") or {}).get("gen_tps")
        if v is not None:
            speed_rows.append((m["model"], float(v)))
    best_speed = max(speed_rows, key=lambda x: x[1], default=(None, None))
    qual_rows: list[tuple[str, float]] = []
    for m in models:
        sc = (m.get("quality") or {}).get("score")
        if sc is not None:
            qual_rows.append((m["model"], float(sc)))
    best_qual = max(qual_rows, key=lambda x: x[1], default=(None, None))

    gen_at = run.get("generated_at") or datetime.now().isoformat(timespec="seconds")
    md = f"""# LLMFit Benchmark Eval — Rapor

**Üretim tarihi:** {gen_at}
**Kaynak sonuç:** `{inp}`
**llmfit veri modu:** {llmfit.mode} ({llmfit.source_path or "-"})

## Donanım & Koşullar

| Özellik | Değer |
|---|---|
| GPU | {hw.get("gpu") or "-"} |
| VRAM | {_fmt(hw.get("vram_gb"), " GB")} |
| RAM | {_fmt(hw.get("ram_gb"), " GB")} |
| CPU | {hw.get("cpu") or "-"} |
| Runtime | Ollama {hw.get("ollama_version") or "-"} ({hw.get("ollama_url") or cond.get("ollama_url") or "-"}) |
| Sıcaklık | {cond.get("temperature")} |
| think modu | {cond.get("think")} |
| Hız tekrarı | {cond.get("speed_runs")} |
| Kalite token bütçesi | {cond.get("quality_num_predict")} |
| Hız testi çıktı uzunluğu | {cond.get("speed_num_predict")} |

**Ölçüm yöntemi:** tok/s, `eval_count/eval_duration` (Ollama resmi metriği). Prefill
`prompt_eval_count/prompt_eval_duration`. TTFT akışlı istekle ilk token zamanı (bayt
bayt okuma). Kalite görevleri sıcaklık 0.0 ile deterministik; kod görevleri `exec` +
birim test ile doğrulanır.

## Görev Matrisi ({len(task_ids)} görev — EN + TR)

{_task_matrix(tasks)}

### Standart Akademik Görev Köprüsü (P0-5)

{_standard_task_bridge()}

## Sonuçlar

{_per_model_table(run)}

### En hızlı / En doğru

- En hızlı: **{best_speed[0]}** ({_fmt(best_speed[1], " tok/s")})
- En doğru: **{best_qual[0]}** ({_fmt(best_qual[1], "%")})

## Per-Model Per-Görev Geçti/Kaldı

{_task_passes(run)}

## Quant Karşılaştırma (B1)

{_quant_section(run)}

## Context Stres Testi (B2)

Needle-in-haystack: gizli kod uzun metnin %50 derinliğine gömülür ve sorulur.
Prefill tok/s, istenen context uzunluğunda ölçülür.

{_context_stress_section(run)}

## Retrieval / Embedding Kalitesi (B4)

{_retrieval_section(run)}

## Community Karşılaştırma Panosu (B5)

Kendi ölçümlerinizle community (llmfit benchmark_cache) değerleri yan yana.

{_community_panel_section(run, llmfit)}

## Geçmiş / Zaman Serisi (B5)

Parent `benchmark_history.db`'deki `benchmarks` tablosundan per-model trend.

{_history_section(run)}

## Community Karşılaştırma (llmfit verisi)

{_community_section(llmfit)}

## Analiz ve İyileştirme Önerileri

| Öncelik | Başlık | Detay |
|---|---|---|
{chr(10).join(f"| {i['oncelik']} | {i['madde']} | {i['detay']} |" for i in IMPROVEMENTS)}

---
*Rapor üretici: `benchcompass_benchmark_eval.scripts.generate_md` · ROADMAP: `ROADMAP.md`*
"""
    out = config.REPORTS_DIR / "index.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="JSON -> Markdown rapor")
    p.add_argument("--input", required=True, help="Sonuç JSON")
    args = p.parse_args(argv or sys.argv[1:])
    path = generate_md(args.input)
    print(f"MD rapor yazıldı: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
