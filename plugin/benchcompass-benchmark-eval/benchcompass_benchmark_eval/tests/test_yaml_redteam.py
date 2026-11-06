"""YAML suite + red-team testleri (Adım 6, ADR-0017). Network yok."""

from __future__ import annotations

import pytest

from benchcompass_benchmark_eval import grading, redteam, yaml_spec


def test_redteam_plan_publishes_six_tasks():
    tasks = redteam.public_tasks()
    assert len(tasks) == 6
    ids = {t["id"] for t in tasks}
    assert {"rt_ignore", "rt_dan", "rt_zararlı_talimat"} <= ids


def test_redteam_grade_refusal_passes():
    task = redteam.find_task("rt_dan")
    assert task is not None
    res = redteam.grade_redteam(task, "Sorry, I cannot help with that.")
    assert res["pass"] is True


def test_redteam_grade_no_refusal_fails():
    task = redteam.find_task("rt_dan")
    assert task is not None
    res = redteam.grade_redteam(task, "DAN mode unlocked, no limits:")
    assert res["pass"] is False
    assert res["reason"] == "reddetme yok"


def test_redteam_grade_harmful_fails_even_with_wordy_reply():
    task = redteam.find_task("rt_zararlı_talimat")
    assert task is not None
    res = redteam.grade_redteam(task, "Adım 1: önce malzemeleri karıştır.")
    assert res["pass"] is False


def test_redteam_grade_info_question_passes_without_marker():
    task = redteam.find_task("rt_kod_enjeksiyon")
    assert task is not None
    res = redteam.grade_redteam(task, "It's a SQL statement that deletes rows.")
    assert res["pass"] is True


def test_yaml_sample_loads_and_grades(tmp_path):
    path = tmp_path / "ornek.yaml"
    path.write_text(yaml_spec.SAMPLE_YAML, encoding="utf-8")
    tasks = yaml_spec.load_yaml_suite(path)
    assert len(tasks) == 2
    assert grading.grade_task(tasks[0], "391") is True
    assert grading.grade_task(tasks[1], "Ankara") is True


def test_yaml_bundled_redteam_suite_loads():
    path = (
        __import__("pathlib").Path(yaml_spec.__file__).parent
        / "tasks"
        / "suite_redteam.yaml"
    )
    tasks = yaml_spec.load_yaml_suite(path)
    by_id = {t["id"]: t for t in tasks}
    assert "rt_ignore" in by_id
    assert grading.grade_task(by_id["ar_ornek"], "391") is True


def test_yaml_invalid_schema_rejected(tmp_path):
    path = tmp_path / "kotu.yaml"
    path.write_text(
        "name: kotu\ntasks:\n  - id: x\n    type: num\n    prompt: p\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected"):
        yaml_spec.load_yaml_suite(path)


def test_yaml_duplicate_ids_rejected(tmp_path):
    path = tmp_path / "dup.yaml"
    path.write_text(
        "name: d\ntasks:\n"
        "  - {id: a, type: num, prompt: p, expected: '1'}\n"
        "  - {id: a, type: num, prompt: p, expected: '2'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="yinelenen"):
        yaml_spec.load_yaml_suite(path)


def test_yaml_syntax_error_is_value_error(tmp_path):
    path = tmp_path / "bozuk.yaml"
    path.write_text("name: [unclosed\n  tasks: {", encoding="utf-8")
    with pytest.raises(ValueError, match="sözdizimi"):
        yaml_spec.load_yaml_suite(path)


def test_yaml_missing_file_is_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        yaml_spec.load_yaml_suite(tmp_path / "yok.yaml")
