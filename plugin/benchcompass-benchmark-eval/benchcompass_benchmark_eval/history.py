"""B5: SQLite geçmiş / zaman serisi çözümleyici (parent benchmark_history.db).

Entegre modda parent projenin `benchmark_history.db`'sindeki `benchmarks`
tablosundan per-model zaman serisi okunur. Standalone/DB yoksa boş dict döner
(zarifçe atlanır — bağımsız çalışma ilkesi kırılmaz).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config


def load_history(db_path: Path | str | None = None) -> dict[str, list[dict]]:
    """benchmarks tablosundan per-model zaman serisini okur.

    Sonuç: {model_adı: [{tps, ttft_ms, created_at, source}, ...]} — created_at
    artan sırada. DB yoksa veya okunamazsa boş dict.
    """
    if db_path is None:
        db_path = config.find_parent_sqlite()
    if db_path is None or not Path(db_path).exists():
        return {}
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT model, measured_tps, ttft_ms, created_at, source"
            " FROM benchmarks WHERE measured_tps IS NOT NULL"
            " ORDER BY created_at ASC, id ASC"
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return {}
    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["model"], []).append(
            {
                "tps": r["measured_tps"],
                "ttft_ms": r["ttft_ms"],
                "created_at": r["created_at"],
                "source": r["source"],
            }
        )
    return series


def summarize_history(series: dict[str, list[dict]], limit: int = 5) -> dict[str, dict]:
    """Her model için son ölçümler + trend yönü (yükseliyor/düşüyor/sabit)."""
    out: dict[str, dict] = {}
    for model, rows in series.items():
        recent = rows[-limit:]
        tps_list = [r["tps"] for r in recent if r.get("tps") is not None]
        first = tps_list[0] if tps_list else None
        last = tps_list[-1] if tps_list else None
        trend = "sabit"
        if first is not None and last is not None:
            if last > first * 1.05:
                trend = "yükseliyor"
            elif last < first * 0.95:
                trend = "düşüyor"
        out[model] = {
            "measurements": len(rows),
            "last_tps": last,
            "trend": trend,
            "recent": recent[-limit:],
        }
    return out
