"""Ollama REST API istemcisi (Sprint 10).

Ollama API (port 11434) uzerinden yerel modelleri listeler, calistirir,
durdurur. Ayrica daha once olculmus benchmark sonuclarini dondurur.

Kullanici karari: Tum kararlari ben veriyorum.
  - Provider: Ollama (localhost:11434)
  - Tum modeller gosterilecek (kucuk/buyuk fark etmez)
  - "Modellerim" ayri bir sekme olacak
"""

from __future__ import annotations

from collections.abc import Callable
import json
import subprocess
import urllib.error
import urllib.request

# llmfit bench normalizasyonu tek kaynak: api/bench_output.py (Sprint 43 DRY).
from .bench_output import normalize_bench_output

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_TIMEOUT = 10


class OllamaError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.message = message
        self.stderr = stderr


# --- Dogrudan REST API cagrilari ---


def _api_get(path: str, timeout: int = OLLAMA_TIMEOUT) -> dict:
    """Ollama REST API'sine GET istegi."""
    url = f"{OLLAMA_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise OllamaError(f"Ollama API'ye erisilemiyor ({url}): {e}") from e
    except json.JSONDecodeError as e:
        raise OllamaError(f"Ollama JSON yaniti bozuk: {e}") from e


def _api_post(path: str, data: dict, timeout: int = OLLAMA_TIMEOUT) -> dict:
    """Ollama REST API'sine POST istegi."""
    url = f"{OLLAMA_BASE}{path}"
    body = json.dumps(data).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise OllamaError(f"Ollama POST hatasi ({url}): {e}") from e


# --- Public API fonksiyonlari ---


def list_models() -> list[dict]:
    """Ollama'daki tum modelleri listeler. GET /api/tags.

    Donus: liste of dict:
      name, size_gb, parameter_size, quantization_level,
      context_length, family, modified_at, digest
    """
    data = _api_get("/api/tags")
    models = data.get("models", [])
    result = []
    for m in models:
        det = m.get("details", {})
        result.append(
            {
                "name": m.get("name", "?"),
                "size_gb": round(m.get("size", 0) / (1024**3), 2),
                "parameter_size": det.get("parameter_size"),
                "quantization_level": det.get("quantization_level"),
                "context_length": det.get("context_length"),
                "family": det.get("family"),
                "modified_at": m.get("modified_at"),
                "digest": m.get("digest"),
                "provider": "ollama",
            }
        )
    return result


def ps() -> list[dict]:
    """O anda calisan modelleri listeler. GET /api/ps."""
    try:
        data = _api_get("/api/ps")
        return data.get("models", [])
    except OllamaError:
        return []


def show_model(model_name: str) -> dict:
    """Model detayini getirir. POST /api/show."""
    return _api_post("/api/show", {"model": model_name}, timeout=15)


def run_model(model_name: str) -> dict:
    """Ollama ile modeli calistirir ve VRAM/RAM bellegine yukler.

    Oncelik 1: Ollama REST API POST /api/generate ile keep_alive='15m' (hizli ve guvenilir).
    Oncelik 2: subprocess ile `ollama run <model>`.
    """
    # 1. REST API denemesi
    try:
        data = _api_post(
            "/api/generate",
            {"model": model_name, "prompt": "", "keep_alive": "15m"},
            timeout=30,
        )
        return {
            "ok": True,
            "model": model_name,
            "message": "Model VRAM belleğe başarıyla yüklendi (Serving modunda aktif).",
            "details": data,
        }
    except Exception:  # noqa: BLE001
        pass

    # 2. CLI fallback
    try:
        subprocess.run(
            ["ollama", "run", model_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        return {"ok": True, "model": model_name, "message": "ollama run baslatildi"}
    except subprocess.TimeoutExpired:
        return {
            "ok": True,
            "model": model_name,
            "message": "ollama run arkaplanda calisiyor",
        }
    except FileNotFoundError:
        raise OllamaError("ollama CLI bulunamadi") from None


def stop_model(model_name: str) -> dict:
    """Ollama modelini durdurur ve VRAM belleginden bosaltir.

    Oncelik 1: Ollama REST API POST /api/generate ile keep_alive=0 (aninda bosaltir).
    Oncelik 2: subprocess `ollama stop <model>`.
    """
    # 1. REST API denemesi (keep_alive: 0 modeli anında unload eder)
    try:
        _api_post(
            "/api/generate",
            {"model": model_name, "prompt": "", "keep_alive": 0},
            timeout=10,
        )
        return {
            "ok": True,
            "model": model_name,
            "message": "Model bellekten bosaltildi",
        }
    except Exception:  # noqa: BLE001
        pass

    # 2. CLI fallback
    try:
        proc = subprocess.run(
            ["ollama", "stop", model_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if proc.returncode == 0:
            return {"ok": True, "model": model_name, "message": "Model durduruldu"}
        raise OllamaError(f"ollama stop basarisiz: {proc.stderr}")
    except FileNotFoundError:
        raise OllamaError("ollama CLI bulunamadi") from None


def generate_chat(
    model_name: str, prompt: str = "Merhaba, 1 cümleyle kendini tanıt."
) -> dict:
    """Modelin gercekten calistigini dogrulamak icin hizli test inference cagrısı yapar."""
    try:
        data = _api_post(
            "/api/generate",
            {"model": model_name, "prompt": prompt, "stream": False},
            timeout=30,
        )
        return {
            "ok": True,
            "model": model_name,
            "response": data.get("response", ""),
            "total_duration_ms": round(data.get("total_duration", 0) / 1e6, 1),
            "eval_count": data.get("eval_count", 0),
            "eval_duration_ms": round(data.get("eval_duration", 0) / 1e6, 1),
        }
    except Exception as e:
        raise OllamaError(f"Inference hatası: {e}") from e


# --- Benchmark entegrasyonu (Sprint 11) ---


def run_benchmark(model_name: str, provider: str = "ollama", runs: int = 1) -> dict:
    """llmfit bench ile gercek olcum yapar.

    Donus: {measured_tps, ttft_ms, output_tokens, total_ms, model, provider}
    """
    import shutil

    binary = shutil.which("llmfit")
    if not binary:
        raise OllamaError("llmfit CLI bulunamadi")

    cmd = [
        binary,
        "bench",
        model_name,
        "--provider",
        provider,
        "--json",
        "--runs",
        str(runs),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode != 0:
            raise OllamaError(f"llmfit bench basarisiz: {proc.stderr[:300]}")

        # JSON baslangicini bul (llmfit bazen extra text basar)
        raw = proc.stdout
        idx = raw.find("{")
        if idx < 0:
            raise OllamaError("llmfit JSON ciktisi bulunamadi")
        data = json.loads(raw[idx:])

        norm = normalize_bench_output(data)
        if norm["measured_tps"] is None:
            raise OllamaError(f"Beklenmeyen bench formati: {json.dumps(data)[:200]}")
        return {
            "measured_tps": round(norm["measured_tps"], 2),
            "ttft_ms": round(norm["ttft_ms"] or 0, 2),
            "output_tokens": int(norm["total_tokens"] or 0),
            "total_ms": round(norm["total_ms"] or 0, 2),
            "num_runs": norm["num_runs"] or runs,
            "model": model_name,
            "provider": provider,
        }
    except subprocess.TimeoutExpired:
        raise OllamaError("llmfit bench timeout (60 sn)") from None
    except json.JSONDecodeError as e:
        raise OllamaError(f"llmfit JSON parse hatasi: {e}") from e


def pull_model(
    model_name: str,
    on_progress: Callable[[dict], None] | None = None,
    timeout: int = 1800,
) -> dict:
    """Ollama API üzerinden model indirir (POST /api/pull stream=true).

    Args:
        model_name: İndirilecek model adı (örn. 'qwen2.5:0.5b')
        on_progress: İlerleme callback fonksiyonu (status, completed, total, pct)
        timeout: Maksimum indirme süresi saniye cinsinden (varsayılan 1800 sn)

    Returns:
        {"ok": True, "model": model_name, "status": "success"}
    """
    url = f"{OLLAMA_BASE}/api/pull"
    body = json.dumps({"model": model_name, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    last_status = "started"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            for line in response:
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    chunk = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                if "error" in chunk:
                    raise OllamaError(f"Ollama pull hatası: {chunk['error']}")

                last_status = chunk.get("status", last_status)
                completed = chunk.get("completed", 0)
                total = chunk.get("total", 0)
                pct = round((completed / total) * 100, 1) if total > 0 else None

                if on_progress:
                    on_progress(
                        {
                            "status": last_status,
                            "completed": completed,
                            "total": total,
                            "pct": pct,
                        }
                    )
        return {"ok": True, "model": model_name, "status": "success"}
    except urllib.error.URLError as e:
        raise OllamaError(f"Ollama pull API erişim hatası ({url}): {e}") from e
    except TimeoutError:
        raise OllamaError(f"Ollama pull zaman aşımı ({timeout}s)") from None


def check_status() -> dict:
    """Ollama servis durumunu kontrol eder."""
    try:
        models = list_models()
        return {
            "ok": True,
            "status": "online",
            "installed_count": len(models),
            "host": OLLAMA_BASE,
        }
    except OllamaError as e:
        return {
            "ok": False,
            "status": "offline",
            "installed_count": 0,
            "error": str(e),
            "host": OLLAMA_BASE,
        }
