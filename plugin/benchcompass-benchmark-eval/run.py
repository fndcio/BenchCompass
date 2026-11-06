"""Kolay başlatıcı: python run.py [seçenekler]

Kısayol:
    python run.py --pipeline
    python run.py --models qwen3:8b gemma4:12b
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchcompass_benchmark_eval.scripts.run_benchmark import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
