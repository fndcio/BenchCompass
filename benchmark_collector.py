"""LLMFit benchmark collector.

llmfit serve (port 8787) HTTP API'sini periyodik olarak sorgular ve top
modelleri SQLite'e yazar.

Sprint 3 degisiklikleri:
  - normalize() artik llmfit 'notes' metninden 7 yapilsal alan cikarir
    (required_vram_gb, required_ram_gb, quantization, param_count_b,
    context_length_supported/estimated_at, estimated_speed_tok_s).
  - Her model ayri try/except icine parse edilir; tek bir bozuk model
    butun snapshot'i dusurmez (Kriter #14).
  - INSERT yeni sutunlari da kapsar.
  - Migrasyon api.db.connect() icinde otomatik yapilir.

Sprint 6 degisiklikleri (Kriter #10):
  - argparse ile CLI flags:
      python benchmark_collector.py                    # tek seferlik
      python benchmark_collector.py --daily            # her gun 2:00'de (loop)
      python benchmark_collector.py --interval-hours 6 # 6 saatte bir (loop)
      python benchmark_collector.py --once             # tek seferlik (acik)
      python benchmark_collector.py --base http://...  # API base override
  - --daily / --interval-hours modunda uzun surenli bir loop calisir;
    signal.SIGINT (Ctrl+C) ile temiz kapanis saglanir.
  - Windows Task Scheduler ile zamanlama icin setup-scheduler-example.ps1
    ve README.txt guncellendi (exact schtasks komutu).

Sprint 7 degisiklikleri:
  - llmfit CLI'i dogrudan subprocess ile cagirma destegi:
      python benchmark_collector.py --source cli --limit 100
    Bu, llmfit serve yerine `llmfit fit --json` cagirir; boylece llmfit'in
    first-class alanlarina (params_b, memory_required_gb, estimated_tps,
    fit_level, is_moe, capabilities, score_components) direkt erisiriz.
    Sprint 3'teki notes-regex parse artik yedek (fallback) konumunda.
  - Varsayilan LIMIT 8 -> 50.
  - Yeni DB sutunlari (migration): fit_level, is_moe, capabilities,
    disk_size_gb, llmfit_score (llmfit'in 'score' alani, fit_score'tan farkli).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# Kendi paketimizden import (api.*)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api.db import connect  # noqa: E402
from api.notes_parser import enrich_model  # noqa: E402

BASE = Path(__file__).resolve().parent
DB = BASE / "benchmark_history.db"
API_BASE = "http://localhost:8787"
USE_CASES = ["coding", "chat", "rag"]
LIMIT = 50  # Sprint 7: 8 -> 50. llmfit zaten donanıma gore filtreliyor.


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_llmfit_binary():
    """llmfit CLI binary'sini PATH'te arar. Bulamazsa None dondurur."""
    return shutil.which("llmfit")


_last_update_check = 0


def _maybe_update_llmfit_cache(force=False):
    """Gunde bir kez llmfit model cache'ini gunceller.

    llmfit update komutu yeni modeller eklendiginde embedded JSON catalog'u
    gunceller. llmfit 1.1.16'da soguk katalog 43 sn, sicak katalog ~5 sn surer;
    eski 30 sn tavanı soğuk kosuda komutu olduruyordu. Oldurulen surec
    yardimci alt surec (llmfit serve) birakirsa pipe'ta EOF gelmedigi icin
    subprocess.run sonsuza kadar bloklaniyordu. Bu yuzden tavan 180 sn'e
    cekildi ve cikti tutmayan sessiz bir cagri icin DEVNULL'a yonlendirildi
    (stdout/stderr pipe'a baglaninca alt surec pipe'i tutuyor).
    """
    global _last_update_check
    now = time.time()
    if not force and (now - _last_update_check) < 86400:  # 24 saat
        return
    binary = find_llmfit_binary()
    if not binary:
        return
    try:
        subprocess.run(
            [binary, "update"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )
        _last_update_check = now
    except (subprocess.TimeoutExpired, OSError):
        pass


def run_llmfit_fit_cli(limit=LIMIT, perfect=False, sort="score", extra_args=None):
    """llmfit fit --json komutunu dogrudan cagirir.

    Bu, llmfit serve API'sinden cok daha zengin veri verir:
    first-class alanlar: params_b, memory_required_gb, estimated_tps,
    fit_level, is_moe, capabilities, score_components, run_mode, vs.

    Geriye {'models': [...], 'system': {...}} formatinda dict dondurur.
    llmfit bulunamazsa veya hata verirse None dondurur.
    """
    binary = find_llmfit_binary()
    if not binary:
        return None
    cmd = [binary, "fit", "--json", "--limit", str(limit), "--sort", sort]
    if perfect:
        cmd.append("--perfect")
    if extra_args:
        cmd.extend(extra_args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if proc.returncode != 0:
            print(f"  [WARN] llmfit fit exit {proc.returncode}: {proc.stderr[:200]}")
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] llmfit fit hatasi: {e}")
        return None


def _safe_float(value):
    """Değeri güvenli şekilde float'a çevirir, olmazsa None döner."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value):
    """Değeri güvenli şekilde int'e çevirir, olmazsa None döner."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_param_count(m):
    """llmfit params_b veya parameter_count (string) alanından parametre sayısı."""
    params_b = m.get("params_b")
    if params_b is not None:
        return params_b
    pc = m.get("parameter_count")
    if not pc:
        return None
    # String "14.8B" formatı
    return _safe_float(str(pc).replace("B", "").replace("b", "").strip())


def _parse_context_fields(m):
    """context_length (supported) ve effective_context_length (estimated) çıkarır."""
    ctx_supported = _safe_int(m.get("context_length"))
    ctx_estimated = _safe_int(m.get("effective_context_length"))
    return ctx_supported, ctx_estimated


def _parse_capabilities(m):
    """capabilities listesini virgülle ayrılmış string'e çevirir."""
    caps = m.get("capabilities") or m.get("capability_ids") or []
    if isinstance(caps, list):
        return ",".join(str(c) for c in caps)
    return caps


def _build_notes_field(m):
    """notes alanını normalize edilmiş metne çevirir."""
    notes_raw = m.get("notes")
    if isinstance(notes_raw, (list, dict)):
        return json.dumps(notes_raw, ensure_ascii=False)
    return notes_raw or m.get("summary") or ""


def _pick(m, keys, default=None):
    """İlk mevcut anahtarın değerini döndürür (fallback zinciri)."""
    for k in keys:
        v = m.get(k)
        if v is not None:
            return v
    return default


def _normalize_model(m, use_case):
    """Tek bir llmfit model yanıtını benchmark_models satırına dönüştürür.

    normalize()'in alt fonksiyonu — döngü gövdesi buradan çağrılır.
    """
    name = _pick(m, ("name", "model"), "Unknown")
    notes_raw = m.get("notes")
    notes_field = _build_notes_field(m)

    # First-class alanlar
    params_b = _parse_param_count(m)
    memory_required_float = _safe_float(m.get("memory_required_gb"))
    tps_float = _safe_float(m.get("estimated_tps") or m.get("measured_tps"))
    ctx_supported, ctx_estimated = _parse_context_fields(m)
    quant = m.get("best_quant")
    disk_size = _safe_float(m.get("disk_size_gb"))
    llmfit_score = _safe_float(m.get("score"))

    # Sprint 7 yeni alanlar
    fit_level = m.get("fit_level")
    is_moe = bool(m.get("is_moe", False))
    capabilities = _parse_capabilities(m)

    # Sprint 3 fallback: notes'tan çıkarma (first-class boş ise)
    enriched = enrich_model(name, notes_raw)

    # required_vram: llmfit memory_required öncelikli, yoksa notes
    required_vram = (
        memory_required_float
        if memory_required_float is not None
        else enriched["required_vram_gb"]
    )
    # required_ram: llmfit ayri vermiyor; ~1.15x VRAM tahmini
    required_ram = enriched["required_ram_gb"]
    if required_ram is None and required_vram is not None:
        required_ram = round(required_vram * 1.15, 2)

    return {
        "name": name,
        "provider": _pick(m, ("provider", "engine"), "-"),
        "use_case": _pick(m, ("useCase", "use_case", "category"), use_case),
        "fit_score": float(_pick(m, ("fitScore", "fit_score", "score"), 0) or 0),
        "context_window": int(
            _pick(m, ("contextWindow", "context_window", "ctx"), ctx_supported or 0)
            or 0
        ),
        "notes": notes_field,
        "required_vram_gb": required_vram,
        "required_ram_gb": required_ram,
        "context_length_supported": (
            ctx_supported
            if ctx_supported is not None
            else enriched["context_length_supported"]
        ),
        "context_length_estimated_at": (
            ctx_estimated
            if ctx_estimated is not None
            else enriched["context_length_estimated_at"]
        ),
        "quantization": quant or enriched["quantization"],
        "param_count_b": params_b
        if params_b is not None
        else enriched["param_count_b"],
        "estimated_speed_tok_s": (
            tps_float if tps_float is not None else enriched["estimated_speed_tok_s"]
        ),
        "fit_level": fit_level,
        "is_moe": is_moe,
        "capabilities": capabilities,
        "disk_size_gb": disk_size,
        "llmfit_score": llmfit_score,
        "run_mode": m.get("run_mode"),
    }


def normalize(data, use_case):
    """llmfit cevabini benchmark_models satir dict'lerine donusturur.

    Sprint 7: llmfit'in first-class alanlarini once kullanir. Eger bir alan
    first-class olarak yoksa (eski API cevaplari, llmfit serve), notes'tan
    regex ile cikarma (Sprint 3 notes_parser) devreye girer.

    Sprint 3 davranisi (her model ayri try/except) korunur.
    Refactor: model dönüşümü _normalize_model'e delege edildi (CC 49 → düşük).
    """
    arr = data if isinstance(data, list) else data.get("models", [])
    out = []
    for m in arr:
        try:
            out.append(_normalize_model(m, use_case))
        except Exception as e:
            # Tek model patladi: guncelle atla, gerisi devam etsin
            print(f"  [WARN] Model atlandi (parse hatasi): {e}")
            continue
    return out


def collect_openai_backend(
    backend_name: str, model_name: str = "default-local-model", runs: int = 1
) -> dict | None:
    """OpenAI uyumlu backend'den benchmark toplar ve benchmarks tablosuna yazar (P1-5)."""
    from api.openai_client import get_backend_url, run_openai_benchmark
    from api.routes.shared import _save_benchmark_record

    base_url, _ = get_backend_url(backend_name)
    print(f"[{backend_name}] {base_url} üzerinde benchmark toplanıyor...")
    try:
        bench_result = run_openai_benchmark(
            model=model_name,
            runs=runs,
            base_url=base_url,
        )
        bench_result["source"] = f"{backend_name}-collector"
        bench_result["provider"] = backend_name
        _save_benchmark_record(model_name, backend_name, bench_result)
        print(
            f"[{backend_name}] Ölçüm başarıyla kaydedildi: {bench_result.get('measured_tps')} tok/s"
        )
        return bench_result
    except Exception as exc:
        print(f"[{backend_name}] Hata (çıkarım sunucusuna bağlanılamadı): {exc}")
        return None


def collect(base=API_BASE, source="auto", limit=LIMIT, backend=None):
    """llmfit'ten top modelleri veya seçili backend'den benchmark cekip SQLite'e yazar.

    backend:
      'lmstudio' / 'llamacpp' / 'vllm': OpenAI uyumlu çıkarım sunucusundan benchmark toplar (P1-5)
      'ollama' / None: Standart llmfit / ollama akışı

    source:
      'auto'  : once llmfit CLI dener (en zengin veri), olmazsa HTTP API'ye dususer
      'cli'   : sadece llmfit CLI (subprocess). llmfit yoksa hata verir
      'api'   : sadece HTTP API (llmfit serve)
    """
    target_backend = backend or os.environ.get("BENCHCOMPASS_BACKEND")
    if target_backend and target_backend.lower() != "ollama":
        print(f"[collector] Çok-Backend modu aktif: {target_backend}")
        collect_openai_backend(target_backend)
        return
    # connect() semayi yaratir + migrate() ile yeni sutunlari ekler.
    con = connect()
    total = 0

    # Sprint 7: llmfit CLI kaynakli tek bir buyuk cekme (use-case bazli degil)
    # llmfit fit --json zaten donanima gore filtreler; ayri ayri use-case
    # cekmek yerine tek seferde cekip "all" olarak kaydedebiliriz.
    use_cli = source in ("cli", "auto") and find_llmfit_binary() is not None
    if use_cli:
        # Sprint 9: günlük model cache güncellemesi (sessiz, hızlı)
        _maybe_update_llmfit_cache()
        print(f"[cli] llmfit fit --json --limit {limit} cagriliyor...")
        data = run_llmfit_fit_cli(limit=limit)
        if data and data.get("models"):
            models = normalize(data, "all")
            # llmfit 'system' bilgisini de kullanabiliriz (ileride donanim profili
            # otomatik guncelleme icin). Su an sadece log.
            sys_info = data.get("system", {})
            print(
                f"[cli] llmfit sistem: {sys_info.get('gpu_name', '?')} "
                f"({sys_info.get('gpu_vram_gb', '?')} GB VRAM, "
                f"{sys_info.get('total_ram_gb', '?')} GB RAM)"
            )
            name = f"cli-fit-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            cur = con.execute(
                "INSERT INTO benchmark_runs(name,source,use_case) VALUES(?,?,?)",
                (name, "llmfit-cli", "all"),
            )
            run_id = cur.lastrowid
            _insert_models(con, run_id, models)
            con.commit()
            total += 1
            print(f"Collected via CLI: {len(models)} models -> run {run_id}")
            con.close()
            print(f"Total runs inserted: {total}")
            return
        elif source == "cli":
            print("[cli] llmfit CLI basarisiz ve source=cli, fallback yok.")
            con.close()
            return
        else:
            print("[cli] llmfit CLI basarisiz, HTTP APIye dusuruluyor...")

    # HTTP API yolu (use-case bazli, Sprint 3 davranisi)
    for use_case in USE_CASES:
        urls = [
            f"{base}/api/v1/models/top?limit={limit}&use_case={urllib.parse.quote(use_case)}",
            f"{base}/api/v1/recommend?limit={limit}&use_case={urllib.parse.quote(use_case)}",
            f"{base}/api/v1/models/top?limit={limit}",
        ]
        data = None
        for url in urls:
            try:
                data = get_json(url)
                break
            except Exception:
                continue
        if data is None:
            print(f"No data for {use_case}")
            continue
        models = normalize(data, use_case)
        name = f"auto-{use_case}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        cur = con.execute(
            "INSERT INTO benchmark_runs(name,source,use_case) VALUES(?,?,?)",
            (name, "collector", use_case),
        )
        run_id = cur.lastrowid
        _insert_models(con, run_id, models)
        con.commit()
        total += 1
        print(f"Collected {use_case}: {len(models)} models -> run {run_id}")
    con.close()
    print(f"Total runs inserted: {total}")


def _insert_models(con, run_id, models):
    """models listesini benchmark_models'e yazar (Sprint 7: tum sutunlar)."""
    for m in models:
        con.execute(
            """
            INSERT INTO benchmark_models(
                run_id,name,provider,use_case,fit_score,context_window,notes,
                required_vram_gb,required_ram_gb,
                context_length_supported,context_length_estimated_at,
                quantization,param_count_b,estimated_speed_tok_s,
                fit_level,is_moe,capabilities,disk_size_gb,llmfit_score,run_mode
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                m["name"],
                m["provider"],
                m["use_case"],
                m["fit_score"],
                m["context_window"],
                m["notes"],
                m["required_vram_gb"],
                m["required_ram_gb"],
                m["context_length_supported"],
                m["context_length_estimated_at"],
                m["quantization"],
                m["param_count_b"],
                m["estimated_speed_tok_s"],
                m["fit_level"],
                1 if m["is_moe"] else 0,
                m["capabilities"],
                m["disk_size_gb"],
                m["llmfit_score"],
                m["run_mode"],
            ),
        )


def _next_daily_run():
    """Bir sonraki günlük çalışmanın zamanını (02:00) hesaplar."""
    now = datetime.now()
    next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def run_loop(mode, base=API_BASE, source="auto", limit=LIMIT):
    """Süreklı toplama döngüsü. Ctrl+C (SIGINT) ile temiz kapanır.

    mode='daily': her gün 02:00'de çalışır (Windows Task Scheduler'ın
                  -Daily -At 2AM'i yerine uzun süreli process olarak çalışır).
    mode='interval': --interval-hours N verildiğinde her N saatte bir çalışır.
    """
    # SIGINT için temiz kapanış bayrağı
    stop = {"requested": False}

    def _handler(signum, frame):
        print("\n[SIGINT] Temiz kapanış istendi, bitiriliyor...")
        stop["requested"] = True

    signal.signal(signal.SIGINT, _handler)
    # Windows'ta SIGTERM yok ama yine de yakalayalım (Unix uyumu için)
    if hasattr(signal, "SIGTERM"):
        # Özgül exception'larla suppress (AGENTS.md Y3: genel suppress YASAK,
        # ama özgül (ValueError, OSError) güvenli)
        with contextlib.suppress(ValueError, OSError):
            signal.signal(signal.SIGTERM, _handler)

    print(f"[loop] Mod: {mode} | base: {base} | source: {source} | limit: {limit}")
    print("[loop] Durdurmak için Ctrl+C.")

    # İlk çalıştırma hemen
    print(f"\n[loop] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - İlk çalıştırma")
    try:
        collect(base, source=source, limit=limit)
    except Exception as e:
        print(f"[loop] Hata (devam edilecek): {e}")

    while not stop["requested"]:
        if mode == "daily":
            next_run = _next_daily_run()
            sleep_seconds = (next_run - datetime.now()).total_seconds()
            print(
                f"\n[loop] Sonraki çalıştırma: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({int(sleep_seconds)} saniye sonra)"
            )
        else:
            # interval mode
            sleep_seconds = 3600  # placeholder; --interval-hours ile değiştirilir
            print(f"\n[loop] Sonraki çalıştırma: {int(sleep_seconds)} saniye sonra")

        # Saatlerce uyumak yerine küçük adımlarla uyuyalım ki SIGINT hızlıca işlesin
        step = 30  # saniye
        slept = 0
        while slept < sleep_seconds and not stop["requested"]:
            time.sleep(min(step, sleep_seconds - slept))
            slept += step

        if stop["requested"]:
            break

        print(
            f"\n[loop] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Çalıştırılıyor..."
        )
        try:
            collect(base, source=source, limit=limit)
        except Exception as e:
            print(f"[loop] Hata (devam edilecek): {e}")

    print("[loop] Temiz şekilde kapatıldı.")


def main():
    """Sprint 6+7: argparse tabanli CLI."""
    parser = argparse.ArgumentParser(
        description="llmfit benchmark collector — top modelleri SQLite'e toplar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Ornekler:
  python benchmark_collector.py                  Tek seferlik toplama (varsayilan: llmfit CLI)
  python benchmark_collector.py --once           Ayini, acik secenek
  python benchmark_collector.py --source cli     Sadece llmfit CLI (llmfit fit --json)
  python benchmark_collector.py --source api     Sadece llmfit serve HTTP API
  python benchmark_collector.py --limit 200     200 model cek (varsayilan 50)
  python benchmark_collector.py --daily          Her gun 02:00'de (surekli process)
  python benchmark_collector.py --interval-hours 6   6 saatte bir (surekli process)
  python benchmark_collector.py --base http://192.168.1.5:8787   API base override

Windows Task Scheduler ile gunluk zamanlama (README'ye bakin):
  schtasks /create /tn "LLMFitCollector" /tr "python C:\\...\\benchmark_collector.py --once" \\
    /sc daily /st 02:00 /f
""",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Tek seferlik calistirma (varsayilan davranis).",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Surekli mod: her gun 02:00'de calisir (Ctrl+C ile durdur).",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        metavar="N",
        help="Surekli mod: her N saatte bir calisir (Ctrl+C ile durdur).",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "cli", "api"],
        default="auto",
        help="Veri kaynagi: auto (once CLI, olmazsa API), cli (sadece "
        "llmfit CLI), api (sadece llmfit serve). Varsayilan: auto.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=LIMIT,
        metavar="N",
        help=f"llmfit'ten cekilecek maksimum model sayisi (varsayilan: {LIMIT}).",
    )
    parser.add_argument(
        "--base",
        default=API_BASE,
        help=f"llmfit API base URL --source api icin (varsayilan: {API_BASE}).",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help="Inference backend: ollama, lmstudio, llamacpp, vllm (P1-5).",
    )
    args = parser.parse_args()

    # Çelişkili mod kontrolü
    modes = [args.once, args.daily, args.interval_hours is not None]
    if sum(bool(m) for m in modes) > 1:
        parser.error("--once, --daily, --interval-hours aynı anda kullanılamaz.")

    if args.daily:
        run_loop("daily", args.base, source=args.source, limit=args.limit)
    elif args.interval_hours is not None:
        if args.interval_hours <= 0:
            parser.error("--interval-hours pozitif olmalı.")
        # interval mode için sleep süresini override ederek run_loop'u çağır
        _run_interval_loop(
            args.interval_hours, args.base, source=args.source, limit=args.limit
        )
    else:
        # varsayılan: tek seferlik (--once verilse de verilmesse de)
        collect(args.base, source=args.source, limit=args.limit, backend=args.backend)


def _run_interval_loop(hours, base, source="auto", limit=LIMIT):
    """--interval-hours N için yardımcı. run_loop'u interval moduna uyarlar."""
    # run_loop fonksiyonunu monkey-patch ile uyarlama yerine, küçük bir wrapper:
    stop = {"requested": False}

    def _handler(signum, frame):
        print("\n[SIGINT] Temiz kapanış istendi...")
        stop["requested"] = True

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        with contextlib.suppress(ValueError, OSError):
            signal.signal(signal.SIGTERM, _handler)

    sleep_seconds = hours * 3600
    print(
        f"[loop] Mod: interval (her {hours} saatte bir) | base: {base}"
        f" | source: {source} | limit: {limit}"
    )
    print("[loop] Durdurmak için Ctrl+C.")

    print(f"\n[loop] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - İlk çalıştırma")
    try:
        collect(base, source=source, limit=limit)
    except Exception as e:
        print(f"[loop] Hata (devam edilecek): {e}")

    while not stop["requested"]:
        print(f"\n[loop] Sonraki çalıştırma: {int(sleep_seconds)} saniye sonra")
        step = 30
        slept = 0
        while slept < sleep_seconds and not stop["requested"]:
            time.sleep(min(step, sleep_seconds - slept))
            slept += step
        if stop["requested"]:
            break
        print(
            f"\n[loop] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Çalıştırılıyor..."
        )
        try:
            collect(base, source=source, limit=limit)
        except Exception as e:
            print(f"[loop] Hata (devam edilecek): {e}")

    print("[loop] Temiz şekilde kapatıldı.")


if __name__ == "__main__":
    main()
