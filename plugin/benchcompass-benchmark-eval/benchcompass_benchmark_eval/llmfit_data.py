"""llmfit veri çözümleyici — bağımsız çalışma ile entegre zenginliği birleştirir.

Çözümleme sırası (kırılmadan bağımsız çalışma):
  1. Açık `--llmfit-data-dir` veya otomatik tespit: parent proje `data/`
     (hf_models.json, benchmark_cache.json) varsa canlı okunur.
  2. Yoksa: plugin kendi `data/llmfit_snapshot_*.json` önbelleğini kullanır.
  3. `--live-api` AÇIKSA: canlı llmfit API'den (localhost llmfit katalog
     endpoint) sorgulanır — erişilemezse yok gibi davranır (Local-First korunur).
  4. O da yoksa: llmfit verisi olmadan çalışır (graceful degradation).

Bu sayede aynı `data/` klasörü paylaşılabilir (entegre mod) ama plugin başka
bir projede de bağımsız koşar (standalone mod).
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config


@dataclass
class LlmfitData:
    """llmfit kaynaklarından çözümlenmiş veri."""

    mode: str  # 'parent' | 'snapshot' | 'live_api' | 'none'
    source_path: str | None = None
    hf_models: list[dict] = field(default_factory=list)
    benchmark_cache: dict[str, Any] = field(default_factory=dict)

    def is_enriched(self) -> bool:
        return bool(
            self.mode in ("parent", "snapshot", "live_api")
            and (self.hf_models or self.benchmark_cache)
        )

    def models_fitting_vram(self, vram_gb: float, limit: int = 40) -> list[dict]:
        """min_vram_gb <= vram_gb olan GGUF modelleri (download sıralı)."""
        rows = []
        for m in self.hf_models:
            mv = m.get("min_vram_gb")
            if mv is None or mv > vram_gb or m.get("format") != "gguf":
                continue
            rows.append(m)
        rows.sort(key=lambda m: m.get("hf_downloads") or 0, reverse=True)
        return rows[:limit]

    def speed_presets(self, preset_names: list[str]) -> dict[str, list[dict]]:
        """benchmark_cache presets'lerinden ölçüm satırlarını döndürür."""
        presets = self.benchmark_cache.get("presets", {})
        out: dict[str, list[dict]] = {}
        for name in preset_names:
            p = presets.get(name)
            if isinstance(p, dict) and "rows" in p:
                out[name] = p["rows"]
        return out


def _latest_snapshot() -> Path | None:
    """Plugin data/ altındaki en yeni llmfit_snapshot_*.json dosyasını bulur."""
    files = sorted(glob.glob(str(config.DATA_DIR / "llmfit_snapshot_*.json")))
    return Path(files[-1]) if files else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_live_api() -> tuple[list[dict], dict[str, Any]] | None:
    """Canlı llmfit API'den katalog + benchmark verisini dener.

    Sprint 34 (ADR-0004 Gelecek — P3): Yalnızca `--live-api` açıkken çağrılır.
    Erişilemez/sağlıksızsa None döner — asla istisna fırlatmaz (Local-First).
    """

    try:
        import urllib.request

        base = "http://localhost:8788/api"
        with urllib.request.urlopen(f"{base}/catalog", timeout=5) as resp:
            cat = json.loads(resp.read().decode("utf-8"))
        hf = cat.get("models") or []
        bc = {}
        try:
            with urllib.request.urlopen(
                f"{base}/benchmarks?limit=500", timeout=5
            ) as br:
                bench = json.loads(br.read().decode("utf-8"))
            runs = bench.get("benchmarks") or []
            presets: dict[str, Any] = {}
            for r in runs:
                presets.setdefault(r.get("model") or "unknown", []).append(r)
            bc = {"presets": presets}
        except Exception:  # noqa: BLE001 — benchmark yoksa katalog yeterli
            bc = {}
        return hf, bc
    except Exception:  # noqa: BLE001 — canlı API erişilemezse graceful
        return None


def resolve(llmfit_data_dir: str | None = None, live_api: bool = False) -> LlmfitData:
    """Çözümleme sırası: parent -> snapshot -> live_api -> none."""
    # 1) Parent entegre mod
    candidates = [llmfit_data_dir, str(config.find_parent_llmfit_data())]
    for c in candidates:
        if not c:
            continue
        d = Path(c)
        if not d.is_dir():
            continue
        hf = d / "hf_models.json"
        bc = d / "benchmark_cache.json"
        hf_list = _load_json(hf) if hf.exists() else []
        bc_data = _load_json(bc) if bc.exists() else {}
        return LlmfitData(
            mode="parent",
            source_path=str(d),
            hf_models=hf_list if isinstance(hf_list, list) else [],
            benchmark_cache=bc_data if isinstance(bc_data, dict) else {},
        )

    # 2) Snapshot (standalone önbellek)
    snap = _latest_snapshot()
    if snap is not None:
        data = _load_json(snap)
        return LlmfitData(
            mode="snapshot",
            source_path=str(snap),
            hf_models=data.get("hf_models", []) if isinstance(data, dict) else [],
            benchmark_cache=data.get("benchmark_cache", {})
            if isinstance(data, dict)
            else {},
        )

    # 3) Canlı API (yalnızca --live-api açıkken)
    if live_api:
        live = _fetch_live_api()
        if live is not None:
            hf_list, bc_data = live
            return LlmfitData(
                mode="live_api",
                source_path="http://localhost:8788/api",
                hf_models=hf_list if isinstance(hf_list, list) else [],
                benchmark_cache=bc_data if isinstance(bc_data, dict) else {},
            )

    # 4) Yok -> llmfit verisi olmadan
    return LlmfitData(mode="none")


def build_snapshot(data_dir: str | None = None, out: str | None = None) -> Path:
    """Parent data/'dan snapshot üretir (standalone mod için önbellek)."""
    import datetime

    src = Path(data_dir) if data_dir else config.find_parent_llmfit_data()
    if src is None or not src.exists():
        raise FileNotFoundError("llmfit data/ bulunamadı. --data-dir verilmelidir.")

    hf = src / "hf_models.json"
    bc = src / "benchmark_cache.json"
    snapshot = {
        "source": str(src),
        "hf_models": _load_json(hf) if hf.exists() else [],
        "benchmark_cache": _load_json(bc) if bc.exists() else {},
    }
    path = config.DATA_DIR / f"llmfit_snapshot_{datetime.date.today().isoformat()}.json"
    if out:
        path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    return path
