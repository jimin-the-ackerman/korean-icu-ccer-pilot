"""pipeline_utils.py 단위 테스트 (API 미호출, 순수 로직)."""

import argparse
import json
import tempfile
from pathlib import Path

import pytest

from src.pipeline_utils import RunLog, add_overwrite_arg, should_skip


def test_run_log_records_valid_statuses():
    log = RunLog()
    log.record("scenario_001", "skipped")
    log.record("scenario_006", "processed", model="gpt-4o")
    log.record("scenario_007", "failed", error="timeout")
    assert len(log.entries) == 3
    assert log.entries[1]["model"] == "gpt-4o"
    assert log.entries[2]["error"] == "timeout"


def test_run_log_rejects_invalid_status():
    log = RunLog()
    with pytest.raises(ValueError):
        log.record("scenario_001", "success")  # "processed"가 맞는 값


def test_run_log_summary_groups_by_status():
    log = RunLog()
    log.record("scenario_001", "skipped")
    log.record("scenario_002", "skipped")
    log.record("scenario_006", "processed")
    log.record("scenario_007", "failed")
    summary = log.summary()
    assert summary["skipped"] == ["scenario_001", "scenario_002"]
    assert summary["processed"] == ["scenario_006"]
    assert summary["failed"] == ["scenario_007"]


def test_run_log_save_writes_entries_and_summary():
    log = RunLog()
    log.record("scenario_001", "skipped")
    log.record("scenario_006", "processed")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = log.save(tmpdir, "test_log.json")
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        assert len(payload["entries"]) == 2
        assert payload["summary"]["skipped"] == ["scenario_001"]
        assert payload["summary"]["processed"] == ["scenario_006"]


def test_should_skip_true_when_exists_and_not_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "scenario_001.json"
        f.write_text("{}")
        assert should_skip(f, overwrite=False) is True


def test_should_skip_false_when_exists_and_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "scenario_001.json"
        f.write_text("{}")
        assert should_skip(f, overwrite=True) is False


def test_should_skip_false_when_not_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "scenario_999.json"  # 존재하지 않음
        assert should_skip(f, overwrite=False) is False


def test_add_overwrite_arg_defaults_to_false():
    parser = argparse.ArgumentParser()
    add_overwrite_arg(parser)
    args = parser.parse_args([])
    assert args.overwrite is False


def test_add_overwrite_arg_true_when_flag_passed():
    parser = argparse.ArgumentParser()
    add_overwrite_arg(parser)
    args = parser.parse_args(["--overwrite"])
    assert args.overwrite is True


def test_add_overwrite_arg_force_alias_works():
    """--force도 --overwrite와 동일하게 동작해야 함."""
    parser = argparse.ArgumentParser()
    add_overwrite_arg(parser)
    args = parser.parse_args(["--force"])
    assert args.overwrite is True


if __name__ == "__main__":
    test_run_log_records_valid_statuses()
    test_run_log_summary_groups_by_status()
    test_run_log_save_writes_entries_and_summary()
    test_should_skip_true_when_exists_and_not_overwrite()
    test_should_skip_false_when_exists_and_overwrite()
    test_should_skip_false_when_not_exists()
    test_add_overwrite_arg_defaults_to_false()
    test_add_overwrite_arg_true_when_flag_passed()
    test_add_overwrite_arg_force_alias_works()
    print("All pipeline_utils tests passed (test_run_log_rejects_invalid_status requires pytest).")
