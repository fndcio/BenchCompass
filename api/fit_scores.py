"""Fit skoru & baseline verisi — api/fit_scores.py

Sprint 21: AlexsJones/llmfit (MIT) `use_case_benchmarks.json` (model aileleri →
coding/reasoning/chat skorları) ve `baselines.json` (frontier modeller → 18 rol ×
quality/speed/composite). Local-First: veri lokal `data/` altında yaşar.

Aile eşleşmesi kuralı: model adının küçük harfli halinde, family match listesindeki
en uzun alt-dize kazanır (örn. 'qwen3.5-coder' hem 'qwen3' hem 'qwen3.5-coder' ile
eşleşir → daha spesifik olan kazanır).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent
DEFAULT_USECASE_PATH = BASE / "data" / "use_case_benchmarks.json"
DEFAULT_BASELINE_PATH = BASE / "data" / "baselines.json"


class FitScores:
    """Use-case skorları + baseline verisi — aile eşleştirme."""

    def __init__(
        self, usecase_path: Path | None = None, baseline_path: Path | None = None
    ):
        self.usecase_path = Path(usecase_path) if usecase_path else DEFAULT_USECASE_PATH
        self.baseline_path = (
            Path(baseline_path) if baseline_path else DEFAULT_BASELINE_PATH
        )
        self.families: list[dict] = []
        self.baselines: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Her iki JSON'ı yükler. Dosya yoksa boş (çökmez)."""
        self.families = []
        self.baselines = {}
        if self.usecase_path.exists():
            try:
                data = json.loads(self.usecase_path.read_text(encoding="utf-8"))
                self.families = (
                    data.get("families", []) if isinstance(data, dict) else []
                )
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.families = []
        if self.baseline_path.exists():
            try:
                data = json.loads(self.baseline_path.read_text(encoding="utf-8"))
                bl = data.get("baselines", []) if isinstance(data, dict) else []
                self.baselines = {b.get("model", ""): b for b in bl if b.get("model")}
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.baselines = {}

    # --- Aile eşleştirme (en uzun alt-dize kazanır) ---
    def family_for(self, model_name: str) -> dict | None:
        """Model adıyla eşleşen aileyi döndürür (en uzun match kazanır)."""
        needle = (model_name or "").strip().lower()
        if not needle or not self.families:
            return None
        best: dict | None = None
        best_len = -1
        for fam in self.families:
            for m in fam.get("match", []):
                pat = str(m).lower()
                if pat and pat in needle and len(pat) > best_len:
                    best = fam
                    best_len = len(pat)
        return best

    def use_case_score(self, model_name: str, use_case: str) -> int | None:
        """Aile eşleşirse o use_case skorunu döndürür (0-100), yoksa None."""
        fam = self.family_for(model_name)
        if not fam:
            return None
        return fam.get("scores", {}).get(use_case)

    # --- Baseline karşılaştırma ---
    def baseline_for_role(self, model_name: str, role: str) -> dict | None:
        """Model + rol baseline skorunu döndürür (quality/speed/composite)."""
        bl = self.baselines.get(model_name)
        if not bl:
            return None
        roles = bl.get("roles") or {}
        role_data = roles.get(role)
        if role_data:
            return {"model": model_name, "provider": bl.get("provider"), **role_data}
        return None

    def top_baseline_for_role(self, role: str) -> dict | None:
        """Bir rol için en yüksek composite'li baseline modelini döndürür."""
        best: dict | None = None
        best_score = -1.0
        for model_name, bl in self.baselines.items():
            roles = bl.get("roles") or {}
            role_data = roles.get(role)
            if not role_data:
                continue
            composite = float(role_data.get("composite") or 0)
            if composite > best_score:
                best_score = composite
                best = {
                    "model": model_name,
                    "provider": bl.get("provider"),
                    "quality": role_data.get("quality"),
                    "speed": role_data.get("speed"),
                    "composite": role_data.get("composite"),
                }
        return best


# Modül seviyesinde singleton (FastAPI endpoint'leri için)
_default_fit: FitScores | None = None


def get_fit() -> FitScores:
    """Varsayılan fit verisini döndürür (dosya yoksa boş — çökmez)."""
    global _default_fit
    if _default_fit is None:
        _default_fit = FitScores()
    return _default_fit


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
