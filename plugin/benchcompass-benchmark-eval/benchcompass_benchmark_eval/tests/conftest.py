"""Plugin test yapılandırması — paket kökünü sys.path'e ekler.

Test hijyeni: `config.REPORTS_DIR` gerçek `reports/` dizinini (git'te TAKİPLİ
`index.md` / `index.html`) gösterir. Bu dizine yazan bir test, depodaki
raporu her koşuda kirletir (bkz. test_history.py regresyonu). Bu yüzden
aşağıdaki autouse fixture her test için çıktı dizinini geçici bir yola
yönlendirir; testler artık `--basetemp` veya elle monkeypatch olmadan da
takip edilen hiçbir dosyaya dokunmaz.
P1-7: CI ortamında (GitHub Actions) deterministik offline mock sağlar.
"""

import os
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from benchcompass_benchmark_eval import config  # noqa: E402  (sys.path sonrası)

# Testlerin asla yazmaması gereken, git'te takipli gerçek rapor dizini.
TRACKED_REPORTS_DIR = config.REPORTS_DIR

# CI mock şeması — harness.measure_speed'ın GERÇEK dönüş sözleşmesiyle aynı
# anahtar setini taşır (bkz. harness.measure_speed dönüş dict'i). Runner
# `s.get("gen_tps")` ile filtrelediği için eksik anahtar mock sonuçlarının
# sessizce elenmesine yol açar (Y24: dış sözleşme varsayma — gerçekle doğrula).
MOCK_SPEED_RESULT: dict = {
    "gen_tps": 42.0,
    "prefill_tps": 120.0,
    "ttft_ms": 100.0,
    "total_ms": 3000.0,
    "eval_count": 128,
    "prompt_eval_count": 24,
    "load_ms": 800.0,
    "model": "mock",
}


@pytest.fixture(autouse=True)
def isolated_reports_dir(tmp_path, monkeypatch):
    """Her testte `config.REPORTS_DIR`'i geçici dizine yönlendirir.

    Autouse: unutulan bir monkeypatch artık depoyu kirletemez. Testin kendi
    monkeypatch'i bu fixture'dan sonra uygulanır ve onu geçersiz kılar.
    """
    target = tmp_path / "_isolated_reports"
    monkeypatch.setattr(config, "REPORTS_DIR", target)
    return target


@pytest.fixture
def tracked_reports_dir() -> Path:
    """Git'te takipli gerçek rapor dizini (regresyon testleri için)."""
    return TRACKED_REPORTS_DIR


@pytest.fixture(autouse=True)
def mock_ollama_in_ci(monkeypatch):
    """CI ortamında (GitHub Actions) gerçek model çağrısı yerine deterministik mock döner (P1-7)."""
    if os.environ.get("CI"):
        from benchcompass_benchmark_eval import harness

        monkeypatch.setattr(
            harness,
            "generate",
            lambda *a, **kw: "mock response 42",
        )
        monkeypatch.setattr(
            harness,
            "measure_speed",
            lambda *a, **kw: dict(MOCK_SPEED_RESULT),
        )
        monkeypatch.setattr(
            harness,
            "available_models",
            lambda *a, **kw: ["qwen3:8b", "llama3:8b"],
        )
        monkeypatch.setattr(harness, "warm_up", lambda *a, **kw: None)
