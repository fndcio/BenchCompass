"""llmfit CLI proxy katmani.

Sprint 8 ile gelen bu modul, llmfit alt komutlarini guvenli sekilde FastAPI
endpoint'lerine acar. Her fonksiyon:
  - llmfit binary varligini kontrol eder (yoksa LlmfitError firlatir)
  - subprocess.run ile belirli timeout degeriyle cagirir
  - stdout'u JSON parse eder (bozuksa LlmfitError)
  - stderr detayini error mesajina ekler (detayli hata + toast ilkesi)
  - cache'li (info/plan/diff 5dk, system 60sn, hf-search 10dk)

Kullanici kararlari (Sprint 8 giris):
  - Hata: Detayli hata + toast (stderr log + UI bildirimi)
  - Cache: 5 dk cache (info/plan/diff), 60 sn (system), 10 dk (hf-search)

Sprint 9'da bench/download/run gibi uzun isler async background task olarak
eklenecek (bu moduldeki wrapper'lar extend edilecek).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

# llmfit bench normalizasyonu tek kaynak: api/bench_output.py (Sprint 43 DRY).
# Alt çizgili isim, bu modülün iç çağrıları için takma addır.
from .bench_output import normalize_bench_output as _normalize_bench_output


class LlmfitError(Exception):
    """llmfit cagrisi sirasinda hata. UI'da toast ile gosterilecek.

    Attributes:
        message: Kullaniciya gosterilecek kisa mesaj
        stderr: llmfit'in stderr ciktisi (debug icin)
        returncode: subprocess exit code
        command: calistirilan komut (list)
    """

    def __init__(
        self, message: str, stderr: str = "", returncode: int = -1, command=None
    ):
        super().__init__(message)
        self.message = message
        self.stderr = stderr
        self.returncode = returncode
        self.command = command

    def to_dict(self) -> dict:
        return {
            "error": self.message,
            "stderr": self.stderr[:500] if self.stderr else "",
            "returncode": self.returncode,
            "command": " ".join(self.command) if self.command else "",
        }


def find_llmfit() -> str | None:
    """llmfit binary yolunu dondurur. Yoksa None."""
    return shutil.which("llmfit")


# --- Cache altyapisi --------------------------------------------------------
# Basit dict bazli TTL cache. asyncio/task gerektirmez; sync fonksiyonlarla
# calisir. Cache key = fonksiyon adi + argumanlarin tuple'i.

_CACHE: dict = {}  # key -> (expires_at, value)
DEFAULT_TTL = {
    "info": 300,  # 5 dk
    "plan": 300,  # 5 dk
    "diff": 300,  # 5 dk
    "system": 60,  # 60 sn
    "recommend": 300,  # 5 dk
    "hf_search": 600,  # 10 dk
}


def _cache_get(key: str):
    entry = _CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.time() > expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any, ttl: int):
    _CACHE[key] = (time.time() + ttl, value)


def cache_clear(pattern: str = ""):
    """Cache'i temizler. pattern bossa hepsini, verilirse o kelimeyi
    iceren key'leri siler."""
    if not pattern:
        _CACHE.clear()
        return
    keys_to_delete = [k for k in _CACHE if pattern in k]
    for k in keys_to_delete:
        _CACHE.pop(k, None)


# --- Ortak subprocess cagirici ---------------------------------------------


def _run_llmfit(args: list, timeout: int = 60, stdin_data: str | None = None) -> dict:
    """llmfit binary'sini verilen argumanlarla cagirir, JSON parse eder.

    Hata olursa LlmfitError firlatir (kullanici tercihi: detayli hata).
    """
    binary = find_llmfit()
    if not binary:
        raise LlmfitError(
            "llmfit bulunamadı. PATH'te olduğundan emin olun "
            "(scoop install llmfit veya cargo install llmfit).",
            command=[binary or "llmfit"] + args,
        )

    cmd = [binary] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL if stdin_data is None else subprocess.PIPE,
            input=stdin_data,
        )
    except subprocess.TimeoutExpired:
        raise LlmfitError(
            f"llmfit komutu {timeout} sn içinde yanıt vermedi (timeout).",
            stderr=f"Timeout after {timeout}s",
            returncode=-2,
            command=cmd,
        ) from None
    except OSError as e:
        raise LlmfitError(
            f"llmfit başlatılamadı: {e}",
            stderr=str(e),
            command=cmd,
        ) from e

    if proc.returncode != 0:
        # llmfit error mesajini stderr'dan cikar
        stderr_tail = (proc.stderr or "").strip().split("\n")[-3:]
        short_msg = "; ".join(line.strip() for line in stderr_tail if line.strip())
        if not short_msg:
            short_msg = f"llmfit exit code {proc.returncode}"
        raise LlmfitError(
            f"llmfit hatası: {short_msg}",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            command=cmd,
        )

    stdout = proc.stdout or ""
    stdout_stripped = stdout.strip()
    if not stdout_stripped:
        raise LlmfitError(
            "llmfit boş çıktı döndürdü.",
            stderr=proc.stderr or "",
            command=cmd,
        )

    try:
        return json.loads(stdout_stripped)
    except json.JSONDecodeError as e:
        return _parse_json_with_prefix(stdout_stripped, e, stdout, cmd)


def _parse_json_with_prefix(stdout_stripped: str, err, stdout: str, cmd: list) -> dict:
    """llmfit bazen 'Searching HuggingFace...' gibi bilgi mesajlari basar
    JSON onunde. Ilk '{' veya '[' karakterini bulup oradan parse edelim."""
    for i, ch in enumerate(stdout_stripped):
        if ch in "{[":
            try:
                return json.loads(stdout_stripped[i:])
            except json.JSONDecodeError:
                break
    raise LlmfitError(
        f"llmfit çıktısı JSON değil: {err}",
        stderr=stdout[:500],
        command=cmd,
    ) from err


# --- Public API (Sprint 8) --------------------------------------------------


def llmfit_info(model_name: str, use_cache: bool = True) -> dict:
    """llmfit info <model> --json

    Tek model icin en zengin detay: score_components (fit/quality/speed/context),
    verify_command, gguf_sources, estimate_basis, capabilities, alternative_quants.
    """
    cache_key = f"info:{model_name}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    # Model adinda quote/special char varsa guvenli hale getir
    safe_name = model_name.strip()
    data = _run_llmfit(["info", safe_name, "--json"], timeout=30)
    if use_cache:
        _cache_set(cache_key, data, DEFAULT_TTL["info"])
    return data


def llmfit_plan(
    model_name: str,
    context: int,
    memory_gb: float | None = None,
    vram_gb: float | None = None,
    quant: str | None = None,
    target_tps: float | None = None,
    use_cache: bool = True,
) -> dict:
    """llmfit plan <model> --context N [--memory Xg --vram Yg --quant Q] --json

    Donanim/upgrade senaryosu: 'bu modeli X context ile calistirmak icin
    hangi donanim gerek?' Cevap: minimum/recommended VRAM/RAM, run_paths
    (gpu/cpu_offload/cpu_only), estimated_tps, upgrade_deltas.

    memory_gb/vram_gb verilirse llmfit'in algiladigi degerleri override eder
    (global --memory/--vram flag'i ile).
    """
    cache_key = (
        f"plan:{model_name}:{context}:{memory_gb}:{vram_gb}:{quant}:{target_tps}"
    )
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    # Global flag'ler (memory/vram) komuttan ONCE gelmeli
    global_args = []
    if memory_gb is not None:
        global_args.extend(["--memory", f"{memory_gb}g"])
    if vram_gb is not None:
        global_args.extend(["--vram", f"{vram_gb}g"])

    cmd_args = ["plan", model_name.strip(), "--context", str(int(context))]
    if quant:
        cmd_args.extend(["--quant", quant])
    if target_tps is not None:
        cmd_args.extend(["--target-tps", str(target_tps)])
    cmd_args.append("--json")

    data = _run_llmfit(global_args + cmd_args, timeout=30)
    if use_cache:
        _cache_set(cache_key, data, DEFAULT_TTL["plan"])
    return data


def llmfit_diff(
    model_a: str | None = None,
    model_b: str | None = None,
    top_n: int = 2,
    use_cache: bool = True,
) -> dict:
    """llmfit diff [a] [b] --json veya llmfit diff --json -n N (auto top N)

    Iki modeli (veya top N modeli) yan yana karsilastirir. Cikti:
    {system: {...}, models: [{model: {...tum spec'ler...}, fit_level, score, ...}, ...]}

    Frontend'de 'models' array'i yan yana tablo olarak gosterilir.
    """
    cache_key = f"diff:{model_a}:{model_b}:{top_n}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    args = ["diff", "--json"]
    if model_a and model_b:
        args.extend([model_a.strip(), model_b.strip()])
    else:
        args.extend(["-n", str(top_n)])

    data = _run_llmfit(args, timeout=30)
    if use_cache:
        _cache_set(cache_key, data, DEFAULT_TTL["diff"])
    return data


def llmfit_system(use_cache: bool = True) -> dict:
    """llmfit system --json

    Donanim tespiti: GPU, VRAM, RAM, CPU, backend. Output: {system: {...}}.
    Ayarlar sekmesindeki 'Otomatik tespit' butonu icin kullanilir.
    """
    cache_key = "system:current"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    data = _run_llmfit(["system", "--json"], timeout=20)
    if use_cache:
        _cache_set(cache_key, data, DEFAULT_TTL["system"])
    return data


def llmfit_recommend(
    use_case: str = "general",
    limit: int = 10,
    min_fit: str | None = None,
    tool_use: bool = False,
    use_cache: bool = True,
) -> dict:
    """llmfit recommend --use-case <X> [--min-fit L --tool-use] -n N --json

    Use-case'e gore yogunlastirilmis tavsiye. llmfit'in 6 use-case degeri:
    general, coding (code), reasoning (reason), chat, multimodal, embedding.

    min_fit degerleri: all, runnable, perfect, good, marginal.
    """
    cache_key = f"recommend:{use_case}:{limit}:{min_fit}:{tool_use}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    args = ["recommend", "--use-case", use_case, "-n", str(limit), "--json"]
    if min_fit:
        args.extend(["--min-fit", min_fit])
    if tool_use:
        args.append("--tool-use")

    data = _run_llmfit(args, timeout=30)
    if use_cache:
        _cache_set(cache_key, data, DEFAULT_TTL["recommend"])
    return data


def llmfit_bench(
    model: str,
    provider: str = "auto",
    runs: int = 1,
    use_cache: bool = False,
    timeout: int = 120,
) -> dict:
    """llmfit bench <model> [--provider P] [--runs N] --json — gerçek yerel ölçüm.

    Sprint 23: mock benchmark yerine kullanıcının donanımında gerçek tok/s ölçer.
    Çıktı formatı sürümler arası değişebilir; dönen dict esnek normalize edilir.

    Cache: kapalı (gerçek ölçüm her seferinde taze olmalı). Arzu edilirse
    caller `use_cache=True` ile kısa TTL cache isteyebilir.
    """
    cache_key = f"bench:{model}:{provider}:{runs}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    args = ["bench", model]
    if provider and provider != "auto":
        args.extend(["--provider", provider])
    if runs and runs > 1:
        args.extend(["--runs", str(runs)])
    args.append("--json")

    data = _run_llmfit(args, timeout=timeout)
    normalized = _normalize_bench_output(data)
    if use_cache:
        _cache_set(cache_key, normalized, DEFAULT_TTL["info"])
    return normalized


def llmfit_hf_search(
    query: str,
    limit: int = 20,
    use_cache: bool = True,
) -> dict:
    """llmfit hf-search <query> -n N --json (Sprint 9)

    HuggingFace'te GGUF model arama. Output: {models: [{repo_id, quant,
    size_gb, downloads, likes, compatible}]} veya hata durumunda {models: []}.
    """
    cache_key = f"hf_search:{query}:{limit}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    args = ["hf-search", query, "-n", str(limit), "--json"]
    data = _run_llmfit(args, timeout=60)
    # hf-search bazen {models: []} doner (eslesme yoksa)
    if not isinstance(data, dict):
        data = {"models": [], "raw": data}
    if use_cache:
        _cache_set(cache_key, data, DEFAULT_TTL["hf_search"])
    return data


def normalize_system_info(system_data: dict) -> dict:
    """llmfit system JSON'unu bizim hardware_profile.json semamiza cevirir.

    Output format HardwareProfileEntry ile uyumlu:
      device_name, cpu, gpu, vram_gb, ram_gb, npu_tops, storage_gb, os, cuda_version
    """
    sys_block = system_data.get("system", system_data)
    return {
        "device_name": _detect_device_name(sys_block),
        "cpu": sys_block.get("cpu_name") or "",
        "gpu": sys_block.get("gpu_name") or "",
        "vram_gb": round(
            sys_block.get("gpu_vram_gb") or sys_block.get("total_gpu_vram_gb") or 0, 2
        ),
        "ram_gb": round(sys_block.get("total_ram_gb") or 0, 2),
        "npu_tops": None,  # llmfit NPU raporlamiyor
        "storage_gb": None,
        "os": _detect_os(),
        "cuda_version": None,
    }


def _detect_device_name(sys_block: dict) -> str:
    """Cihaz adini tahmin et (CPU+GPU bilgisinden)."""
    cpu = (sys_block.get("cpu_name") or "").strip()
    gpu = (sys_block.get("gpu_name") or "").strip()
    if cpu and gpu:
        return f"{cpu} + {gpu}"
    return cpu or gpu or "Algılanan donanım"


def _detect_os() -> str:
    import platform

    return f"{platform.system()} {platform.release()}"


# --- Yeni llmfit komutlari (Sprint 12+) -------------------------------------


def llmfit_doctor(use_cache: bool = True) -> str:
    """llmfit doctor — hardware detection report (duz metin)."""
    cache_key = "doctor:current"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    binary = find_llmfit()
    if not binary:
        raise LlmfitError("llmfit bulunamadi.", command=["llmfit", "doctor"])
    cmd = [binary, "doctor"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise LlmfitError("llmfit doctor timeout", returncode=-2, command=cmd) from None
    except OSError as e:
        raise LlmfitError(f"llmfit baslatilamadi: {e}", command=cmd) from e
    if proc.returncode != 0:
        raise LlmfitError(
            "llmfit doctor basarisiz",
            stderr=proc.stderr,
            returncode=proc.returncode,
            command=cmd,
        )
    report = proc.stdout or "Bos rapor"
    if use_cache:
        _cache_set(cache_key, report, DEFAULT_TTL["system"])
    return report


def llmfit_fit(refresh: bool = False) -> dict:
    """llmfit fit --json — tum modellerin fit siralamasi."""
    cache_key = "fit:all"
    if not refresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    data = _run_llmfit(["fit", "--json"], timeout=60)
    if not refresh:
        _cache_set(cache_key, data, DEFAULT_TTL["info"])
    return data


def check_llmfit_status() -> dict:
    """llmfit CLI durumunu kontrol eder."""
    binary = find_llmfit()
    if binary:
        return {
            "ok": True,
            "installed": True,
            "path": binary,
        }
    return {
        "ok": True,
        "installed": False,
        "path": None,
        "message": (
            "llmfit CLI bulunamadı. Lütfen PATH'te olduğundan emin olun "
            "(scoop install llmfit veya cargo install llmfit)."
        ),
    }
