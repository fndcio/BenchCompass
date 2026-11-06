"""Değerlendirme koşulları ve yolları.

Y17: Eşikler/ayarlar koda sabitlenmez — tek kaynak bu modül + tasks/*.json.
Kullanıcı ihtiyacına göre çevresel değişken veya argümanlarla override edilebilir.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

PACKAGE_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = PACKAGE_DIR.parent  # plugin/benchcompass-benchmark-eval/
TASKS_DIR = PACKAGE_DIR / "tasks"
DATA_DIR = PACKAGE_DIR / "data"
REPORTS_DIR = PACKAGE_DIR / "reports"

# --- Ollama ----------------------------------------------------------------
OLLAMA_URL = os.environ.get("LLMFIT_EVAL_OLLAMA_URL", "http://localhost:11434")

# --- Değerlendirme koşulları (varsayılan) ----------------------------------


class EvalDefaults(TypedDict):
    """Varsayılan değerlendirme koşulları (mypy tip güvenliği için)."""

    speed_runs: int
    temperature: float
    quality_num_predict: int
    speed_num_predict: int
    think: bool
    keep_alive: str
    request_timeout: int
    speed_prompt: str


DEFAULTS: EvalDefaults = {
    "speed_runs": 3,  # hız ölçümü tekrar sayısı (P0-4: N≥3 istatistiksel taban)
    "temperature": 0.0,  # deterministik çıktı
    "quality_num_predict": 1024,  # kalite görevlerinde token bütçesi
    "speed_num_predict": 512,  # hız testi çıktı uzunluğu
    "think": False,  # thinking modu (deepseek-r1 gibi her zaman düşünenler hariç)
    "keep_alive": "10m",  # modelin bellekte tutulma süresi
    "request_timeout": 600,  # tek istek timeout (sn)
    "speed_prompt": (
        "Explain in detail how photosynthesis works in plants, including the light "
        "reactions, the Calvin cycle, and why plants are green. Write at least 200 words."
    ),
}

# --- Varsayılan görev suite'leri -------------------------------------------
DEFAULT_SUITES = ["suite_default", "suite_tr"]

# --- Standart Akademik Görev Köprüsü (P0-5) -------------------------------
STANDARD_TASK_MAP: dict[str, str] = {
    "suite_default": "GSM8K & MMLU-Pro Alt-Kümesi",
    "suite_tr": "IFEval TR / Türkçe Anlama",
    "suite_vision": "DocVQA / MMMU Alt-Kümesi",
    "b1_instruction": "IFEval",
    "b1_reasoning": "MMLU-Pro (50-item subset)",
    "b3_code": "HumanEval+",
    "b4_retrieval": "MTEB-retrieval",
}


# --- SQLite (entegre mod, opsiyonel) ---------------------------------------
# Parent projenin benchmark_history.db'sini bulmaya çalışır.
def find_parent_sqlite() -> Path | None:
    """Parent projede benchmark_history.db varsa yolunu döndürür, yoksa None."""
    # plugin/benchcompass-benchmark-eval/benchcompass_benchmark_eval -> yukarı 3 = proje kökü
    probe = PLUGIN_DIR.parent.parent / "benchmark_history.db"
    return probe if probe.exists() else None


# --- llmfit veri çözümleyici varsayılan yolu --------------------------------
def find_parent_llmfit_data() -> Path | None:
    """Parent projede data/ (hf_models.json vb.) varsa döndürür, yoksa None."""
    probe = PLUGIN_DIR.parent.parent / "data"
    if probe.exists() and (probe / "hf_models.json").exists():
        return probe
    return None
