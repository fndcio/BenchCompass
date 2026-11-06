"""api/gguf_parser.py — Hafif ve Güvenli GGUF Başlık Okuyucu (Zero-Config Keşif).

GGUF dosyalarının yalnızca ilk metadata başlığını okur; tensor ağırlıklarını
asla belleğe almaz. Bellek ve I/O dostudur (ADR-0012, Ortakheyet konsensüsü).
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path
from typing import Any

# GGUF Value Types
GGUF_TYPE_UINT8 = 0
GGUF_TYPE_INT8 = 1
GGUF_TYPE_UINT16 = 2
GGUF_TYPE_INT16 = 3
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_INT32 = 5
GGUF_TYPE_FLOAT32 = 6
GGUF_TYPE_BOOL = 7
GGUF_TYPE_STRING = 8
GGUF_TYPE_ARRAY = 9
GGUF_TYPE_UINT64 = 10
GGUF_TYPE_INT64 = 11
GGUF_TYPE_FLOAT64 = 12

TYPE_FORMATS = {
    GGUF_TYPE_UINT8: ("<B", 1),
    GGUF_TYPE_INT8: ("<b", 1),
    GGUF_TYPE_UINT16: ("<H", 2),
    GGUF_TYPE_INT16: ("<h", 2),
    GGUF_TYPE_UINT32: ("<I", 4),
    GGUF_TYPE_INT32: ("<i", 4),
    GGUF_TYPE_FLOAT32: ("<f", 4),
    GGUF_TYPE_BOOL: ("<?", 1),
    GGUF_TYPE_UINT64: ("<Q", 8),
    GGUF_TYPE_INT64: ("<q", 8),
    GGUF_TYPE_FLOAT64: ("<d", 8),
}

# Ağır tokenizer array'lerini atlamak için anahtar desenleri
SKIP_KEYS = {
    "tokenizer.ggml.tokens",
    "tokenizer.ggml.merges",
    "tokenizer.ggml.token_type",
    "tokenizer.ggml.scores",
}


def _read_str(f: io.BufferedReader) -> str:
    len_bytes = f.read(8)
    if len(len_bytes) < 8:
        return ""
    (length,) = struct.unpack("<Q", len_bytes)
    if length > 10 * 1024 * 1024:
        return ""
    val_bytes = f.read(length)
    return val_bytes.decode("utf-8", errors="ignore")


def _read_value(f: io.BufferedReader, val_type: int) -> Any:
    if val_type in TYPE_FORMATS:
        fmt, size = TYPE_FORMATS[val_type]
        raw = f.read(size)
        if len(raw) < size:
            return None
        return struct.unpack(fmt, raw)[0]
    if val_type == GGUF_TYPE_STRING:
        return _read_str(f)
    if val_type == GGUF_TYPE_ARRAY:
        raw_arr = f.read(12)
        if len(raw_arr) < 12:
            return None
        elem_type, arr_len = struct.unpack("<IQ", raw_arr)
        if arr_len > 1000:
            if elem_type in TYPE_FORMATS:
                _, size = TYPE_FORMATS[elem_type]
                f.seek(arr_len * size, io.SEEK_CUR)
            return f"<array[{arr_len}]>"
        items = []
        for _ in range(arr_len):
            items.append(_read_value(f, elem_type))
        return items
    return None


def _skip_large_array(f: io.BufferedReader) -> None:
    """Tokenizer gibi çok büyük array'leri bellek tüketmeden dosya işaretçisiyle atlar."""
    arr_hdr = f.read(12)
    if len(arr_hdr) != 12:
        return
    elem_type, arr_len = struct.unpack("<IQ", arr_hdr)
    if elem_type == GGUF_TYPE_STRING:
        for _ in range(arr_len):
            slen_b = f.read(8)
            if len(slen_b) < 8:
                break
            (slen,) = struct.unpack("<Q", slen_b)
            f.seek(slen, io.SEEK_CUR)
    elif elem_type in TYPE_FORMATS:
        _, size = TYPE_FORMATS[elem_type]
        f.seek(arr_len * size, io.SEEK_CUR)


def _apply_meta_kv(key: str, val: Any, meta: dict[str, Any]) -> None:
    """Okunan tek bir anahtar-değer çiftini hedef meta sözlüğüne işler."""
    if key == "general.architecture":
        meta["architecture"] = str(val)
    elif key == "general.name":
        meta["general_name"] = str(val)
    elif "context_length" in key:
        try:
            meta["context_length"] = int(val)
        except Exception:  # noqa: BLE001
            pass
    elif key == "general.file_type":
        meta["file_type"] = val


def extract_quant_from_filename(filename: str) -> str:
    """Dosya adından quantization tipini tahmin eder (örn: q4_k_m, iq2_m, bf16)."""
    match = re.search(
        r"(q[0-9]_[a-z0-9_]+|q[0-9][a-z0-9_]+|iq[0-9]_[a-z0-9_]+|bf16|fp16|nvfp4)",
        filename.lower(),
    )
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


def _read_header_counts(f: io.BufferedReader) -> tuple[int, int] | None:
    """GGUF başlığından tensor_count ve kv_count okur."""
    magic = f.read(4)
    if magic != b"GGUF":
        return None
    ver_bytes = f.read(4)
    if len(ver_bytes) < 4:
        return None
    t_bytes = f.read(8)
    k_bytes = f.read(8)
    if len(t_bytes) < 8 or len(k_bytes) < 8:
        return None
    (tensor_count,) = struct.unpack("<Q", t_bytes)
    (kv_count,) = struct.unpack("<Q", k_bytes)
    return tensor_count, kv_count


def read_gguf_metadata(file_path: Path | str) -> dict[str, Any]:
    """GGUF dosyasının metadata başlığını okur. Ağırlıkları yüklemez."""
    p = Path(file_path)
    if not p.exists() or p.stat().st_size < 32:
        return {"error": "Dosya bulunamadı veya boyutu çok küçük"}

    meta: dict[str, Any] = {
        "file_name": p.name,
        "file_path": str(p.resolve()),
        "size_bytes": p.stat().st_size,
        "size_gb": round(p.stat().st_size / (1024**3), 2),
        "mtime": p.stat().st_mtime,
        "architecture": "unknown",
        "quant_type": extract_quant_from_filename(p.name),
        "context_length": 4096,
        "general_name": p.stem,
        "tensor_count": 0,
    }

    try:
        with open(p, "rb") as f:
            counts = _read_header_counts(f)
            if not counts:
                meta["error"] = "Geçersiz GGUF başlığı"
                return meta
            tensor_count, kv_count = counts
            meta["tensor_count"] = tensor_count

            for _ in range(kv_count):
                key = _read_str(f)
                type_bytes = f.read(4)
                if len(type_bytes) < 4:
                    break
                (val_type,) = struct.unpack("<I", type_bytes)

                if key in SKIP_KEYS and val_type == GGUF_TYPE_ARRAY:
                    _skip_large_array(f)
                    continue

                val = _read_value(f, val_type)
                _apply_meta_kv(key, val, meta)
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)

    return meta
