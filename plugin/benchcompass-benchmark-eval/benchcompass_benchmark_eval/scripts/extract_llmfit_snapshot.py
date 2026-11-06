"""llmfit veri snapshot'ı üretir (standalone mod için önbellek).

Parent projenin data/ (hf_models.json, benchmark_cache.json) içeriğinden,
plugin data/llmfit_snapshot_<tarih>.json dosyası üretir. Bu sayede plugin
başka bir projeye kopyalandığında llmfit zenginliğini önbellekten kullanabilir.

Kullanım:
    python -m benchcompass_benchmark_eval.scripts.extract_llmfit_snapshot [--data-dir <path>]
"""

from __future__ import annotations

import argparse
import sys

from .. import llmfit_data


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="llmfit data snapshot üret")
    p.add_argument(
        "--data-dir", default=None, help="llmfit data/ yolu (varsayılan: parent proje)"
    )
    args = p.parse_args(argv or sys.argv[1:])
    try:
        path = llmfit_data.build_snapshot(args.data_dir)
    except FileNotFoundError as e:
        print(f"Hata: {e}")
        return 1
    print(f"Snapshot yazıldı: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
