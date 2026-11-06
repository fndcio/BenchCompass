"""api/routes/shared.py — Route modüllerinin ortak sabitleri ve yardımcıları.

Sprint 31 (Y7 modül bölme): `api/main.py`'deki (1567 satır) ortak sabitler ve
yardımcı fonksiyonlar buraya taşındı. Route modülleri buradan import eder;
`api/main.py` re-export ederek `from api.main import X` uyumluluğunu korur
(test monkeypatch hedefleri `api.routes.shared.X` olarak güncellendi).

Flat layout korunur (Y15): `api/` backend, `web/` statik frontend, kök collector.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.responses import JSONResponse

from .. import bench_data, fit_scores, benchcompass_proxy, ollama_client
from .. import db as dbmod
from ..catalog import use_case_key as _use_case_key  # T5: tek kaynak (AGENTS.md §1.6)
from ..compat import _tier_from_margins  # T4: tek kaynak (AGENTS.md §1.6)
from ..schemas import TierThresholds

BASE = Path(__file__).resolve().parent.parent.parent  # benchcompass/
DB = dbmod.DB
WEB_DIR = BASE / "web"  # Sprint 4 yeni shell
INDEX_HTML = WEB_DIR / "index.html"
CONFIG_DIR = BASE / "config"
HARDWARE_FILE = CONFIG_DIR / "hardware_profile.json"
# BenchCompass Benchmark Eval plugin raporları (plugin/benchcompass-benchmark-eval/...)
EVAL_REPORTS_DIR = (
    BASE
    / "plugin"
    / "benchcompass-benchmark-eval"
    / "benchcompass_benchmark_eval"
    / "reports"
)
PROVIDER_FILE = CONFIG_DIR / "provider.json"
MEDIA_KIT_DIR = BASE / "social-media-kit"


# --- Dashboard enrich yardımcıları (Sprint 20/21/23) ------------------------
# Not: `_use_case_key` artık api/catalog.py'den import edilir (T5 tek kaynak);
# eski yerel tanım kaldırıldı — aile skoru ile katalog filtresi aynı eşlemeyi
# paylaşır, anahtar setleri birbirinden sapamaz.


def _enrich_models_with_family_score(models: list[dict]) -> None:
    """Sprint 21 — modellere gerçek use_case aile skoru ekler.

    `family_score` (0-100) ve `family_use_case` set edilir. Aile eşleşmezse
    hiçbir alan eklenmez (mevcut fit_score davranışı korunur). Karar asistanı
    hibrit sıralama için bu alanı kullanır.
    """
    if not models:
        return
    fit = fit_scores.get_fit()
    if not fit.families:
        return
    for m in models:
        key = _use_case_key(m.get("useCase") or m.get("use_case") or "")
        if not key:
            continue
        score = fit.use_case_score(m.get("name") or "", key)
        if score is not None:
            m["family_score"] = score
            m["family_use_case"] = key


def _current_gpu_name() -> str:
    """Aktif donanım profilinden GPU adını döndürür (yoksa boş)."""
    try:
        if not HARDWARE_FILE.exists():
            return ""
        cfg = json.loads(HARDWARE_FILE.read_text(encoding="utf-8"))
        active = cfg.get("active_profile")
        profiles = cfg.get("profiles") or []
        for p in profiles:
            if p.get("id") == active:
                return p.get("gpu") or ""
        if profiles:
            return profiles[0].get("gpu") or ""
    except Exception:  # noqa: BLE001 — donanım profili okunamazsa boş
        return ""
    return ""


def _enrich_models_with_community_speed(models: list[dict]) -> None:
    """Sprint 20 — modellerin estimated_speed_tok_s'ini community verisiyle güçlendirir.

    Aktif donanımdaki gerçek ölçüm varsa `estimated_speed_tok_s` ve
    `speed_source='community'` set edilir; yoksa modeldeki mevcut tahmin KORUNUR.
    Tek lookup (N+1 yok — Y8).
    """
    gpu = _current_gpu_name()
    if not gpu or not models:
        return
    smap = bench_data.get_bench().speed_map_for_gpu(gpu)
    if not smap:
        return
    for m in models:
        name = (m.get("name") or "").lower()
        if not name:
            continue
        hit = None
        for key, speed in smap.items():
            if (
                key in name
                or name in key
                or name in (key.split("/")[-1] if "/" in key else "")
            ):
                hit = speed
                break
        if hit and not m.get("speed_source"):
            m["estimated_speed_tok_s"] = hit["measured_tps"]
            m["speed_source"] = "community"
            m["community_ttft_ms"] = hit.get("ttft_ms")


def _enrich_models_with_real_benchmark(con, models: list[dict]) -> None:
    """Sprint 23 / 32 — gerçek yerel ölçümler (real/benchkit/plugin-eval) öncelikli uygulanır.

    benchmarks tablosunda model adına kayıtlı ölçüm varsa
    `estimated_speed_tok_s` ve `speed_source='real'` set edilir. Community
    güçlendirmesinden ÖNCE çağrılır (gerçek ölçüm en güçlü kaynaktır). Tek batch
    fetch (N+1 yok — Y8).
    """
    if not models:
        return
    names = [m.get("name") for m in models if m.get("name")]
    if not names:
        return
    placeholders = ",".join("?" * len(names))
    rows = con.execute(
        f"SELECT model, measured_tps, ttft_ms FROM benchmarks "
        f"WHERE model IN ({placeholders}) "
        f"AND (source IS NULL OR source != 'community') "
        f"AND measured_tps IS NOT NULL ORDER BY id DESC",
        names,
    ).fetchall()
    seen = set()
    for row in rows:
        if row["model"] in seen:
            continue
        seen.add(row["model"])
        for m in models:
            if (m.get("name") or "") == row["model"]:
                m["estimated_speed_tok_s"] = row["measured_tps"]
                m["speed_source"] = "real"
                m["community_ttft_ms"] = row["ttft_ms"]
                break


# --- llmfit proxy yardımcıları ----------------------------------------------


def _llmfit_error_response(e: benchcompass_proxy.LlmfitError):
    """LlmfitError'yu FastAPI HTTPException'a cevirir (detayli hata + toast)."""

    return JSONResponse(
        status_code=503,
        content={
            "error": e.message,
            "stderr": e.stderr[:500] if e.stderr else "",
            "returncode": e.returncode,
            "command": " ".join(e.command) if e.command else "",
            "type": "llmfit_error",
        },
    )


# --- Background tasks yardımcısı --------------------------------------------


def _task_dict(t: dict | None) -> dict:
    if not t:
        return {"error": "task not found"}
    return {
        "uuid": t.get("uuid", ""),
        "status": t.get("status", "unknown"),
        "type": t.get("type"),
        "progress": t.get("progress", 0),
        "detail": t.get("detail"),
        "result": t.get("result"),
        "error": t.get("error"),
        "created_at": t.get("created_at"),
        "completed_at": t.get("completed_at"),
    }


# --- Benchmark yardımcıları --------------------------------------------------


def _real_benchmark(model: str, provider: str = "auto") -> dict | None:
    """Community verisinde donanım+model eşleşirse gerçek ölçümü döndürür."""
    gpu = _current_gpu_name()
    if not gpu:
        return None
    return bench_data.get_bench().get_speed_for_model(model, gpu_name=gpu)


def _mock_benchmark(model: str, provider: str = "auto", shared: bool = False) -> dict:
    """Benchmark: gerçek ölçüm (llmfit bench) → community → dürüst hata.

    Sprint 27 düzeltmesi: rastgele tahmin ÜRETMEZ (eski "1.5sn bekle + random
    sayı" mock davranışı kaldırıldı). Kaynak önceliği:
      1. real      — `llmfit bench` subprocess (bu makinede gerçek ölçüm)
      2. community — yerel benchmark_cache (başka donanımlarda ölçülmüş gerçek)
      3. hiçbiri   — RuntimeError fırlatır → task 'failed' → kullanıcıya dürüst
                     hata gösterilir; sahte veri DB'ye YAZILMAZ.
    """
    result = _run_ollama_bench(model, runs=1)
    if result is None:
        raise RuntimeError(
            "llmfit bench çalıştırılamadı ve bu model için community ölçümü "
            "bulunamadı. Dürüst sonuç: ölçüm yapılmadı. Gerçek yerel ölçüm için "
            "llmfit CLI kurun veya Benchmark Eval plugin'ini çalıştırın "
            "(plugin/benchcompass-benchmark-eval/run.cmd)."
        )
    _save_benchmark_record(model, provider, result)
    return {**result, "shared": 1 if shared else 0}


def _run_ollama_bench(model: str, runs: int = 1) -> dict | None:
    """Gerçek bench'i dener, başarısızsa community verisine düşer.

    Dönüş: normalize edilmiş sonuç dict (source dahil) veya None.
    """
    try:
        bench = benchcompass_proxy.llmfit_bench(model, provider="ollama", runs=runs)
        measured = bench.get("measured_tps")
        if measured is not None:
            return {
                "model": model,
                "provider": "ollama",
                "measured_tps": measured,
                "ttft_ms": bench.get("ttft_ms"),
                "ttft_method": bench.get("ttft_method", "measured"),
                "output_tokens": bench.get("total_tokens"),
                "total_ms": bench.get("total_ms"),
                "num_runs": runs,
                "source": "real",
            }
    except benchcompass_proxy.LlmfitError:
        pass  # community fallback'a düş

    community = _real_benchmark(model, "ollama")
    if community and community.get("measured_tps") is not None:
        return {
            "model": model,
            "provider": "ollama",
            "measured_tps": community["measured_tps"],
            "ttft_ms": community.get("ttft_ms"),
            "ttft_method": community.get("ttft_method", "measured"),
            "output_tokens": None,
            "total_ms": None,
            "num_runs": 1,
            "source": "community",
            "matched_gpu": community.get("matched_gpu"),
        }
    return None


def _save_benchmark_record(model: str, provider: str, result: dict) -> None:
    """Normalize edilmiş benchmark sonucunu DB'ye yazar (source ve kalibrasyon dahil)."""
    from ..calibration import compute_calibration_delta

    measured_tps = result.get("measured_tps")
    pred_tps = result.get("predicted_tps")
    if pred_tps is None:
        try:
            from ..bench_data import get_bench

            pred_tps = get_bench().get_reference_tps(model_name=model)
        except Exception:
            pred_tps = None

    delta_pct = result.get("prediction_delta_pct")
    if delta_pct is None and pred_tps is not None and measured_tps is not None:
        delta_pct = compute_calibration_delta(measured_tps, pred_tps)

    con = dbmod.connect()
    try:
        con.execute(
            "INSERT INTO benchmarks(model,provider,measured_tps,ttft_ms,"
            "total_tokens,wall_clock_s,shared,error,source,predicted_tps,prediction_delta_pct,"
            "itl_ms,ttft_method) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                model,
                provider,
                measured_tps,
                result.get("ttft_ms"),
                result.get("output_tokens") or result.get("total_tokens"),
                result.get("total_ms"),
                0,
                None,
                result.get("source"),
                pred_tps,
                delta_pct,
                result.get("itl_ms"),
                result.get("ttft_method"),
            ),
        )
        con.commit()
    finally:
        con.close()


# --- Download & Run yardımcıları ---------------------------------------------


def _mock_download(repo: str, quant: str = "Q4_K_M") -> dict:
    """Mock download: bağımsız UI testleri için indirme simülasyonu."""
    time.sleep(0.5)
    model_name = repo.rsplit("/", maxsplit=1)[-1]
    path = f"models/simulated/{repo.replace('/', '--')}-{quant}.gguf"
    size_gb = 4.0  # Sabit simülasyon boyutu (rastgele sahte veri yerine sabit)
    sha256 = f"mock_simulated_{model_name}_{quant}"
    # DB'ye yaz (açık mock etiketiyle)
    con = dbmod.connect()
    try:
        con.execute(
            "INSERT INTO downloaded_models(repo,model,quant,path,size_gb,sha256,installed)"
            " VALUES(?,?,?,?,?,?,?)",
            (f"[MOCK] {repo}", model_name, quant, path, size_gb, sha256, 1),
        )
        con.commit()
    finally:
        con.close()
    return {
        "repo": repo,
        "quant": quant,
        "path": path,
        "size_gb": size_gb,
        "sha256": sha256,
        "is_mock": True,
    }


def _mock_run(model: str, port: int = 8080) -> dict:
    """Mock run: server başlatma simülasyonu."""
    time.sleep(0.5)
    con = dbmod.connect()
    mock_pid = 99999
    try:
        con.execute(
            "INSERT INTO running_servers(pid,port,model,endpoint) VALUES(?,?,?,?)",
            (mock_pid, port, f"[MOCK] {model}", f"http://localhost:{port} (simulated)"),
        )
        con.commit()
    finally:
        con.close()
    return {
        "pid": mock_pid,
        "port": port,
        "endpoint": f"http://localhost:{port}",
        "is_mock": True,
    }


# --- Ollama models tier yardımcıları -----------------------------------------


def _parse_params_b(param_str: str) -> float:
    """Model parametre boyutunu GB olarak parse eder ('' → 0)."""
    try:
        return float(param_str.replace("B", "").strip())
    except (ValueError, AttributeError):
        return 0


def _quant_bytes_per_param(quant: str) -> float:
    """Quantization seviyesine gore param basina byte tahmini."""
    if "Q4_0" in quant:
        return 0.65
    if "Q8" in quant:
        return 1.1
    if "Q2" in quant:
        return 0.5
    if "Q3" in quant:
        return 0.55
    return 0.7


def _determine_run_mode(required_vram: float, hw_vram: float) -> str:
    """VRAM ihtiyacina gore calisma modunu belirler."""
    if required_vram > hw_vram:
        return "CPU_offload"
    if required_vram > hw_vram * 0.7:
        return "Mixed"
    return "GPU"


def _compute_tier_for_model(
    model: dict, hardware: dict, full_config: dict | None = None
) -> dict:
    """Bir model icin tier hesaplar (compat.compute_tier mantigi ile).

    Sprint 12: run_mode belirlenir; tier formülü TEK KAYNAK olan
    ``api/compat.py::_tier_from_margins``'ten alınır (T4 — Y17/DRY).
    """
    # Ollama modelinden vram/ram ihtiyacini tahmin et
    params_b = _parse_params_b(model.get("parameter_size") or "")
    bytes_per_param = _quant_bytes_per_param(model.get("quantization_level", ""))

    required_vram = round(params_b * bytes_per_param, 2)
    required_ram = round(required_vram * 1.15, 2)
    hw_vram = hardware.get("vram_gb", 12)
    hw_ram = hardware.get("ram_gb", 32)

    vram_margin = hw_vram - required_vram
    ram_margin = hw_ram - required_ram

    # Sprint 12: run_mode belirle (Ollama icin otomatik)
    run_mode = _determine_run_mode(required_vram, hw_vram)

    # Tier formülü tek kaynak: api/compat.py::_tier_from_margins
    thresholds_dict = (full_config or {}).get("tier_thresholds", {})
    thresholds = TierThresholds(**thresholds_dict)
    tier, tone = _tier_from_margins(vram_margin, ram_margin, run_mode, thresholds)

    return {
        "tier": tier,
        "tone": tone,
        "required_vram_gb": required_vram,
        "required_ram_gb": required_ram,
        "vram_margin_gb": round(vram_margin, 2),
        "ram_margin_gb": round(ram_margin, 2),
        "run_mode": run_mode,
    }


def _get_latest_benchmark(con, model_name: str) -> dict | None:
    """Bir model icin en son benchmark sonucunu getirir."""
    row = con.execute(
        "SELECT * FROM benchmarks WHERE model=? ORDER BY id DESC LIMIT 1",
        (model_name,),
    ).fetchone()
    if row:
        return {
            "measured_tps": row["measured_tps"],
            "ttft_ms": row["ttft_ms"],
            "source": row["source"],
            "created_at": row["created_at"],
        }
    # Ollama tag name ile de dene (qwen3:8b -> qwen3:8b)
    return None


def _find_benchcompass_match(con, model_name: str) -> dict | None:
    """Ollama model adi ile llmfit katalogunda eslesme ara.

    Ornegin 'qwen3:8b' -> llmfit'te 'Qwen/Qwen3-8B' gibi.
    Basit bir substring eslesmesi yapar.
    """
    # Ollama adindan parametreyi cikar: qwen3:8b -> 8b, deepseek-r1:14b -> 14b
    parts = model_name.split(":")
    param_hint = parts[1].lower() if len(parts) >= 2 else ""

    # Son run'daki modellerde eslestir
    latest = dbmod.fetch_latest(con)
    for m in latest.get("models", []):
        mn = (m.get("name") or "").lower()
        if param_hint and param_hint in mn:
            return {
                "name": m.get("name"),
                "fit_score": m.get("fitScore"),
                "fit_level": m.get("fit_level"),
                "estimated_tps": m.get("estimated_speed_tok_s"),
                "llmfit_score": m.get("llmfit_score"),
            }
    return None


# --- Provider yardımcıları ----------------------------------------------------


def _get_provider_config() -> dict:
    if PROVIDER_FILE.exists():
        data = json.loads(PROVIDER_FILE.read_text(encoding="utf-8"))
        if "active_provider" not in data:
            data["active_provider"] = data.get("provider", "auto")
        return data
    return {
        "active_provider": "auto",
        "provider": "auto",
        "ollama_host": "http://localhost:11434",
        "lmstudio_host": "http://localhost:1234",
        "llamacpp_host": "http://localhost:8080",
        "mlx_host": "http://localhost:8080",
    }


def _save_provider_config(cfg: dict):
    PROVIDER_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _run_all_benchmarks(models: list) -> dict:
    """Background task: tum modelleri benchmark et (Sprint 11)."""
    results = []
    for m in models:
        name = m["name"]
        try:
            result = ollama_client.run_benchmark(name, runs=1)
            _save_benchmark_record(
                result["model"],
                result["provider"],
                {
                    "measured_tps": result["measured_tps"],
                    "ttft_ms": result["ttft_ms"],
                    "output_tokens": result["output_tokens"],
                    "total_ms": result["total_ms"] / 1000,
                    "source": "real",
                },
            )
            results.append({"model": name, "ok": True, "tps": result["measured_tps"]})
        except Exception as e:
            results.append({"model": name, "ok": False, "error": str(e)})

    return {
        "results": results,
        "total": len(models),
        "success": sum(1 for r in results if r["ok"]),
    }
