"""FastAPI dashboard server (port 8788).

Sprint 3 ile dashboard_server.py (stdlib http.server) buraya tasanmistir.
Sprint 31 (Y7) ile 45 route anlamli modullere bolundu:
    api/routes/dashboard.py   — summary/history/snapshot/delete + grafik + export
    api/routes/catalog.py     — catalog search/summary + hf-search
    api/routes/ollama.py      — ollama + benchmark + download/run + tasks
    api/routes/hardware.py    — hardware GET/PUT + autodetect + provider + migrate
    api/routes/benchcompass.py — benchcompass proxy + fit/baseline + cache
Bu dosya sadece app olusturur, router'lari include eder ve yardimci sabitleri
re-export eder (test uyumu icin `from api.main import X` calisir).

Calistirma:
    uvicorn api.main:app --port 8788 --host 0.0.0.0
ya
    python -m uvicorn api.main:app --port 8788 --host 0.0.0.0
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import db as dbmod
from .routes.catalog import router as catalog_router
from .routes.control_center import router as control_center_router
from .routes.dashboard import router as dashboard_router
from .routes.eval import router as eval_router
from .routes.hardware import router as hardware_router
from .routes.benchcompass import router as benchcompass_router
from .routes.ollama import router as ollama_router
from .routes.discovery import router as discovery_router
from .routes.arena import router as arena_router
from .routes.asr import router as asr_router
from .routes.matrix import router as matrix_router
from .routes.telemetry import router as telemetry_router
from .routes.shared import (  # noqa: F401 — bilinçli re-export (test uyumu)
    BASE,
    CONFIG_DIR,
    DB,
    EVAL_REPORTS_DIR,
    HARDWARE_FILE,
    INDEX_HTML,
    MEDIA_KIT_DIR,
    PROVIDER_FILE,
    WEB_DIR,
)

# Modül referansları (test monkeypatch uyumu: `api.main.bench_data.get_bench` vb.)
from . import bench_data, catalog, fit_scores, benchcompass_proxy, ollama_client  # noqa: F401
from . import tasks as bg_tasks  # noqa: F401

# Re-export (test uyumu: `from api.main import _enrich_models_with_community_speed` vb.)
from .routes.shared import (  # noqa: E402,F401 — bilinçli re-export
    _compute_tier_for_model,
    _current_gpu_name,
    _enrich_models_with_community_speed,
    _enrich_models_with_family_score,
    _enrich_models_with_real_benchmark,
    _find_benchcompass_match,
    _get_latest_benchmark,
    _llmfit_error_response,
    _mock_benchmark,
    _mock_download,
    _mock_run,
    _real_benchmark,
    _run_all_benchmarks,
    _run_ollama_bench,
    _save_benchmark_record,
    _task_dict,
    _use_case_key,
)

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Sunucu açılırken migrasyon + backfill + orphan task kurtarma çalışır."""
    logger = logging.getLogger("llmfit.dashboard")
    try:
        con = dbmod.connect()
        dbmod.backfill_from_notes(con)
        con.close()
        logger.info("DB hazır: %s", DB)
    except Exception as e:
        logger.error("DB hatası: %s", e)
    # Orphan task kurtarma (denetim kapanışı): daemon task thread'leri restart'ta
    # ölür; DB'de pending/running kalan satırlar gerçekte ölüdür. Failed işaretlenmezse
    # frontend sonsuza kadar pending poll eder.
    try:
        reaped = bg_tasks.reap_orphan_tasks()
        if reaped:
            logger.warning(
                "Orphan task kurtarma: %s adet pending/running görev failed işaretlendi",
                reaped,
            )
    except Exception as e:
        logger.error("Orphan task kurtarma hatası: %s", e)
    yield


app = FastAPI(
    title="BenchCompass",
    description="Yerel LLM uyumluluk dashboard'u — donanım profiline göre model tier hesaplar.",
    version="0.26.9",
    lifespan=lifespan,
)

# CORS: yalnızca yerel origin'lere izin (local-first). Dashboard web/ statik
# dosyası aynı origin'den servis edilir; collector API (8790) buradan çağrılır.
# LAN'dan erişim gerekiyorsa ilgili origin listeye eklenir.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8788",
        "http://127.0.0.1:8788",
        "http://localhost:8790",
        "http://127.0.0.1:8790",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Sayfa -------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index():
    """Sprint 4: Yeni Alpine.js shell'ini serve eder.

    index.html icindeki asset linkleri /web/ prefix'i kullanir (styles.css ->
    /web/styles.css), bu yüzden StaticFiles mount'u asagida /web altinda yapildi.
    """
    if INDEX_HTML.exists():
        content = INDEX_HTML.read_text(encoding="utf-8")
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    raise HTTPException(404, "Dashboard HTML bulunamadi (web/index.html yok)")


# Statik asset'ler /web/ altinda serve edilir.
# Cache-busting icin no-cache header'i eklenir.
class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp


app.mount("/web", NoCacheStaticFiles(directory=str(WEB_DIR), html=False), name="web")

# LLMFit Benchmark Eval interaktif raporu (plugin) — /eval-reports/ -> index.html
if EVAL_REPORTS_DIR.exists():
    app.mount(
        "/eval-reports",
        NoCacheStaticFiles(directory=str(EVAL_REPORTS_DIR), html=True),
        name="eval-reports",
    )

# BenchCompass Social Media Kit & Interaktif Laboratuvar Portalı
if MEDIA_KIT_DIR.exists():
    app.mount(
        "/social-media-kit",
        NoCacheStaticFiles(directory=str(MEDIA_KIT_DIR), html=True),
        name="social-media-kit",
    )


@app.get("/api/eval/report-status")
def eval_report_status():
    """LLMFit Benchmark Eval raporu üretilmiş mi? (C1 — [ RAPOR ] boş durum).

    Rapor üretilmediyse frontend iframe yerine "--pipeline çalıştır" mesajı
    gösterir; 404/boş iframe yerine anlamlı bilgi verir.
    """
    index = EVAL_REPORTS_DIR / "index.html"
    if not index.exists():
        return {"exists": False, "updated_at": None, "path": str(index)}

    return {
        "exists": True,
        "updated_at": datetime.fromtimestamp(index.stat().st_mtime).isoformat(),
        "path": str(index),
    }


# --- Saglik ------------------------------------------------------------------


@app.get("/health")
def health():
    return {"ok": True, "db": str(DB)}


# --- Route modulleri (Sprint 31 Y7) ------------------------------------------


app.include_router(control_center_router)
app.include_router(dashboard_router)
app.include_router(catalog_router)
app.include_router(eval_router)
app.include_router(ollama_router)
app.include_router(hardware_router)
app.include_router(benchcompass_router)
app.include_router(telemetry_router)
app.include_router(matrix_router)
app.include_router(discovery_router)
app.include_router(arena_router)
app.include_router(asr_router)


# --- Re-export (test uyumu: `from api.main import _enrich_models_with_community_speed`) ---


def main() -> None:
    """python -m api.main olarak dogrudan calistirma destegi."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8788, log_level="info")


if __name__ == "__main__":
    main()
