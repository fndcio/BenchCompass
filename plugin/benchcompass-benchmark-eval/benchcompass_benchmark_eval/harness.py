"""Ollama REST istemcisi — hız ölçümü ve üretim çağrıları.

Hız metrikleri Ollama /api/generate yanıtının resmi alanlarından hesaplanır:
  - eval_count / eval_duration  -> tok/s (generation)
  - prompt_eval_count / prompt_eval_duration -> tok/s (prefill)
  - TTFT akışlı (stream) istekle ilk token zamanı (bayt bayt okuma, doğru ölçüm)
  - load_duration -> model yükleme süresi
"""

from __future__ import annotations

import base64
import json
import math
import re
import struct
import time
import urllib.request
import zlib
from typing import Any

from . import config

# Ollama model adı sonundaki quant/tip sonekleri (ör. qwen3:8b-q4_K_M, llama3-fp16)
_QUANT_RE = re.compile(r"[-_]((?:i?q|Q)\d[\w.]*|(?:[bi]?f|fp)(?:16|32)|f16|f32)$")


def model_quant(name: str) -> str | None:
    """Ollama model adından quant bilgisini çıkarır.

    Örnekler: ``qwen3:8b-q4_K_M`` -> ``q4_K_M``, ``llama3:8b`` -> ``None``.
    B1 (çoklu quant karşılaştırma): aynı aile içi quant'ları gruplamak için.
    """
    tag = name.split(":", 1)[-1]
    m = _QUANT_RE.search(tag)
    return m.group(1) if m else None


def model_family(name: str) -> str:
    """Quant/sonek olmadan model ailesi adı.

    Örnekler: ``qwen3:8b-q4_K_M`` -> ``qwen3:8b``, ``llama3:8b`` -> ``llama3:8b``.
    """
    tag = name.split(":", 1)[-1]
    m = _QUANT_RE.search(tag)
    if not m:
        return name
    base_tag = tag[: m.start()].rstrip("-").rstrip("_")
    if not base_tag:
        return name
    return name[: name.rfind(":") + 1] + base_tag


class OllamaError(Exception):
    """Ollama çağrısı sırasında hata."""


def _post(url: str, payload: dict, timeout: int) -> bytes:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read()
    except OSError as e:
        raise OllamaError(f"Ollama erişilemiyor ({url}): {e}") from e


def _get_json(url: str, timeout: int) -> Any:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def available_models() -> list[str]:
    """Kurulu modellerin ad listesi."""
    try:
        data = _get_json(f"{config.OLLAMA_URL}/api/tags", 15)
    except (OllamaError, OSError):
        return []
    return [m["name"] for m in data.get("models", [])]


def warm_up(model: str) -> None:
    """Modeli belleğe alır (ilk çağrı yüklemeyi yapar; ölçüme katılmaz)."""
    _post(
        f"{config.OLLAMA_URL}/api/generate",
        {
            "model": model,
            "prompt": "hi",
            "stream": False,
            "keep_alive": "5m",
            "options": {"num_predict": 1},
        },
        timeout=600,
    )


def generate(
    model: str, prompt: str, num_predict: int, temperature: float, think: bool
) -> str:
    """Tek üretim çağrısı; yanıt metnini döndürür."""
    options = {"num_predict": num_predict, "temperature": temperature}
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.DEFAULTS["keep_alive"],
        "options": options,
    }
    if think is False:
        payload["think"] = False
    raw = _post(
        f"{config.OLLAMA_URL}/api/generate", payload, config.DEFAULTS["request_timeout"]
    )
    data = json.loads(raw.decode("utf-8"))
    return data.get("response", "")


# --- B2: Context stres (needle-in-haystack) ---------------------------------
# Token->karakter kaba oranı (İngilizce filler, ~4 char/token)
_CHARS_PER_TOKEN = 4.0

_FILLER = (
    "The quick brown fox jumps over the lazy dog while the sun sets slowly. "
    "Quantum mechanics describes nature at the smallest scales of energy levels "
    "of atoms and subatomic particles. "
    "The library at the old castle holds over three thousand manuscripts about "
    "the history of navigation and astronomy. "
    "A river flows gently through the valley and into the wide blue sea beyond "
    "the green hills and the quiet forests. "
    "History remembers the names of those who dared to change the world with "
    "their ideas and their courage. "
    "Technology advances at a pace that surprises even the most optimistic "
    "observer of modern science and engineering. "
    "The stars above the desert shine brighter than anywhere else on the earth "
    "and guide the traveler through the night. "
)


def _recall_passes(answer: str, needle: str) -> bool:
    """Yanıtta gizli kod/anahtar kelime geçiyor mu? (case-insensitive)"""
    return needle.lower() in answer.lower()


def context_stress(model: str, ctx_tokens: int, needle: str, question: str) -> dict:
    """Needle-in-haystack: uzun context'te bilgi hatırlama + prefill hızı ölçer.

    B2: istenen token uzunluğuna (~char/token=4) filler tekrarlanır, gizli kod
    %50 derinliğe gömülür, sonunda hatırlama sorusu sorulur. Yanıt kısa tutulur
    (num_predict=16); ``recall`` anahtar kelimeyle doğrulanır. ``num_ctx`` istenen
    uzunluğun 2 katına ayarlanır (Ollama'nın kırpmaması için).
    """
    chars_needed = max(int(ctx_tokens * _CHARS_PER_TOKEN), len(_FILLER) * 3)
    repeat = chars_needed // len(_FILLER) + 1
    haystack = _FILLER * repeat
    mid = len(haystack) // 2
    prompt = (
        haystack[:mid]
        + "\n\nNEEDLE: "
        + needle
        + "\n\n"
        + haystack[mid:]
        + f"\n\n{question}\nAnswer with exactly one word or the code."
    )
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.DEFAULTS["keep_alive"],
        "think": False,
        "options": {
            "num_ctx": int(ctx_tokens * 2),
            "num_predict": 16,
            "temperature": 0.0,
        },
    }
    t0 = time.perf_counter()
    try:
        raw = _post(
            f"{config.OLLAMA_URL}/api/generate",
            payload,
            config.DEFAULTS["request_timeout"],
        )
    except OllamaError as e:
        return {"ctx_tokens": ctx_tokens, "error": str(e)}
    data = json.loads(raw.decode("utf-8"))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    prompt_count = data.get("prompt_eval_count")
    prompt_dur = data.get("prompt_eval_duration")
    prefill_tps = prompt_count / (prompt_dur / 1e9) if prompt_dur else None
    gen_tps = (
        data.get("eval_count") / (data.get("eval_duration") / 1e9)
        if data.get("eval_duration")
        else None
    )
    answer = data.get("response", "")
    return {
        "ctx_tokens": ctx_tokens,
        "prompt_eval_count": prompt_count,
        "prefill_tps": round(prefill_tps, 1) if prefill_tps else None,
        "gen_tps": round(gen_tps, 1) if gen_tps else None,
        "total_ms": round(elapsed_ms, 1),
        "recall": _recall_passes(answer, needle),
        "answer": answer[:160],
        "eval_count": data.get("eval_count"),
        "model": data.get("model") or model,
    }


def measure_speed(model: str) -> dict:
    """Akışlı istekle TTFT ölçer; bitiş chunk'ından tok/s metriklerini alır."""
    warm_up(model)

    payload: dict[str, Any] = {
        "model": model,
        "prompt": config.DEFAULTS["speed_prompt"],
        "stream": True,
        "keep_alive": config.DEFAULTS["keep_alive"],
        "think": False,
        "options": {
            "num_predict": config.DEFAULTS["speed_num_predict"],
            "temperature": 0.0,
        },
    }
    req = urllib.request.Request(
        f"{config.OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    ttft_ms: float | None = None
    last: dict = {}
    line_buffer = b""
    try:
        with urllib.request.urlopen(
            req, timeout=config.DEFAULTS["request_timeout"]
        ) as resp:  # noqa: S310
            while True:
                chunk = resp.read(1)  # bayt bayt — ilk token zamanı doğru ölçülsün
                if not chunk:
                    break
                line_buffer += chunk
                if b"\n" in line_buffer:
                    parts = line_buffer.split(b"\n")
                    line_buffer = parts[-1]
                    for raw in parts[:-1]:
                        if not raw.strip():
                            continue
                        try:
                            obj = json.loads(raw.decode("utf-8"))
                        except json.JSONDecodeError:
                            continue
                        if ttft_ms is None and obj.get("response"):
                            ttft_ms = (time.perf_counter() - t0) * 1000
                        last = obj
    except OSError as e:
        raise OllamaError(f"Ölçüm sırasında bağlantı hatası: {e}") from e

    total_ms = (time.perf_counter() - t0) * 1000
    gen_tps = (
        last.get("eval_count", 0) / (last.get("eval_duration", 1) / 1e9)
        if last.get("eval_duration")
        else None
    )
    pre_tps = (
        last.get("prompt_eval_count", 0) / (last.get("prompt_eval_duration", 1) / 1e9)
        if last.get("prompt_eval_duration")
        else None
    )
    return {
        "gen_tps": round(gen_tps, 1) if gen_tps else None,
        "prefill_tps": round(pre_tps, 1) if pre_tps else None,
        "ttft_ms": round(ttft_ms, 1) if ttft_ms else None,
        "total_ms": round(total_ms, 1),
        "eval_count": last.get("eval_count"),
        "prompt_eval_count": last.get("prompt_eval_count"),
        "load_ms": round((last.get("load_duration") or 0) / 1e6, 1),
        "model": last.get("model") or model,
    }


# --- B4: Vision -------------------------------------------------------------
# Minimal PNG üretici (stdlib struct + zlib — PIL bağımlılığı yok).


def _png_chunk(typ: bytes, data: bytes) -> bytes:
    c = struct.pack(">I", len(data)) + typ + data
    return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)


def synthetic_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Solid renkli PNG üretir (test görüntüsü)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def synthetic_png_split(
    width: int,
    height: int,
    left_rgb: tuple[int, int, int],
    right_rgb: tuple[int, int, int],
) -> bytes:
    """Sol/sağ iki renkli PNG üretir (mekansal anlama testi)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    half = width // 2
    left = bytes(left_rgb) * half
    right = bytes(right_rgb) * (width - half)
    idat = zlib.compress((b"\x00" + left + right) * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def vision_image(spec: str) -> bytes:
    """Vision görevlerinde kullanılan test görüntüsünü döndürür.

    Spec'ler: ``solid_red``, ``solid_green``, ``solid_blue``,
    ``split_red_blue`` (sol kırmızı, sağ mavi), ``split_blue_red``.
    """
    if spec == "solid_red":
        return synthetic_png(64, 64, (255, 0, 0))
    if spec == "solid_green":
        return synthetic_png(64, 64, (0, 160, 0))
    if spec == "solid_blue":
        return synthetic_png(64, 64, (0, 0, 255))
    if spec == "split_red_blue":
        return synthetic_png_split(64, 64, (255, 0, 0), (0, 0, 255))
    if spec == "split_blue_red":
        return synthetic_png_split(64, 64, (0, 0, 255), (255, 0, 0))
    raise ValueError(f"Bilinmeyen vision görüntüsü: {spec}")


def generate_vision(
    model: str, prompt: str, image_bytes: bytes, num_predict: int = 64
) -> str:
    """Görüntülü üretim (vision modeller — minicpm-v, Qwen3-VL vb.)."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False,
        "keep_alive": config.DEFAULTS["keep_alive"],
        "options": {"num_predict": num_predict, "temperature": 0.0},
    }
    raw = _post(
        f"{config.OLLAMA_URL}/api/generate", payload, config.DEFAULTS["request_timeout"]
    )
    data = json.loads(raw.decode("utf-8"))
    return data.get("response", "")


# --- B4: Embedding / RAG ----------------------------------------------------


def embed(model: str, text: str) -> list[float]:
    """Ollama /api/embeddings ile metin vektörünü döndürür."""
    raw = _post(
        f"{config.OLLAMA_URL}/api/embeddings",
        {"model": model, "prompt": text},
        config.DEFAULTS["request_timeout"],
    )
    data = json.loads(raw.decode("utf-8"))
    emb = data.get("embedding") or data.get("embeddings", [[]])[0]
    if not isinstance(emb, list):
        raise OllamaError("embedding yanıtı beklenen formatta değil")
    return [float(v) for v in emb]


def cosine(a: list[float], b: list[float]) -> float:
    """İki vektör arası kosinüs benzerliği."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
