"""api/openai_client.py — OpenAI-Uyumlu Backend İstemcisi (P1-5).

LM Studio, llama.cpp server, vLLM-local gibi `/v1/chat/completions` API'si
sunan yerel çıkarım sunucularından çıktı üretimi ve benchmark ölçümü sağlar.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "backends.json"


def load_backends_config() -> dict[str, Any]:
    """config/backends.json dosyasını yükler."""
    if not CONFIG_PATH.is_file():
        return {
            "default": "ollama",
            "backends": {
                "ollama": {"url": "http://localhost:11434", "type": "ollama"},
                "lmstudio": {"url": "http://localhost:1234", "type": "openai"},
                "llamacpp": {"url": "http://localhost:8080", "type": "openai"},
                "vllm": {"url": "http://localhost:8000", "type": "openai"},
            },
        }
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_backend_url(backend_name: str | None = None) -> tuple[str, str]:
    """Seçili backend için (url, type) ikilisini döner.

    Öncelik: Parametre -> BENCHCOMPASS_BACKEND env -> config default.
    """
    config = load_backends_config()
    target = (
        backend_name
        or os.environ.get("BENCHCOMPASS_BACKEND")
        or config.get("default", "ollama")
    )
    backends = config.get("backends", {})
    if target in backends:
        b_info = backends[target]
        return b_info.get("url", "http://localhost:1234"), b_info.get("type", "openai")
    return "http://localhost:1234", "openai"


def _median(values: list[float]) -> float:
    """Medyan (p50) — boş listede 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _parse_sse_chunk(line: str) -> dict[str, Any] | None:
    """Tek SSE satırını çözer. ``data: [DONE]``/boş satır → None, geçersiz JSON → None."""
    stripped = line.strip()
    if not stripped or not stripped.startswith("data:"):
        return None
    payload = stripped[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def openai_generate(
    prompt: str,
    model: str,
    base_url: str = "http://localhost:1234",
    max_tokens: int = 120,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """OpenAI uyumlu /v1/chat/completions — önce SSE streaming dener, olmazsa fallback.

    Streaming: `stream=True` + `client.stream()`; ilk içerik chunk'ı = TTFT,
    chunk-arası delta = ITL (p50), decode tok/s = (n_tokens-1)/(t_last-t_first)
    (prefill hariç). Başarısızlıkta non-streaming POST'a düşer
    (`ttft_method="estimated"`, Y24: sahte ölçüm ezici gösterilmez).
    """
    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"

    # --- 1. Streaming denemesi -------------------------------------------------
    try:
        return _openai_generate_streaming(prompt, model, endpoint, max_tokens, timeout)
    except Exception as exc:
        logger.warning("SSE streaming başarısız, non-streaming'e düşülüyor: %s", exc)

    # --- 2. Non-streaming fallback ---------------------------------------------
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
    }

    t0 = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        r = client.post(endpoint, json=payload)
        r.raise_for_status()
        t_total = time.perf_counter() - t0
        data = r.json()

    choices = data.get("choices", [])
    content = choices[0]["message"]["content"] if choices else ""
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)

    # Yaklaşık token hesabı (eğer server token dönmezse kelime bazlı)
    if not completion_tokens:
        completion_tokens = max(1, int(len(content.split()) * 1.3))

    tps = (
        round(completion_tokens / max(0.001, t_total), 1) if completion_tokens else 0.0
    )
    # TTFT şeffaflık (denetim T2): streaming yokken gerçek ilk-token zamanı
    # bilinmez; %20 tahmini Y24-tipinde "sahte ölçüm" riski taşır. Değer
    # üstte hesaplanır ama yöntem açıkça "estimated" işaretlenir; arayüz ve
    # paylaşıp kartı bu bayrağı "tahmini" rozetiyle gösterir (F2 dürüstlüğü).
    ttft_ms = max(1.0, round(t_total * 200, 1))
    ttft_method = "estimated"

    return {
        "response": content,
        "tps": tps,
        "ttft_ms": ttft_ms,
        "ttft_method": ttft_method,
        "itl_ms": None,
        "output_tokens": completion_tokens,
        "total_duration_s": round(t_total, 2),
    }


def _decode_tps(
    completion_tokens: int,
    chunk_times: list[float],
    t_first: float,
    t_last: float,
    t_total: float,
) -> float:
    """Decode tok/s (prefill hariç) — tek chunk'ta genel hıza düşer."""
    if len(chunk_times) > 1 and completion_tokens > 1:
        return round((completion_tokens - 1) / max(0.001, t_last - t_first), 1)
    if completion_tokens:
        return round(completion_tokens / max(0.001, t_total), 1)
    return 0.0


def _openai_generate_streaming(
    prompt: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    """SSE streaming ölçümü (başarısızlıkta ValueError fırlatır → fallback)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
    }
    content_parts: list[str] = []
    chunk_times: list[float] = []  # perf_counter, yalnız içerik chunk'ları
    completion_tokens = 0

    t0 = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", endpoint, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                data = _parse_sse_chunk(str(line))
                if data is None:
                    continue
                usage = data.get("usage") or {}
                if usage.get("completion_tokens"):
                    completion_tokens = int(usage["completion_tokens"])
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = str(delta.get("content") or "")
                if not piece:
                    continue
                content_parts.append(piece)
                chunk_times.append(time.perf_counter())
    t_total = time.perf_counter() - t0

    if not content_parts or len(chunk_times) == 0:
        raise ValueError("streaming yanıtında içerik alınamadı")

    content = "".join(content_parts)
    if not completion_tokens:
        completion_tokens = max(1, int(len(content.split()) * 1.3))

    t_first = chunk_times[0]
    t_last = chunk_times[-1]
    ttft_ms = max(0.1, round((t_first - t0) * 1000.0, 1))
    deltas = [round((b - a) * 1000.0, 1) for a, b in zip(chunk_times, chunk_times[1:])]
    itl_ms: float | None = _median(deltas) if deltas else None

    decode_tps = _decode_tps(completion_tokens, chunk_times, t_first, t_last, t_total)

    return {
        "response": content,
        "tps": decode_tps,
        "ttft_ms": ttft_ms,
        "ttft_method": "streaming",
        "itl_ms": itl_ms,
        "output_tokens": completion_tokens,
        "total_duration_s": round(t_total, 2),
    }


def run_openai_benchmark(
    model: str,
    runs: int = 1,
    base_url: str = "http://localhost:1234",
    prompt: str = "Write a concise explanation of local AI execution in 3 bullet points.",
    max_tokens: int = 100,
) -> dict[str, Any]:
    """OpenAI uyumlu sunucu üzerinde benchmark koşusu yapar ve metrikleri döner."""
    tps_list: list[float] = []
    total_tokens = 0
    total_ms = 0.0
    last_ttft = 0.0
    last_itl: float | None = None
    last_method = "estimated"

    for _ in range(max(1, runs)):
        gen = openai_generate(
            prompt=prompt,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
        )
        tps_list.append(gen["tps"])
        total_tokens += gen["output_tokens"]
        total_ms += gen["total_duration_s"] * 1000.0
        last_ttft = gen["ttft_ms"]
        last_itl = gen.get("itl_ms")
        last_method = str(gen.get("ttft_method") or "estimated")

    avg_tps = round(sum(tps_list) / len(tps_list), 1) if tps_list else 0.0

    return {
        "model": model,
        "provider": "openai-compatible",
        "measured_tps": avg_tps,
        "ttft_ms": last_ttft,
        "ttft_method": last_method,
        "itl_ms": last_itl,
        "output_tokens": total_tokens,
        "total_ms": round(total_ms, 1),
        "runs": runs,
        "source": "real",
    }
