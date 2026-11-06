"""
Unit testler — api/tasks.py (background task framework)
==========================================================================
Thread + SQLite tabanlı arka plan görev yönetimi.

AGENTS.md §6: DB'ye gerçek bağlanır ama tmp_root altında izole SQLite olmalı
(gerçek benchmark_history.db'ye DOKUNULMAZ). create_task thread başlatır —
testte thread tamamlanana kadar beklenir (join).
"""

from __future__ import annotations

import time

import pytest

from api import db as dbmod
from api import tasks as tasks_mod


@pytest.fixture(autouse=True)
def reset_tasks_state():
    """Her test öncesi bellek içi _tasks sözlüğünü temizle (izolasyon)."""
    tasks_mod._tasks.clear()
    yield
    tasks_mod._tasks.clear()


def _wait_task_done(task_uuid: str, timeout: float = 2.0) -> None:
    """Task tamamlanana kadar bekle (thread senkronizasyonu).

    AGENTS.md §6: time.sleep YASAK (E2E'de) — ama unit testte thread join
    için kısa polling kabul edilebilir (gerçek waiter değil, test senkronu).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = tasks_mod.get_task(task_uuid)
        if task and task.get("status") in ("completed", "failed"):
            return
        time.sleep(0.01)


# =============================================================================
# create_task — başarı yolu
# =============================================================================
class TestCreateTask:
    def test_create_returns_uuid(self):
        """create_task geçerli bir UUID döner."""

        def dummy():
            return {"done": True}

        task_uuid = tasks_mod.create_task("test-type", dummy)
        _wait_task_done(task_uuid)

        assert isinstance(task_uuid, str)
        assert len(task_uuid) > 0

    def test_task_completes_successfully(self):
        """Başarılı task → status='completed', result dolu."""

        def dummy():
            return {"value": 42}

        task_uuid = tasks_mod.create_task("success-test", dummy)
        _wait_task_done(task_uuid)

        task = tasks_mod.get_task(task_uuid)
        assert task is not None
        assert task["status"] == "completed"
        assert task["progress"] == 100

    def test_task_with_kwargs(self):
        """create_task kwargs'ı fn'e geçirir."""

        def adder(a, b):
            return {"sum": a + b}

        task_uuid = tasks_mod.create_task("adder", adder, a=3, b=4)
        _wait_task_done(task_uuid)

        task = tasks_mod.get_task(task_uuid)
        assert task["status"] == "completed"


# =============================================================================
# create_task — hata yolu
# =============================================================================
class TestCreateTaskFailure:
    def test_failing_task_marked_failed(self):
        """Exception fırlatan task → status='failed', error dolu."""

        def boom():
            raise ValueError("test hatası")

        task_uuid = tasks_mod.create_task("fail-test", boom)
        _wait_task_done(task_uuid)

        task = tasks_mod.get_task(task_uuid)
        assert task is not None
        assert task["status"] == "failed"
        assert "test hatası" in task["error"]


# =============================================================================
# get_task
# =============================================================================
class TestGetTask:
    def test_get_existing_task(self):
        """Var olan task UUID'si ile task döner."""

        def dummy():
            return {"x": 1}

        task_uuid = tasks_mod.create_task("get-test", dummy)
        _wait_task_done(task_uuid)

        task = tasks_mod.get_task(task_uuid)
        assert task is not None
        assert task["uuid"] == task_uuid

    def test_get_nonexistent_returns_none(self):
        """Olmayan UUID → None (fırlatma yapmaz)."""
        result = tasks_mod.get_task("nonexistent-uuid-12345")
        assert result is None


# =============================================================================
# list_tasks
# =============================================================================
class TestListTasks:
    def test_list_returns_list(self):
        """list_tasks liste döner."""
        result = tasks_mod.list_tasks(limit=5)
        assert isinstance(result, list)

    def test_list_respects_limit(self):
        """limit parametresi dönen öğe sayısını sınırlar."""
        result = tasks_mod.list_tasks(limit=3)
        assert len(result) <= 3


# =============================================================================
# update_task & pass_task_uuid
# =============================================================================
class TestUpdateTask:
    def test_pass_task_uuid_and_update_task(self):
        """pass_task_uuid=True ile task_uuid fonksiyona iletilir ve update_task progress günceller."""

        def worker(task_uuid=""):
            tasks_mod.update_task(task_uuid, progress=45, detail="indiriliyor")
            return {"ok": True}

        task_uuid = tasks_mod.create_task("pull-test", worker, pass_task_uuid=True)
        _wait_task_done(task_uuid)

        task = tasks_mod.get_task(task_uuid)
        assert task["status"] == "completed"
        assert task["result"] == {"ok": True}

    def test_update_task_writes_progress_to_db(self):
        """update_task progress'i DB'ye de yazar (backend restart dayanıklılığı).

        Bellek kaydı düşürülüp DB fallback okuması yapıldığında progress
        görünmelidir — önceden yalnızca bellekte güncellendiği için restart
        sonrası görev yüzde 0'da takılı kalıyordu.
        """
        task_uuid = tasks_mod.create_task("db-prog", lambda: {"ok": 1})
        _wait_task_done(task_uuid)

        tasks_mod.update_task(task_uuid, progress=55)

        tasks_mod._tasks.pop(
            task_uuid, None
        )  # belleği simüle edilmiş restart ile düşür
        task = tasks_mod.get_task(task_uuid)
        assert task is not None
        assert task["progress"] == 55

    def test_update_task_without_fields_is_db_noop(self):
        """progress/status verilmeden update_task DB'ye dokunmaz ve patlamaz."""
        task_uuid = tasks_mod.create_task("noop", lambda: None)
        _wait_task_done(task_uuid)

        tasks_mod.update_task(task_uuid)  # sadece detail verilmiş gibi davranmasın

        task = tasks_mod.get_task(task_uuid)
        assert task["status"] == "completed"


# =============================================================================
# reap_orphan_tasks — backend restart kurtarma (denetim kapanışı)
# =============================================================================
class TestReapOrphanTasks:
    def test_reap_marks_pending_running_failed(self):
        """Restart'ta ölen pending/running satırları failed olur; completed'e dokunmaz."""
        con = dbmod.connect()
        con.execute(
            "INSERT INTO background_tasks(uuid,type,status) VALUES(?,?,?)",
            ("orphan-running-1", "t", "running"),
        )
        con.execute(
            "INSERT INTO background_tasks(uuid,type,status) VALUES(?,?,?)",
            ("orphan-pending-1", "t", "pending"),
        )
        con.execute(
            "INSERT INTO background_tasks(uuid,type,status) VALUES(?,?,?)",
            ("done-completed-1", "t", "completed"),
        )
        con.commit()
        con.close()

        reaped = tasks_mod.reap_orphan_tasks()
        assert reaped >= 2

        tasks_mod._tasks.clear()  # DB fallback üzerinden oku
        running = tasks_mod.get_task("orphan-running-1")
        assert running is not None
        assert running["status"] == "failed"
        assert "yeniden başlatıldı" in running["error"]
        pending = tasks_mod.get_task("orphan-pending-1")
        assert pending is not None
        assert pending["status"] == "failed"
        completed = tasks_mod.get_task("done-completed-1")
        assert completed is not None
        assert completed["status"] == "completed"

    def test_reap_with_no_orphans_returns_zero(self):
        """Yetim satır yoksa 0 döner (temiz başlangıç)."""
        assert tasks_mod.reap_orphan_tasks() == 0
