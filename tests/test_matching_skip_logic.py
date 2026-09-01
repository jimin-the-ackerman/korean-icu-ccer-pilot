"""
run_closed_vocab_matching.py / run_semantic_matching.py의 skip-by-default
안전장치 검증 (API 미호출, 파일 I/O만 임시 디렉토리에서 확인).

목적: 5->50 확장 시 이미 매칭이 끝난 scenario_001~005의 closed_vocab_matches/
open_vocab_matches가 --overwrite 없이는 절대 재계산(=변경 위험)되지 않는지 확인.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.matching.run_closed_vocab_matching import run_matching as run_closed_matching


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _make_scaffold(scenario_id="scenario_001"):
    return {
        "scenario_id": scenario_id,
        "vital_signs": {"BP": "120/80", "HR": "80", "RR": "16", "BT": "36.5", "SpO2": "98%"},
        "symptom": {"name": "cough", "negation": False, "severity": "mild"},
        "medication": {"name": "Aspirin", "dose": "100mg", "route": "PO", "frequency": "BID"},
        "oxygen_support": None, "intervention": None, "device": None, "io": None,
        "clinical_status": "alert", "notification": None,
    }


def test_closed_vocab_matching_skips_when_already_matched():
    """closed_vocab_matches가 이미 있으면 --overwrite 없이는 절대 안 건드림."""
    with tempfile.TemporaryDirectory() as tmpdir:
        entities_dir = Path(tmpdir) / "entities"
        scenarios_dir = Path(tmpdir) / "scenarios"
        entities_dir.mkdir()
        scenarios_dir.mkdir()

        _write_json(scenarios_dir / "scenario_001.json", _make_scaffold())
        _write_json(entities_dir / "scenario_001_style_closed.json", {
            "sample_id": "scenario_001_style",
            "whisper_entities": {"route": [], "frequency": [], "device": [], "vital_sign": [], "dose": []},
        })
        original_marker = {"already_here": True}
        _write_json(entities_dir / "scenario_001_style_matched.json", {
            "sample_id": "scenario_001_style",
            "closed_vocab_matches": original_marker,
        })

        run_log = run_closed_matching(str(entities_dir), str(scenarios_dir), overwrite=False)

        result = json.load(open(entities_dir / "scenario_001_style_matched.json", encoding="utf-8"))
        assert result["closed_vocab_matches"] == original_marker  # 절대 안 바뀜
        assert run_log.summary()["skipped"] == ["scenario_001_style"]
        assert run_log.summary()["processed"] == []


def test_closed_vocab_matching_overwrite_forces_recompute():
    """--overwrite(=overwrite=True)면 재계산해서 실제로 값이 갱신됨."""
    with tempfile.TemporaryDirectory() as tmpdir:
        entities_dir = Path(tmpdir) / "entities"
        scenarios_dir = Path(tmpdir) / "scenarios"
        entities_dir.mkdir()
        scenarios_dir.mkdir()

        _write_json(scenarios_dir / "scenario_001.json", _make_scaffold())
        _write_json(entities_dir / "scenario_001_style_closed.json", {
            "sample_id": "scenario_001_style",
            "whisper_entities": {"route": [], "frequency": [], "device": [], "vital_sign": [], "dose": []},
        })
        _write_json(entities_dir / "scenario_001_style_matched.json", {
            "sample_id": "scenario_001_style",
            "closed_vocab_matches": {"stale": True},
        })

        run_log = run_closed_matching(str(entities_dir), str(scenarios_dir), overwrite=True)

        result = json.load(open(entities_dir / "scenario_001_style_matched.json", encoding="utf-8"))
        assert result["closed_vocab_matches"] != {"stale": True}  # 재계산되어 값이 바뀜
        assert run_log.summary()["processed"] == ["scenario_001_style"]


def test_closed_vocab_matching_processes_new_scenario_without_touching_existing():
    """5->50 확장 시나리오 재현: scenario_001(기존, 매칭 완료)은 건드리지 않고
    scenario_006(신규, 미매칭)만 처리되는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        entities_dir = Path(tmpdir) / "entities"
        scenarios_dir = Path(tmpdir) / "scenarios"
        entities_dir.mkdir()
        scenarios_dir.mkdir()

        for sid in ["scenario_001", "scenario_006"]:
            _write_json(scenarios_dir / f"{sid}.json", _make_scaffold(sid))
            _write_json(entities_dir / f"{sid}_style_closed.json", {
                "sample_id": f"{sid}_style",
                "whisper_entities": {"route": [], "frequency": [], "device": [], "vital_sign": [], "dose": []},
            })

        # scenario_001만 이미 매칭 완료 상태로 세팅
        preserved = {"preserved_marker": "scenario_001_original_result"}
        _write_json(entities_dir / "scenario_001_style_matched.json", {
            "sample_id": "scenario_001_style", "closed_vocab_matches": preserved,
        })

        run_log = run_closed_matching(str(entities_dir), str(scenarios_dir), overwrite=False)

        result_001 = json.load(open(entities_dir / "scenario_001_style_matched.json", encoding="utf-8"))
        assert result_001["closed_vocab_matches"] == preserved  # 기존 것 보존

        result_006 = json.load(open(entities_dir / "scenario_006_style_matched.json", encoding="utf-8"))
        assert "closed_vocab_matches" in result_006  # 신규는 새로 생성됨

        summary = run_log.summary()
        assert "scenario_001_style" in summary["skipped"]
        assert "scenario_006_style" in summary["processed"]


def test_semantic_matching_skip_logic_uses_open_vocab_matches_key():
    """run_semantic_matching.py도 동일한 키 존재 기반 skip 로직을 쓰는지
    (open_vocab_matches 키), API 호출 없이 로직 함수 시그니처/동작만 정적 확인."""
    import inspect
    from src.matching.run_semantic_matching import run_matching as run_semantic_matching
    src = inspect.getsource(run_semantic_matching)
    assert 'combined.get("open_vocab_matches")' in src
    assert "overwrite" in src


if __name__ == "__main__":
    test_closed_vocab_matching_skips_when_already_matched()
    test_closed_vocab_matching_overwrite_forces_recompute()
    test_closed_vocab_matching_processes_new_scenario_without_touching_existing()
    test_semantic_matching_skip_logic_uses_open_vocab_matches_key()
    print("All matching skip-logic tests passed.")
