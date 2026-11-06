"""Sprint 9: Async background task framework.

Uzun suren islemler (benchmark, download, run) icin merkezi task yonetimi.
Her task UUID alir, background_tasks tablosunda durum kaydi tutulur.
Frontend /api/tasks/<uuid> ile polling yapar.

Kullanici tercihi (Sprint 8 giris):
  - Async + polling: background task + UUID + durum tablosu + frontend polling
  - Detayli hata + toast: hata detayi UI'da gosterilir
  - Mock veri: gercek llmfit komutlari calistirilmaz, placeholder veri doner
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from . import db as dbmod

# Bellek ici task kaydi (backend tarafindan goruntulemek icin)
_tasks: dict[str, dict] = {}


def create_task(
    task_type: str,
    background_fn: Callable[..., Any],
    pass_task_uuid: bool = False,
    **kwargs: Any,
) -> str:
    """Yeni bir background task olusturur.

    Args:
        task_type: 'benchmark' | 'download' | 'run_model' | 'hf_search' | 'ollama_pull'
        background_fn: arka planda calistirilacak fonksiyon
        pass_task_uuid: True ise task_uuid fonksiyona kwargs olarak iletilir
        **kwargs: fonksiyona gonderilecek argumanlar

    Returns:
        task_uuid: polling icin uuid
    """
    task_uuid = str(uuid.uuid4())
    task = {
        "uuid": task_uuid,
        "type": task_type,
        "status": "pending",
        "progress": 0,
        "detail": None,
        "result": None,
        "error": None,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
    }
    _tasks[task_uuid] = task

    # DB'ye yaz
    con = dbmod.connect()
    try:
        con.execute(
            "INSERT INTO background_tasks(uuid,type,status) VALUES(?,?,?)",
            (task_uuid, task_type, "pending"),
        )
        con.commit()
    finally:
        con.close()

    call_kwargs = dict(kwargs)
    if pass_task_uuid:
        call_kwargs["_pass_task_uuid"] = True

    # Thread'de baslat
    thread = threading.Thread(
        target=_run_task,
        args=(task_uuid, background_fn),
        kwargs=call_kwargs,
        daemon=True,
    )
    thread.start()

    return task_uuid


def update_task(
    task_uuid: str,
    *,
    progress: int | None = None,
    detail: str | None = None,
    status: str | None = None,
) -> None:
    """Task durumunu günceller: bellek içi kayıt + DB (progress/status).

    Yeniden başlatma dayanıklılığı (denetim kapanışı): ``background_tasks``
    tablosundaki ``progress`` kolonu (SCHEMA_SPRINT9) zaten mevcut olduğundan
    ara ilerleme de kalıcıdır — backend yeniden başlasa bile görev yüzdesi
    kaybolmaz. ``detail`` yalnızca bellekte yaşar (DB kolonu yok; eklenmesi
    migration, yani insan onayı ister — AGENTS.md §9.3).
    """
    task = _tasks.get(task_uuid)
    if task:
        if progress is not None:
            task["progress"] = progress
        if detail is not None:
            task["detail"] = detail
        if status is not None:
            task["status"] = status

    # DB tarafı: yalnızca verilmiş alanları güncelle (kolonlar mevcut, migration yok).
    sets: list[str] = []
    params: list[Any] = []
    if progress is not None:
        sets.append("progress=?")
        params.append(int(progress))
    if status is not None:
        sets.append("status=?")
        params.append(status)
    if not sets:
        return
    params.append(task_uuid)
    con = dbmod.connect()
    try:
        con.execute(
            f"UPDATE background_tasks SET {', '.join(sets)} WHERE uuid=?",
            tuple(params),
        )
        con.commit()
    finally:
        con.close()


def _run_task(task_uuid: str, fn: Callable[..., Any], **kwargs: Any) -> None:
    """Task'i arka planda calistirir, sonucu gunceller."""
    task = _tasks.get(task_uuid)
    if not task:
        return
    task["status"] = "running"

    pass_uuid = kwargs.pop("_pass_task_uuid", False)

    con = dbmod.connect()
    try:
        con.execute(
            "UPDATE background_tasks SET status='running' WHERE uuid=?", (task_uuid,)
        )
        con.commit()
    finally:
        con.close()

    try:
        if pass_uuid:
            result = fn(task_uuid=task_uuid, **kwargs)
        else:
            result = fn(**kwargs)
        task["status"] = "completed"
        task["progress"] = 100
        task["result"] = result
        con = dbmod.connect()
        try:
            con.execute(
                "UPDATE background_tasks SET status='completed', progress=100,"
                " result=? WHERE uuid=?",
                (json.dumps(result, ensure_ascii=False, default=str), task_uuid),
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        con = dbmod.connect()
        try:
            con.execute(
                "UPDATE background_tasks SET status='failed', error=? WHERE uuid=?",
                (str(e), task_uuid),
            )
            con.commit()
        finally:
            con.close()


def get_task(task_uuid: str) -> dict | None:
    """Task durumunu dondurur (once bellek ici, sonra DB)."""
    if task_uuid in _tasks:
        return _tasks[task_uuid]
    con = dbmod.connect()
    try:
        row = con.execute(
            "SELECT * FROM background_tasks WHERE uuid=? ORDER BY id DESC LIMIT 1",
            (task_uuid,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def reap_orphan_tasks() -> int:
    """Yeniden başlatmada ölü (pending/running) görev satırlarını failed yapar.

    Task'ler daemon thread'de koşar: backend yeniden başlarsa thread'ler ölür
    ama DB satırları ``pending``/``running`` kalır ve frontend sonsuza kadar
    poll eder. Bu fonksiyon lifespan sırasında çağrılır ve bu yetim satırları
    dürüstçe ``failed`` olarak işaretler. Dönen değer güncellenen satır sayısıdır.
    """
    con = dbmod.connect()
    try:
        cur = con.execute(
            "UPDATE background_tasks SET status='failed',"
            " error='backend yeniden başlatıldı — görev yarıda kesildi'"
            " WHERE status IN ('pending','running')"
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def list_tasks(limit: int = 20) -> list[dict]:
    """Son task'leri listeler."""
    con = dbmod.connect()
    try:
        rows = con.execute(
            "SELECT * FROM background_tasks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()
