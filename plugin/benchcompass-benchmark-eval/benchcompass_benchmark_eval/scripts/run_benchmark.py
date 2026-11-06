"""Benchmark koşucu — CLI entrypoint.

Kullanım:
    python -m benchcompass_benchmark_eval.scripts.run_benchmark [seçenekler]

Pipeline:
    python -m benchcompass_benchmark_eval.scripts.run_benchmark --pipeline
    -> koş -> data/results_<tarih>.json -> SQLite (entegre mod) -> index.md -> index.html

Bağımsız çalışma: plugin kendi verisiyle koşar; parent proje olmadan da çalışır.
"""

from __future__ import annotations

import argparse
import sys

from .. import config, grading, harness, llmfit_data, runner


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LLMFit Benchmark Eval — yerel model değerlendirme"
    )
    p.add_argument(
        "--models", nargs="+", default=None, help="Model listesi (yoksa kurulu tümü)"
    )
    p.add_argument(
        "--suites",
        default=None,
        help="Görev suite'leri, virgülle (ör. suite_default,suite_tr)",
    )
    p.add_argument("--no-speed", action="store_true", help="Hız testini atla")
    p.add_argument("--no-quality", action="store_true", help="Kalite testini atla")
    p.add_argument("--runs", type=int, default=None, help="Hız tekrar sayısı")
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Determinizm seed'i — görev sırası buradan türetilir (P0-4)",
    )
    p.add_argument(
        "--json-out",
        default=None,
        help="Sonuç JSON yolu (varsayılan data/results_<tarih>.json)",
    )
    p.add_argument(
        "--llmfit-data-dir", default=None, help="llmfit data/ yolu (entegre mod)"
    )
    p.add_argument(
        "--live-api",
        action="store_true",
        help="Sprint 34: canlı llmfit API kaynağını dene (parent/snapshot yoksa; "
        "erişilemezse yok gibi davranır — Local-First)",
    )
    p.add_argument(
        "--pipeline",
        action="store_true",
        help="Koş + SQLite + MD + HTML (tam otomatik)",
    )
    p.add_argument(
        "--context-stress",
        default=None,
        help="B2: context stres testi — virgülle uzunluklar (ör. 32k,64k,128k)",
    )
    p.add_argument(
        "--retrieval",
        action="store_true",
        help="B4: embedding retrieval kalitesi testini çalıştır (embedding modeller)",
    )
    return p.parse_args(argv)


def _checkpoint(json_out, models, tasks):
    """Her model bitince kısmi koşuyu JSON'a yazan callback üretir."""
    from datetime import datetime, timezone

    from .. import config as cfg

    def _cb(model_name, model_result, partial_results):
        partial = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hardware": runner.load_hardware(),
            "conditions": {
                "speed_runs": cfg.DEFAULTS["speed_runs"],
                "temperature": cfg.DEFAULTS["temperature"],
                "quality_num_predict": cfg.DEFAULTS["quality_num_predict"],
                "speed_num_predict": cfg.DEFAULTS["speed_num_predict"],
                "think": cfg.DEFAULTS["think"],
                "ollama_url": cfg.OLLAMA_URL,
            },
            "task_ids": [t["id"] for t in tasks],
            "tasks": tasks,
            "models": partial_results,
        }
        runner.save_results(partial, json_out)
        q = model_result.get("quality") or {}
        s = model_result.get("speed") or {}
        print(
            f"  [checkpoint] {model_name}: tok/s={s.get('gen_tps') or 0:.1f} "
            f"kalite={q.get('score')}% -> {json_out}"
        )
        import sys

        sys.stdout.flush()

    return _cb


def _parse_ctx_lengths(raw: str) -> list[int]:
    """'32k,64k,128k' -> [32000, 64000, 128000]"""
    out = []
    for part in raw.split(","):
        part = part.strip().lower()
        if not part:
            continue
        mult = 1000 if part.endswith("k") else 1
        num = part[:-1] if part.endswith("k") else part
        out.append(int(float(num) * mult))
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    available = harness.available_models()
    if not available:
        print("Ollama'ya ulaşılamıyor veya hiç model yok. `ollama serve` çalışıyor mu?")
        return 1

    models = args.models or available
    models = [m for m in models if m in available]
    if not models:
        print("Seçilen modeller kurulu değil. Kurulu: " + ", ".join(available))
        return 1

    tasks = grading.load_suites(args.suites.split(",") if args.suites else None)
    print(f"Modeller : {models}")
    print(f"Görevler : {len(tasks)} görev")
    print(
        f"Koşullar : runs={args.runs or config.DEFAULTS['speed_runs']}, "
        f"temp={config.DEFAULTS['temperature']}, think={config.DEFAULTS['think']}, "
        f"seed={args.seed}"
    )

    run = runner.run_eval(
        models,
        tasks,
        speed_runs=args.runs,
        do_speed=not args.no_speed,
        do_quality=not args.no_quality,
        on_model_done=_checkpoint(args.json_out, models, tasks),
        ctx_lengths=_parse_ctx_lengths(args.context_stress)
        if args.context_stress
        else None,
        do_retrieval=args.retrieval,
        seed=args.seed,
    )

    out_path = runner.save_results(run, args.json_out)
    print(f"Sonuç yazıldı: {out_path}")

    # Özet
    for m in run["models"]:
        s = m.get("speed") or {}
        q = m.get("quality") or {}
        tps = s.get("gen_tps")
        score = q.get("score")
        print(
            f"  {m['model']:<20} tok/s={tps or 0:>7.1f}  prefill={s.get('prefill_tps') or 0:>7.0f}"
            f"  TTFT={s.get('ttft_ms') or 0:>7.0f}ms  kalite={score}%"
        )

    # llmfit veri modu (raporlar için)
    llmfit = llmfit_data.resolve(args.llmfit_data_dir, live_api=args.live_api)
    print(
        f"llmfit veri modu: {llmfit.mode}"
        + (f" ({llmfit.source_path})" if llmfit.source_path else "")
    )

    # SQLite (entegre mod)
    db_result = runner.write_sqlite(run)
    if db_result:
        if db_result.get("error"):
            print(f"SQLite uyarısı: {db_result['error']}")
        else:
            print(f"SQLite: {db_result['inserted']} ölçüm eklendi -> {db_result['db']}")
    else:
        print(
            "SQLite: parent benchmark_history.db bulunamadı (standalone mod, atlandı)"
        )

    # Pipeline: rapor üret
    if args.pipeline:
        from ..scripts.generate_html import generate_html
        from ..scripts.generate_md import generate_md

        md = generate_md(out_path)
        html = generate_html(out_path)
        print(f"MD rapor : {md}")
        print(f"HTML rapor: {html}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
