#!/usr/bin/env python3
"""
LLMFit gerçek veri indirici — fetch_benchcompass_data.py
==========================================================================
Sprint 19-21: AlexsJones/llmfit (MIT) deposundaki gerçek veri dosyalarını
`data/` altına indirir. Local-First (AGENTS.md §1): veri lokal yaşar, dış
çağrı yalnızca bu script çalıştırılırken yapılır.

İndirilen dosyalar:
  data/hf_models.json          -> 5744 gerçek model kataloğu (~4.9 MB)
  data/benchmark_cache.json    -> topluluk benchmark ölçümleri (~1.4 MB)
  data/use_case_benchmarks.json-> model ailesi -> use_case skorları
  data/baselines.json          -> frontier model baseline skorları
  data/community/*.json        -> donanım bazlı gerçek ölçümler (opsiyonel)

Kullanım:
    python scripts/fetch_benchcompass_data.py            # tüm dosyalar
    python scripts/fetch_benchcompass_data.py --dry-run  # indirmeden ne yapacağını göster
    python scripts/fetch_benchcompass_data.py --check    # dosyalar mevcut mu + kayıt sayısı

Y17: Veri sabitlenmez — tek kaynak remote repo; indirme bu script üzerinden.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"

SOURCES = [
    (
        "hf_models.json",
        "https://raw.githubusercontent.com/AlexsJones/llmfit/main/llmfit-core/data/hf_models.json",
        "katalog kayıt sayısı",
    ),
    (
        "benchmark_cache.json",
        "https://raw.githubusercontent.com/AlexsJones/llmfit/main/llmfit-core/data/benchmark_cache.json",
        "benchmark cache",
    ),
    (
        "use_case_benchmarks.json",
        "https://raw.githubusercontent.com/AlexsJones/llmfit/main/llmfit-core/data/use_case_benchmarks.json",
        "use_case skorları",
    ),
    (
        "baselines.json",
        "https://raw.githubusercontent.com/AlexsJones/llmfit/main/llmfit-core/data/baselines.json",
        "baseline skorları",
    ),
]


def _http_get(url: str, timeout: int = 120) -> bytes:
    """URL'den bayt döndürür (Local-First: yalnızca bu script ağa dokunur)."""
    req = urllib.request.Request(url, headers={"User-Agent": "benchcompass"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def download_one(rel: str, url: str, timeout: int = 120) -> int:
    """Tek dosyayı data/ altına indirir. Bayt boyutu döner."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = _http_get(url, timeout=timeout)
    (DATA_DIR / rel).write_bytes(raw)
    return len(raw)


def check() -> dict:
    """Mevcut dosyaların durumunu raporlar. data/ yoksa boş dict."""
    out: dict[str, dict] = {}
    if not DATA_DIR.exists():
        return out
    for rel, _, _ in SOURCES:
        path = DATA_DIR / rel
        out[rel] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    out[rel]["record_count"] = len(data)
                elif isinstance(data, dict):
                    out[rel]["keys"] = list(data.keys())[:6]
            except (json.JSONDecodeError, UnicodeDecodeError):
                out[rel]["parse_error"] = True
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="LLMFit gerçek veri indirici")
    parser.add_argument(
        "--dry-run", action="store_true", help="İndirmeden planı göster"
    )
    parser.add_argument(
        "--check", action="store_true", help="Dosyaların durumunu raporla"
    )
    parser.add_argument("--timeout", type=int, default=120, help="İndirme timeout (sn)")
    args = parser.parse_args()

    if args.check:
        status = check()
        if not status:
            print(
                "data/ bulunamadı — önce indirme yapın: python scripts/fetch_benchcompass_data.py"
            )
            return 1
        for rel, info in status.items():
            mark = "OK" if info.get("exists") else "YOK"
            size = info.get("size_bytes", 0)
            extra = f" ({info['record_count']} kayıt)" if "record_count" in info else ""
            print(f"[{mark}] {rel} — {size:,} bayt{extra}")
        return 0

    if args.dry_run:
        print("İndirilecek dosyalar (data/ altına):")
        for rel, url, _ in SOURCES:
            print(f"  {rel}  <-  {url}")
        print(f"Toplam {len(SOURCES)} dosya.")
        return 0

    print(f"Veri dizini: {DATA_DIR}")
    total = 0
    for rel, url, label in SOURCES:
        try:
            size = download_one(rel, url, timeout=args.timeout)
            total += size
            print(f"[OK] {rel} — {size:,} bayt ({label})")
        except Exception as e:  # noqa: BLE001 — ağ hatası tüm akışı durdurmaz
            print(f"[HATA] {rel} — {e}")
            return 1
    print(f"Tamamlandı: {len(SOURCES)} dosya, toplam {total:,} bayt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
