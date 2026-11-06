"""Deklaratif YAML görev suite'leri (Adım 6, 06.11.2026 — ADR-0017).

JSON suite'leri (tasks/*.json, bkz. grading.load_suite) aynen korunur;
bu modül tasks/*.yaml dosyalarını aynı görev dict şekline çevirir, böylece
`grading.grade_task` / `runner.evaluate_model` değişmeden çalışır.

Şema (suite üst düzeyi):
  name: str (zorunlu)
  tasks: list (zorunlu, boş olamaz)
    - id: str (zorunlu, benzersiz)
      type: num | word | code | vision (zorunlu)
      prompt: str (zorunlu)
      expected/accept/test: type'a göre en az biri (grading ile aynı kural)
      lang/difficulty/category: opsiyonel, grading ile taşınır

Güvenlik: `yaml.safe_load` (YASAK: unsafe loader).
Doğrulama başarısızlığı -> ValueError (dosya/alan adı ile).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

VALID_TYPES = ("num", "word", "code", "vision")


def _fail(path: Path, msg: str) -> ValueError:
    return ValueError(f"YAML suite hatalı ({path.name}): {msg}")


def validate_task(task: Any, path: Path) -> dict:
    """Tek görev dict'ini doğrula ve normalize et."""
    if not isinstance(task, dict):
        raise _fail(path, "görev dict olmalı")
    for field in ("id", "type", "prompt"):
        if not task.get(field):
            raise _fail(path, f"'{field}' alanı zorunlu (görev: {task.get('id', '?')})")
    ttype = str(task["type"])
    if ttype not in VALID_TYPES:
        raise _fail(path, f"geçersiz type '{ttype}' (geçerli: {VALID_TYPES})")
    if ttype in ("num", "word", "vision") and not (
        task.get("expected") or task.get("accept")
    ):
        raise _fail(path, f"'expected' veya 'accept' zorunlu (görev: {task['id']})")
    if ttype == "code" and not task.get("test"):
        raise _fail(path, f"'test' alanı zorunlu (görev: {task['id']})")
    return dict(task)


def load_yaml_suite(
    path_or_name: str | Path, base_dir: Path | None = None
) -> list[dict]:
    """YAML suite dosyasından görev listesi yükle (doğrulanmış).

    `path_or_name` tam yol veya suite adı olabilir (`.yaml` eklenir).
    """
    import yaml  # opsiyonel bağımlılık; ImportError dostça mesajla yükselir

    path = Path(path_or_name)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    if not path.is_file() and path.suffix == "":
        candidate = path.with_suffix(".yaml")
        if candidate.is_file():
            path = candidate
    if not path.is_file():
        raise FileNotFoundError(f"YAML suite bulunamadı: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise _fail(path, f"YAML sözdizimi hatası: {e}") from e
    if not isinstance(data, dict):
        raise _fail(path, "üst düzey dict olmalı")
    tasks = data.get("tasks", data)
    if not isinstance(tasks, list) or not tasks:
        raise _fail(path, "'tasks' boş olmayan liste olmalı")
    out: list[dict] = []
    seen: set[str] = set()
    for raw in tasks:
        task = validate_task(raw, path)
        tid = str(task["id"])
        if tid in seen:
            raise _fail(path, f"yinelenen görev id: {tid}")
        seen.add(tid)
        out.append(task)
    return out


def list_yaml_suites(tasks_dir: Path) -> list[str]:
    """tasks/ dizinindeki *.yaml suite adları."""
    if not tasks_dir.is_dir():
        return []
    return sorted(p.stem for p in tasks_dir.glob("*.yaml"))


SAMPLE_YAML = """\
# BenchCompass deklaratif eval suite'i (Adım 6) — tasks/ altına koyun.
name: ornek
tasks:
  - id: ar1_ornek
    type: num
    lang: tr
    difficulty: kolay
    category: aritmetik
    prompt: "17 ile 23'ün çarpımı kaçtır? Yalnızca sayıyı yaz."
    expected: "391"
  - id: soz1_ornek
    type: word
    lang: tr
    difficulty: kolay
    category: genel
    prompt: "Türkiye'nin başkenti neresidir? Tek kelimeyle yaz."
    expected: "ankara"
"""
