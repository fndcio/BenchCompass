"""api/routes/ollama.py — Ollama + Benchmark + Task route'ları (Sprint 31 Y7).

`api/main.py`'den taşındı: ollama status/models/ps/run/stop/benchmark +
benchmark + download/run/running-servers/stop + tasks. Davranış birebir korunur.
Test uyumu: monkeypatch hedefleri `api.routes.shared.X`.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Body
from pydantic import BaseModel as PydBaseModel

from .. import db as dbmod
from .. import ollama_client
from .. import tasks as bg_tasks
from ..concurrent_bench import run_concurrent_stress
from . import shared

router = APIRouter()


# --- Background tasks endpoint'leri ---


@router.get("/api/tasks/{task_uuid}")
def get_task(task_uuid: str):
    """Task durumunu dondurur (frontend polling icin)."""
    t = bg_tasks.get_task(task_uuid)
    return shared._task_dict(t)


@router.get("/api/tasks")
def list_tasks(limit: int = 20):
    return {"tasks": bg_tasks.list_tasks(limit)}


# --- Benchmark ---


class BenchmarkRecord(PydBaseModel):
    id: int
    model: str
    provider: str | None = None
    measured_tps: float | None = None
    ttft_ms: float | None = None
    total_tokens: int | None = None
    wall_clock_s: float | None = None
    shared: int = 0
    error: str | None = None
    source: str | None = None
    created_at: str | None = None


@router.post("/api/benchmark")
def start_benchmark(
    model: str = Body("qwen3:8b"),
    provider: str = Body("auto"),
    share: bool = Body(False),
):
    """Benchmark baslatir (arka planda).

    Sprint 27 düzeltmesi: model/provider/share JSON body'den okunur — frontend
    `JSON.stringify({model, provider, share})` gönderir; query param okumak
    varsayılana (Qwen/Qwen2.5-Coder-7B — Ollama'da yok) düşürüp 404 üretiyordu.
    """
    task_uuid = bg_tasks.create_task(
        "benchmark",
        shared._mock_benchmark,
        model=model,
        provider=provider,
        shared=share,
    )
    return {"task_uuid": task_uuid, "status": "started"}


@router.get("/api/benchmarks")
def list_benchmarks(limit: int = 20):
    """Gecmis benchmark sonuclari."""
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT * FROM benchmarks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return {"benchmarks": [dict(r) for r in rows]}
    finally:
        con.close()


# --- Download & Run ---


@router.post("/api/download")
def start_download(repo: str, quant: str = "Q4_K_M"):
    """Model indirme baslatir (arka planda)."""
    task_uuid = bg_tasks.create_task(
        "download", shared._mock_download, repo=repo, quant=quant
    )
    return {"task_uuid": task_uuid, "status": "started"}


@router.post("/api/run")
def start_run(model: str, port: int = 8080):
    """Modeli calistirir (arka planda)."""
    # once indirilmis mi kontrol et
    con = dbmod.connect()
    try:
        row = con.execute(
            "SELECT * FROM downloaded_models WHERE model=? AND installed=1"
            " ORDER BY id DESC LIMIT 1",
            (model,),
        ).fetchone()
    finally:
        con.close()

    if not row:
        # Indirilmemis: once indir
        dl_task = bg_tasks.create_task("download", shared._mock_download, repo=model)
        bg_tasks._run_task(dl_task, lambda: None)  # hizlica indir

    task_uuid = bg_tasks.create_task(
        "run_model", shared._mock_run, model=model, port=port
    )
    return {"task_uuid": task_uuid, "status": "started"}


@router.get("/api/running-servers")
def list_running_servers():
    """Calisan modellerin listesi."""
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT * FROM running_servers WHERE stopped_at IS NULL ORDER BY id DESC"
        ).fetchall()
        return {"servers": [dict(r) for r in rows]}
    finally:
        con.close()


@router.post("/api/run/stop")
def stop_run(pid: int):
    """Calisan modeli durdurur (mock: sadece DB'de stopped_at gunceller)."""
    con = dbmod.connect()
    try:
        con.execute(
            "UPDATE running_servers SET stopped_at=CURRENT_TIMESTAMP WHERE pid=?",
            (pid,),
        )
        con.commit()
        return {"ok": True, "pid": pid}
    finally:
        con.close()


# --- Ollama yerel modeller ---


@router.get("/api/ollama/status")
def ollama_status():
    """Ollama servis durumunu kontrol eder (online/offline + installed_count)."""
    return ollama_client.check_status()


@router.get("/api/benchcompass/status")
def llmfit_status():
    """llmfit CLI yuklu mu kontrol eder."""
    return shared.benchcompass_proxy.check_llmfit_status()


@router.get("/api/ollama/models")
def ollama_models():
    """Ollama'daki tum yerel modelleri listeler (+ computeTier).

    Her model icin:
      - Ollama API verisi (name, size, quant, param, context)
      - computeTier (donanim profilimize gore)
      - llmfit katalogunda varsa: estimated_tps, fit_score, fit_level
      - Son benchmark sonucu varsa: measured_tps

    Karar: Tum modeller gosterilecek — kucuk/buyuk fark etmez.
    """
    try:
        models = ollama_client.list_models()
    except ollama_client.OllamaError as e:
        return {"ok": False, "error": e.message, "models": []}

    # Donanim profilini yukle
    hw_config = {}
    try:
        if shared.HARDWARE_FILE.exists():
            hw_config = json.loads(shared.HARDWARE_FILE.read_text(encoding="utf-8"))
            active_id = hw_config.get("active_profile", "")
            profiles = hw_config.get("profiles", [])
            active = next(
                (p for p in profiles if p.get("id") == active_id),
                profiles[0] if profiles else {},
            )
        else:
            active = {}
    except Exception:
        active = {}

    # Her model icin computeTier + benchmark + llmfit katalog eslesmesi
    con = dbmod.connect()
    for m in models:
        m["computeTier"] = shared._compute_tier_for_model(m, active, hw_config)
        m["benchmark"] = shared._get_latest_benchmark(con, m["name"])
        m["benchcompass_match"] = shared._find_benchcompass_match(con, m["name"])
    con.close()

    return {"ok": True, "models": models}


class ModelActionRequest(PydBaseModel):
    model: str = "qwen3:8b"


class ModelChatRequest(PydBaseModel):
    model: str = "qwen3:8b"
    prompt: str = "Merhaba, 1 cümleyle kendini tanıt."


@router.get("/api/ollama/ps")
def ollama_ps():
    """O anda calisan (VRAM/RAM bellegine yuklu) Ollama modellerini listeler."""
    try:
        return {"ok": True, "models": ollama_client.ps()}
    except ollama_client.OllamaError as e:
        return {"ok": False, "error": e.message, "models": []}


@router.post("/api/ollama/run")
def ollama_run(req: ModelActionRequest):
    """Ollama ile modeli bellege yukler ve serving moduna alir."""
    try:
        result = ollama_client.run_model(req.model)
        return {"ok": True, "model": req.model, "message": result.get("message", "")}
    except ollama_client.OllamaError as e:
        return {"ok": False, "error": e.message}


def _run_pull_task(model_name: str, task_uuid: str = "") -> dict:
    def _on_progress(p: dict) -> None:
        pct = p.get("pct")
        prog = int(pct) if pct is not None else 0
        detail = f"{p.get('status', '')}"
        if p.get("total", 0) > 0:
            comp_mb = round(p.get("completed", 0) / (1024**2), 1)
            tot_mb = round(p.get("total", 0) / (1024**2), 1)
            detail += f" ({comp_mb}MB / {tot_mb}MB)"
        bg_tasks.update_task(task_uuid, progress=prog, detail=detail)

    return ollama_client.pull_model(model_name, on_progress=_on_progress)


@router.post("/api/ollama/pull")
def ollama_pull(req: ModelActionRequest):
    """Ollama üzerinden arka planda model indirir."""
    task_uuid = bg_tasks.create_task(
        "ollama_pull",
        _run_pull_task,
        pass_task_uuid=True,
        model_name=req.model,
    )
    return {"ok": True, "task_uuid": task_uuid, "model": req.model}


@router.post("/api/ollama/stop")
def ollama_stop(req: ModelActionRequest):
    """Ollama modelini VRAM/RAM belleginden bosaltir (durdurur)."""
    try:
        result = ollama_client.stop_model(req.model)
        return {
            "ok": True,
            "model": req.model,
            "message": result.get("message", "Model durduruldu."),
        }
    except ollama_client.OllamaError as e:
        return {"ok": False, "error": e.message}


@router.post("/api/ollama/test-chat")
def ollama_test_chat(req: ModelChatRequest):
    """Modelin gercekten calistigini dogrulamak icin tek atimlik test cagrısı yapar."""
    try:
        result = ollama_client.generate_chat(req.model, req.prompt)
        return result
    except ollama_client.OllamaError as e:
        return {"ok": False, "error": e.message}


@router.post("/api/ollama/benchmark")
def ollama_benchmark(model: str = Body("qwen3:8b"), runs: int = Body(1)):
    """Gerçek llmfit bench ile yerel ölçüm yapar; yoksa community verisine düşer.

    Sprint 23: mock benchmark kaldırıldı. Kaynak önceliği:
      1. real      — `llmfit bench` subprocess (benchcompass_proxy.llmfit_bench)
      2. community — yerel community cache (bench_data)
      3. hiçbiri   — dürüst hata (ok:false) — tahmin üretilmez.
    Sonuç `source` alanıyla DB'ye yazılır.
    """
    result = shared._run_ollama_bench(model, runs)
    if result is None:
        return {
            "ok": False,
            "error": (
                "llmfit bench çalıştırılamadı ve bu model için community "
                "ölçümü bulunamadı. Dürüst sonuç: ölçüm yapılmadı."
            ),
        }
    shared._save_benchmark_record(model, "ollama", result)
    return {"ok": True, "result": result}


@router.post("/api/ollama/benchmark-all")
def ollama_benchmark_all():
    """Tum Ollama modellerini sirayla benchmark eder (arka planda).

    Karar: Background task olarak calisir, frontend polling yapar.
    Once kucuk modeller, sonra buyuk.
    """
    try:
        models = ollama_client.list_models()
    except ollama_client.OllamaError as e:
        return {"ok": False, "error": e.message}

    # Kucukten buyuge sirala
    models.sort(key=lambda m: m.get("size_gb", 0))

    task_uuid = bg_tasks.create_task(
        "benchmark_all", shared._run_all_benchmarks, models=models
    )
    return {"ok": True, "task_uuid": task_uuid, "total": len(models)}


@router.post("/api/benchmark/concurrent")
def concurrent_benchmark(
    model: str = Body("qwen3:8b"),
    backend: str = Body("lmstudio"),
    prompt: str = Body("Kısaca yerel yapay zeka avantajlarını 3 maddede yaz."),
    max_tokens: int = Body(80),
    levels: list[int] = Body([1, 2, 4, 8]),
):
    """Eşzamanlılık stresi (Adım 4): N paralel SSE isteği, p50/p95/p99 + kuyruk etkisi.

    OpenAI-uyumlu backend'ler için (lmstudio/llamacpp/vllm). Ollama backend'i
    llmfit tekil ölçüm kullanır — dürüst hata döner (sahte paralel üretim yok).
    Sonuçlar `concurrency_benchmarks` tablosuna yazılır (§9.3 onayı A).
    """
    from ..openai_client import get_backend_url

    if backend == "ollama":
        return {
            "ok": False,
            "error": "Eşzamanlılık stresi yalnız OpenAI-uyumlu backend'de (lmstudio/llamacpp/vllm).",
        }
    base_url, btype = get_backend_url(backend)
    if btype != "openai":
        return {"ok": False, "error": f"Desteklenmeyen backend türü: {btype}"}
    clean_levels = sorted({min(8, max(1, int(level))) for level in levels}) or [1]
    try:
        results = run_concurrent_stress(
            model=model,
            base_url=base_url,
            prompt=prompt,
            max_tokens=max_tokens,
            levels=clean_levels,
        )
    except Exception as exc:  # noqa: BLE001 — dürüst hata döner, 500 yerine ok:false
        return {"ok": False, "error": str(exc)}
    con = dbmod.connect()
    try:
        con.executemany(
            "INSERT INTO concurrency_benchmarks(model, backend, concurrency,"
            " latency_p50_ms, latency_p95_ms, latency_p99_ms, ttft_p50_ms,"
            " ttft_p95_ms, throughput_tps, queue_effect_pct, success, errors)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    model,
                    backend,
                    r["concurrency"],
                    r["latency_p50_ms"],
                    r["latency_p95_ms"],
                    r["latency_p99_ms"],
                    r["ttft_p50_ms"],
                    r["ttft_p95_ms"],
                    r["throughput_tps"],
                    r["queue_effect_pct"],
                    r["success"],
                    r["errors"],
                )
                for r in results
            ],
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "model": model, "backend": backend, "results": results}


@router.get("/api/benchmark/concurrent")
def concurrent_benchmark_history(limit: int = 20):
    """Geçmiş eşzamanlılık stres kayıtları."""
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT * FROM concurrency_benchmarks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return {"ok": True, "results": [dict(r) for r in rows]}
    finally:
        con.close()
