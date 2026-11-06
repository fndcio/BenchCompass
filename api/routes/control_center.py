"""api/routes/control_center.py — Control Center agregasyon endpoint'leri (Sprint 53).

Mevcut sistemlerin üstünde bir agregasyon katmanıdır — yeni veri deposu
OLUŞTURMAZ, mevcut endpoint'leri / DB tablolarını / runtime kontrollerini
tek bir yanıtta birleştirir. Her endpoint READ-ONLY'dir.

Endpoint'ler:
    GET /api/cc/status       — Sistem + servis + DB durumu
    GET /api/cc/flags        — Bayrak/uyarı agregasyonu
    GET /api/cc/versions     — Versiyon tutarlılık kontrolü
    GET /api/cc/recent       — Son aktiviteler
    GET /api/cc/diagnostics  — Sistem tanılama
    GET /api/cc/docs         — Doküman listesi + durum
    GET /api/cc/db-info      — Veritabanı bilgisi
"""

from __future__ import annotations

import json
import platform
import sqlite3
import subprocess
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import db as dbmod
from .shared import BASE, DB, HARDWARE_FILE

router = APIRouter()


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _check_service_online(
    port: int, probe_path: str = "/health", timeout: float = 1.0
) -> bool:
    """HTTP probe — baglanti basariliysa True."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{probe_path}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status in (200, 204, 301, 302)
    except Exception:  # noqa: BLE001
        return False


def _cmd_version(cmd: list[str], timeout: int = 3) -> str | None:
    """Subprocess ile versiyon string'i döndürür."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout.strip().split("\n")[0] if r.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def _get_services_status() -> tuple[dict[str, Any], int, int]:
    """Servis erişim durumu ve sayıları."""
    services = {
        "dashboard": {"port": 8788, "online": True, "name": "Dashboard API"},
        "collector": {
            "port": 8790,
            "online": _check_service_online(8790, "/health"),
            "name": "Collector API",
        },
        "ollama": {
            "port": 11434,
            "online": _check_service_online(11434, "/api/tags")
            or _check_service_online(11434, "/"),
            "name": "Ollama",
        },
    }
    online = sum(1 for s in services.values() if s["online"])
    return services, online, len(services)


def _get_db_status() -> dict[str, Any]:
    """DB kayıt ve son run bilgisi."""
    try:
        con = dbmod.connect()
        bm = con.execute("SELECT COUNT(*) FROM benchmarks").fetchone()[0]
        models = con.execute("SELECT COUNT(*) FROM benchmark_models").fetchone()[0]
        runs = con.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
        last_row = con.execute(
            "SELECT created_at FROM benchmark_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last = last_row[0] if last_row else None
        con.close()
        return {
            "ok": True,
            "path": str(DB),
            "benchmarks": bm,
            "models": models,
            "runs": runs,
            "last_run": last,
        }
    except Exception:  # noqa: BLE001
        return {
            "ok": False,
            "path": str(DB),
            "benchmarks": 0,
            "models": 0,
            "runs": 0,
            "last_run": None,
        }


def _get_active_hw_profile() -> dict[str, Any]:
    """Aktif donanım profili."""
    hw: dict[str, Any] = {}
    try:
        if HARDWARE_FILE.exists():
            cfg = json.loads(HARDWARE_FILE.read_text(encoding="utf-8"))
            active = cfg.get("active_profile")
            for p in cfg.get("profiles") or []:
                if p.get("id") == active:
                    return p
            if cfg.get("profiles"):
                return cfg["profiles"][0]
    except Exception:  # noqa: BLE001
        pass
    return hw


def _get_app_version() -> str:
    """pyproject.toml'dan uygulama versiyonu."""
    pyproject = BASE / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "unknown"


# ---------------------------------------------------------------------------
# GET /api/cc/status
# ---------------------------------------------------------------------------


@router.get("/api/cc/status")
def cc_status() -> dict[str, Any]:
    """Sistem durumu agregasyonu — servisler, DB, donanım."""
    services, online_count, total_count = _get_services_status()
    db_info = _get_db_status()
    hw = _get_active_hw_profile()
    version = _get_app_version()

    git_branch = _cmd_version(["git", "branch", "--show-current"])
    git_commit = _cmd_version(["git", "rev-parse", "--short", "HEAD"])

    health = "HEALTHY"
    if not db_info["ok"] or online_count < total_count:
        health = "DEGRADED"

    return {
        "health": health,
        "version": version,
        "git_branch": git_branch,
        "git_commit": git_commit,
        "timestamp": datetime.now().isoformat(),
        "services": services,
        "services_online": online_count,
        "services_total": total_count,
        "database": db_info,
        "hardware": {
            "gpu": hw.get("gpu", "Unknown"),
            "vram_gb": hw.get("vram_gb", 0),
            "cpu": hw.get("cpu", "Unknown"),
            "ram_gb": hw.get("ram_gb", 0),
            "os": hw.get("os", platform.system()),
        },
    }


def _collect_service_flags() -> list[dict[str, Any]]:
    """Servis erişim kontrolleri."""
    flags = []
    service_probes = [
        ("Collector", 8790, "/health"),
        ("Ollama", 11434, "/api/tags"),
    ]
    for name, port, probe in service_probes:
        if not _check_service_online(port, probe):
            flags.append(
                {
                    "severity": "HIGH",
                    "category": "SYSTEM",
                    "title": f"{name} Offline",
                    "description": f"{name} servisi port {port}'da yanıt vermiyor.",
                    "action": f"{name} servisini başlatın.",
                }
            )
    return flags


def _collect_db_flags() -> list[dict[str, Any]]:
    """DB durumu ve veri eskiliği kontrolleri."""
    flags = []
    try:
        con = dbmod.connect()
        total = con.execute("SELECT COUNT(*) FROM benchmarks").fetchone()[0]
        if total == 0:
            flags.append(
                {
                    "severity": "MEDIUM",
                    "category": "DATA",
                    "title": "Benchmark Verisi Yok",
                    "description": "benchmarks tablosu boş — henüz gerçek ölçüm yapılmamış.",
                    "action": "Bir benchmark çalıştırın.",
                }
            )
        last = con.execute(
            "SELECT created_at FROM benchmarks ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last and last[0]:
            try:
                age_h = (
                    datetime.now()
                    - datetime.fromisoformat(last[0].replace("Z", "+00:00"))
                ).total_seconds() / 3600
                if age_h > 168:
                    flags.append(
                        {
                            "severity": "LOW",
                            "category": "DATA",
                            "title": "Eski Benchmark Verisi",
                            "description": f"Son benchmark {age_h:.0f} saat önce çalışmış.",
                            "action": "Güncel veriler için yeni benchmark çalıştırın.",
                        }
                    )
            except Exception:  # noqa: BLE001
                pass
        con.close()
    except Exception:  # noqa: BLE001
        flags.append(
            {
                "severity": "CRITICAL",
                "category": "SYSTEM",
                "title": "Veritabanı Erişim Hatası",
                "description": "benchmark_history.db'ye bağlanılamıyor.",
                "action": "DB dosyasının varlığını ve izinlerini kontrol edin.",
            }
        )
    return flags


def _collect_version_flags() -> list[dict[str, Any]]:
    """Versiyon tutarlılık kontrolleri."""
    flags = []
    pyproject_ver, pkg_ver = None, None
    try:
        pyproject = BASE / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("version"):
                    pyproject_ver = line.split("=")[1].strip().strip('"').strip("'")
                    break
        pkg = BASE / "package.json"
        if pkg.exists():
            pkg_ver = json.loads(pkg.read_text(encoding="utf-8")).get("version")
    except Exception:  # noqa: BLE001
        pass
    if pyproject_ver and pkg_ver and pyproject_ver != pkg_ver:
        flags.append(
            {
                "severity": "HIGH",
                "category": "VERSION",
                "title": "Versiyon Uyumsuzluğu",
                "description": f"pyproject.toml={pyproject_ver}, package.json={pkg_ver}",
                "action": "Versiyonları senkronize edin.",
            }
        )
    return flags


def _collect_gpu_flags() -> list[dict[str, Any]]:
    """GPU sürücü erişim kontrolleri."""
    flags = []
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode != 0:
            flags.append(
                {
                    "severity": "HIGH",
                    "category": "SYSTEM",
                    "title": "GPU Sürücüsü Erişilemiyor",
                    "description": "nvidia-smi çalışamıyor.",
                    "action": "NVIDIA sürücüsünü kontrol edin.",
                }
            )
    except FileNotFoundError:
        flags.append(
            {
                "severity": "MEDIUM",
                "category": "SYSTEM",
                "title": "nvidia-smi Bulunamadı",
                "description": "GPU telemetri kullanılamaz.",
                "action": "NVIDIA sürücülerini yükleyin.",
            }
        )
    except Exception:  # noqa: BLE001
        pass
    return flags


# ---------------------------------------------------------------------------
# GET /api/cc/flags
# ---------------------------------------------------------------------------


@router.get("/api/cc/flags")
def cc_flags() -> dict[str, Any]:
    """Bayrak/uyarı agregasyonu — çapraz sistem kontrolü."""
    flags: list[dict[str, Any]] = []
    flags.extend(_collect_service_flags())
    flags.extend(_collect_db_flags())
    flags.extend(_collect_version_flags())
    flags.extend(_collect_gpu_flags())

    # Önem sıralama
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    flags.sort(key=lambda f: sev_order.get(f["severity"], 5))

    counts = {
        "critical": sum(1 for f in flags if f["severity"] == "CRITICAL"),
        "high": sum(1 for f in flags if f["severity"] == "HIGH"),
        "medium": sum(1 for f in flags if f["severity"] == "MEDIUM"),
        "low": sum(1 for f in flags if f["severity"] == "LOW"),
    }

    return {"flags": flags, "counts": counts, "total": len(flags)}


# ---------------------------------------------------------------------------
# GET /api/cc/versions
# ---------------------------------------------------------------------------


@router.get("/api/cc/versions")
def cc_versions() -> dict[str, Any]:
    """Versiyon tutarlılık kontrolü."""
    versions: dict[str, dict[str, Any]] = {}

    # pyproject.toml
    pyproject = BASE / "pyproject.toml"
    py_ver = None
    if pyproject.exists():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                py_ver = line.split("=")[1].strip().strip('"').strip("'")
                break
    versions["application"] = {
        "version": py_ver,
        "source": "pyproject.toml",
        "status": "OK",
    }

    # package.json
    pkg = BASE / "package.json"
    pkg_ver = None
    if pkg.exists():
        try:
            pkg_ver = json.loads(pkg.read_text(encoding="utf-8")).get("version")
        except Exception:  # noqa: BLE001
            pass
    match = py_ver == pkg_ver if py_ver and pkg_ver else False
    versions["frontend"] = {
        "version": pkg_ver,
        "source": "package.json",
        "status": "OK" if match else "CONFLICT",
    }

    # Git
    versions["git"] = {
        "branch": _cmd_version(["git", "branch", "--show-current"]),
        "commit": _cmd_version(["git", "rev-parse", "--short", "HEAD"]),
        "status": "OK",
    }

    consistent = all(v.get("status") == "OK" for v in versions.values())

    return {
        "versions": versions,
        "consistent": consistent,
        "authoritative_version": py_ver,
    }


# ---------------------------------------------------------------------------
# GET /api/cc/recent
# ---------------------------------------------------------------------------


@router.get("/api/cc/recent")
def cc_recent(limit: int = 20) -> dict[str, Any]:
    """Son aktiviteler — benchmark çalıştırmaları ve ölçümler."""
    events: list[dict[str, Any]] = []
    try:
        con = dbmod.connect()
        # Son benchmark ölçümleri
        for row in con.execute(
            "SELECT model, measured_tps, ttft_ms, created_at, source "
            "FROM benchmarks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall():
            events.append(
                {
                    "type": "benchmark_completed",
                    "time": row["created_at"],
                    "description": f"{row['model']} — {row['measured_tps']:.1f} tok/s"
                    if row["measured_tps"]
                    else f"{row['model']} — ölçüm yok",
                    "source": row["source"] or "unknown",
                }
            )
        # Son benchmark run'ları
        for row in con.execute(
            "SELECT name, source, created_at FROM benchmark_runs "
            "ORDER BY id DESC LIMIT ?",
            (min(limit, 5),),
        ).fetchall():
            events.append(
                {
                    "type": "run_completed",
                    "time": row["created_at"],
                    "description": f"Run: {row['name']}",
                    "source": row["source"] or "unknown",
                }
            )
        con.close()
    except Exception:  # noqa: BLE001
        pass

    # Zaman sırası
    events.sort(key=lambda e: e.get("time") or "", reverse=True)
    return {"events": events[:limit]}


# ---------------------------------------------------------------------------
# GET /api/cc/diagnostics
# ---------------------------------------------------------------------------


@router.get("/api/cc/diagnostics")
def cc_diagnostics() -> dict[str, Any]:
    """Sistem tanılama — runtime bilgileri ve bağımlılık kontrolü."""
    diag: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "node": _cmd_version(["node", "--version"]),
        "npm": _cmd_version(["npm", "--version"]),
        "git": _cmd_version(["git", "--version"]),
    }

    # GPU
    driver = None
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=driver_version,name",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(",")
            driver = parts[0].strip() if parts else None
            diag["gpu_name"] = parts[1].strip() if len(parts) > 1 else None
    except Exception:  # noqa: BLE001
        pass
    diag["gpu_driver"] = driver

    # CUDA
    cuda = _cmd_version(["nvcc", "--version"])
    if cuda:
        # "release X.Y" dizisini bul
        for part in cuda.split(","):
            if "release" in part.lower():
                cuda = part.strip()
                break
    diag["cuda"] = cuda

    # Ollama
    diag["ollama"] = _cmd_version(["ollama", "--version"])

    # DB
    diag["database"] = {
        "path": str(DB),
        "exists": DB.exists(),
        "size_mb": round(DB.stat().st_size / (1024 * 1024), 2) if DB.exists() else 0,
        "sqlite_version": sqlite3.sqlite_version,
    }

    return diag


# ---------------------------------------------------------------------------
# GET /api/cc/docs
# ---------------------------------------------------------------------------


@router.get("/api/cc/docs")
def cc_docs() -> dict[str, Any]:
    """Doküman listesi — docs/ dizini + kök dokümanlar."""
    docs_list: list[dict[str, Any]] = []

    # Kök dokümanlar
    for name in [
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "AGENTS.md",
        "11_BACKLOG.md",
        "12_ROADMAP.md",
        "ROADMAP_MASTER.md",
    ]:
        path = BASE / name
        if path.exists():
            docs_list.append(
                {
                    "name": name,
                    "path": name,
                    "size_kb": round(path.stat().st_size / 1024, 1),
                    "last_modified": datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat(),
                }
            )

    # docs/ altı
    docs_dir = BASE / "docs"
    if docs_dir.exists():
        for f in sorted(docs_dir.rglob("*.md")):
            rel = str(f.relative_to(BASE)).replace("\\", "/")
            docs_list.append(
                {
                    "name": f.name,
                    "path": rel,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "last_modified": datetime.fromtimestamp(
                        f.stat().st_mtime
                    ).isoformat(),
                }
            )

    return {"documents": docs_list, "total": len(docs_list)}


# ---------------------------------------------------------------------------
# GET /api/cc/db-info
# ---------------------------------------------------------------------------


@router.get("/api/cc/db-info")
def cc_db_info() -> dict[str, Any]:
    """Veritabanı bilgisi — boyut, tablo sayıları, son kayıtlar."""
    info: dict[str, Any] = {
        "path": str(DB),
        "exists": DB.exists(),
        "size_mb": round(DB.stat().st_size / (1024 * 1024), 2) if DB.exists() else 0,
        # Şema kararlılığı: DB yokken bile `tables` anahtarı her zaman var —
        # tüketici (Kontrol Merkezi UI + test) varlığa göre alan seti değişmez.
        "tables": {},
    }

    if not DB.exists():
        return info

    try:
        con = dbmod.connect()
        tables: dict[str, int] = {}
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall():
            tbl = row[0]
            cnt = con.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]  # noqa: S608
            tables[tbl] = cnt
        info["tables"] = tables
        info["sqlite_version"] = sqlite3.sqlite_version

        # Son benchmark kaydı
        last_bm = con.execute(
            "SELECT model, measured_tps, created_at "
            "FROM benchmarks ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last_bm:
            info["latest_benchmark"] = {
                "model": last_bm["model"],
                "measured_tps": last_bm["measured_tps"],
                "created_at": last_bm["created_at"],
            }

        # İntegrity check
        integrity = con.execute("PRAGMA integrity_check").fetchone()
        info["integrity"] = integrity[0] if integrity else "unknown"

        con.close()
    except Exception as e:  # noqa: BLE001
        info["error"] = str(e)

    return info


# ---------------------------------------------------------------------------
# Başlatıcı Operasyon Köprüsü (ADR-0012, Sprint 53 / Portal Konsolidasyonu)
# ---------------------------------------------------------------------------

LAUNCHERS_DIR = BASE / "launchers"


@router.get("/api/control/launchers")
def list_launchers() -> dict[str, Any]:
    """launchers/ altındaki hazır scriptleri listeler."""
    items = []
    if LAUNCHERS_DIR.exists():
        for f in sorted(LAUNCHERS_DIR.iterdir()):
            if f.suffix.lower() in (".bat", ".cmd", ".ps1") and not f.name.startswith(
                "."
            ):
                items.append(
                    {
                        "name": f.name,
                        "type": f.suffix.lower()[1:],
                        "size_bytes": f.stat().st_size,
                    }
                )
    return {"launchers": items, "total": len(items)}


@router.post("/api/control/launch")
def launch_script(name: str) -> dict[str, Any]:
    """Whitelist altındaki bir başlatıcı scriptini arka planda tetikler."""
    import re

    if not re.match(r"^[a-zA-Z0-9_\-]+\.(bat|cmd|ps1)$", name):
        raise HTTPException(status_code=400, detail="Geçersiz script adı formatı.")

    target = (LAUNCHERS_DIR / name).resolve()
    # Güvenlik kontrolü: launchers dizini dışına çıkamaz
    if not str(target).startswith(str(LAUNCHERS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Yol erişim kısıtı ihlali.")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Başlatıcı bulunamadı: {name}")

    try:
        if target.suffix.lower() == ".ps1":
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(target),
            ]
        else:
            cmd = ["cmd.exe", "/c", str(target)]

        subprocess.Popen(
            cmd,
            cwd=str(BASE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"ok": True, "message": f"{name} başlatıldı.", "script": name}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Başlatma hatası: {exc}")
