"""Gerçek community benchmark verisi — api/bench_data.py

Sprint 20: AlexsJones/llmfit (MIT) `benchmark_cache.json` gerçek topluluk
ölçümlerini (tok/s, TTFT) donanım bazlı sunar. Local-First: veri lokal
`data/benchmark_cache.json` altında yaşar.

Eşleştirme stratejisi (donanım):
  1. GPU adı birebir (küçük/büyük harf duyarsız)
  2. GPU adı alt-dizesi (örn. 'RTX 5070 Laptop' → 'RTX 5070')
  3. Eşleşme yoksa boş → çağıran taraf mevcut tahmine düşer (yıkıcı değişiklik YOK)

Model eşleştirme: hfId veya displayName içinde model adı alt-dizesi aranır.
Aynı model farklı quant'ta birden çok ölçüm içerebilir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent
DEFAULT_BENCH_PATH = BASE / "data" / "benchmark_cache.json"


class BenchData:
    """Benchmark cache verisi — donanım + model eşleştirme."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DEFAULT_BENCH_PATH
        self.presets: dict[str, list[dict]] = {}
        self.total_rows = 0
        self.loaded = False
        self.load()

    def load(self) -> None:
        """Cache'i yükler. Dosya yoksa boş (çökmez)."""
        if not self.path.exists():
            self.presets = {}
            self.total_rows = 0
            self.loaded = False
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            presets = data.get("presets", {}) if isinstance(data, dict) else {}
            self.presets = {}
            for label, group in presets.items():
                rows = group.get("rows", []) if isinstance(group, dict) else []
                if rows:
                    self.presets[label] = rows
                    self.total_rows += len(rows)
            self.loaded = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.presets = {}
            self.total_rows = 0
            self.loaded = False

    # --- GPU eşleştirme ---
    def lookup_gpu(self, gpu_name: str) -> list[dict]:
        """GPU adıyla eşleşen preset'in satırlarını döndürür (boşsa [])."""
        if not gpu_name:
            return []
        norm = gpu_name.strip().lower()
        # 1) birebir (anahtar zaten küçük harfe normalize değil — büyük/küçük duyarsız)
        for label, rows in self.presets.items():
            if label.lower() == norm:
                return rows
        # 2) alt-dize (preset etiketi gpu adının içinde mi, ya da tersi)
        for label, rows in self.presets.items():
            lbl = label.lower()
            if lbl and (lbl in norm or norm in lbl):
                return rows
        return []

    # --- Model eşleştirme ---
    def lookup_model(self, model_name: str, gpu_name: str = "") -> list[dict]:
        """Donanım eşleşen satırlardan model adını içerenleri döndürür."""
        rows = self.lookup_gpu(gpu_name)
        if not rows:
            return []
        needle = (model_name or "").strip().lower()
        if not needle:
            return []
        out = []
        for r in rows:
            model = r.get("model") or {}
            hf = (model.get("hfId") or "").lower()
            disp = (model.get("displayName") or "").lower()
            if needle in hf or needle in disp or hf in needle or disp in needle:
                out.append(r)
        return out

    # --- Özet hız ---
    def speed_map_for_gpu(self, gpu_name: str) -> dict[str, dict]:
        """Donanım için model-adı → hız özeti haritası (tek lookup — N+1 yok).

        Sıralama: önce birebir model eşleşmesi; aynı model birden çok satırda
        varsa en yüksek tokSOut kazanır. Sorgu: hfId veya displayName alt-dizesi.
        """
        rows = self.lookup_gpu(gpu_name)
        if not rows:
            return {}
        out: dict[str, dict] = {}
        for r in rows:
            model = r.get("model") or {}
            hf = (model.get("hfId") or "").lower()
            disp = (model.get("displayName") or "").lower()
            key = hf or disp
            if not key:
                continue
            speed = _num(r.get("tokSOut"))
            if speed is None:
                continue
            existing = out.get(key)
            if existing is None or speed > existing["measured_tps"]:
                hw = r.get("hardware") or {}
                out[key] = {
                    "measured_tps": speed,
                    "total_tps": _num(r.get("tokSTotal")),
                    "ttft_ms": _num(r.get("ttftMs")),
                    "quantization": (r.get("engine") or {}).get("quantization"),
                    "matched_gpu": hw.get("gpuName"),
                    "source": "community",
                }
        return out

    def get_speed_for_model(self, model_name: str, gpu_name: str = "") -> dict | None:
        """Donanım+model eşleşirse gerçek ölçüm özeti döner; yoksa None.

        Dönüş: {measured_tps, ttft_ms, total_tps, source: 'community', matched_gpu}
        """
        rows = self.lookup_model(model_name, gpu_name)
        if not rows:
            return None
        # En yüksek tokSOut'lu ölçümü seç (en iyi temsil)
        best = max(
            rows, key=lambda r: float(r.get("tokSOut") or 0) if r.get("tokSOut") else -1
        )
        hw = best.get("hardware") or {}
        return {
            "measured_tps": _num(best.get("tokSOut")),
            "total_tps": _num(best.get("tokSTotal")),
            "ttft_ms": _num(best.get("ttftMs")),
            "quantization": (best.get("engine") or {}).get("quantization"),
            "matched_gpu": hw.get("gpuName"),
            "source": "community",
        }

    def get_reference_tps(self, model_name: str, gpu_name: str = "") -> float | None:
        """Donanım sınıfı veya genel topluluk için referans tok/s döner (P1-1)."""
        res = self.get_speed_for_model(model_name, gpu_name)
        if res and res.get("measured_tps"):
            return res["measured_tps"]
        # GPU eşleşmediyse tüm donanımlardaki model ortalamasını bul
        all_rows = []
        for rows in self.presets.values():
            all_rows.extend(rows)
        needle = (model_name or "").strip().lower()
        model_speeds = []
        for r in all_rows:
            m = r.get("model") or {}
            hf = (m.get("hfId") or "").lower()
            disp = (m.get("displayName") or "").lower()
            if needle in hf or needle in disp or hf in needle or disp in needle:
                spd = _num(r.get("tokSOut"))
                if spd and spd > 0:
                    model_speeds.append(spd)
        if model_speeds:
            return round(sum(model_speeds) / len(model_speeds), 1)
        return None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# Modül seviyesinde singleton (FastAPI endpoint'leri için)
_default_bench: BenchData | None = None


def get_bench() -> BenchData:
    """Varsayılan benchmark verisini döndürür (dosya yoksa boş — çökmez)."""
    global _default_bench
    if _default_bench is None:
        _default_bench = BenchData()
    return _default_bench
