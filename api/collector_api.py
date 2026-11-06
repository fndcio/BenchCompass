"""FastAPI collector kontrol serveri (port 8790).

Mevcut collector_api.py davranisini birebilir korur:
    GET  /health                 -> {ok, db, runs}
    GET  /api/dashboard/history  -> {history} (sadece run metadata)
    GET  /api/dashboard/summary  -> {source:'collector-api', history, latest:{models:[]}}
    POST /api/collector/run      -> benchmark_collector.py'yi subprocess olarak calistirir

Calistirma:
    uvicorn api.collector_api:app --port 8790 --host 0.0.0.0
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db as dbmod

BASE = Path(__file__).resolve().parent.parent  # benchcompass/
DB = dbmod.DB
COLLECTOR = BASE / "benchmark_collector.py"

app = FastAPI(
    title="BenchCompass Collector Control",
    description="benchmark_collector.py'yi uzaktan tetiklemek icin kontrol API.",
    version="3.0.0",
)

# CORS: dashboard (8788) buraya cross-origin istek atar — yalnızca yerel
# origin'lere izin verilir. LAN'dan erişim gerekiyorsa origin listeye eklenir.
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


def _count_runs() -> int:
    con = dbmod.connect()
    try:
        return con.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
    finally:
        con.close()


def _recent_runs(limit: int = 50):
    """Sadece benchmark_runs satirlarini dondurur (modeller DEGIL).

    Bu, mevcut collector_api davranisini birebir korur — dashboard UI
    bu endpoint'i 'latest runs' listesi icin kullanir, model detayi yok.
    """
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT id,name,source,use_case,created_at FROM benchmark_runs "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


class CollectorRunResult(BaseModel):
    ok: bool
    stdout: str
    stderr: str
    runs: int


@app.get("/health")
def health():
    return {"ok": True, "db": str(DB), "runs": _count_runs()}


@app.get("/api/dashboard/history")
def dashboard_history():
    return {"history": _recent_runs(50)}


@app.get("/api/dashboard/summary")
def dashboard_summary():
    # Mevcut davranisi koru: latest.models bilerek bos (dashboard ana API'den cekiyor)
    return {
        "source": "collector-api",
        "history": _recent_runs(50),
        "latest": {"models": []},
    }


@app.post("/api/collector/run", response_model=CollectorRunResult)
def collector_run():
    """benchmark_collector.py'yi subprocess olarak calistirir.

    Sprint 6'da --daily / --interval-hours desteklendiginde buraya opsiyonel
    arguman eklenebilir.
    """
    # Timeout: istek süresiz askıda kalmasın (collector --once tek tur atar;
    # 600 sn, llmfit cache güncellemesi dahil yeterli üst sınırdır).
    try:
        proc = subprocess.run(
            ["python", str(COLLECTOR)],
            capture_output=True,
            text=True,
            cwd=str(BASE),
            timeout=600,
        )
    except subprocess.TimeoutExpired as e:
        return CollectorRunResult(
            ok=False,
            stdout=str(e.stdout or ""),
            stderr=f"collector timeout (600 sn): {e.cmd}",
            runs=_count_runs(),
        )
    return CollectorRunResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        runs=_count_runs(),
    )


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8790, log_level="info")


if __name__ == "__main__":
    main()
