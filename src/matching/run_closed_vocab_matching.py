"""
Closed-vocabulary Entity Matching - 전체 데이터셋 실행

[Design Change] Gold Standard를 Gold Transcript 추출 결과 대신
Content Scaffold로 사용한다 (사유: scaffold_as_gold.py 참고).

[안전장치] 이 스크립트의 output은 *_matched.json 파일 자체가 아니라 그 안의
"closed_vocab_matches" 키다. 이미 이 키가 채워진 샘플은 기본적으로 건너뛴다
(--overwrite로 강제 재실행 가능) — src/pipeline_utils.py 참고. 이 매칭
로직 자체는 결정론적(규칙 기반)이라 재실행해도 값이 바뀌진 않지만, 50개
확장 시 이미 끝난 5개 시나리오를 불필요하게 다시 계산하지 않기 위해 다른
파이프라인 단계와 동일한 skip 패턴을 적용한다.
"""

import json
from pathlib import Path

import yaml

from src.matching.entity_matcher import match_closed_vocab
from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab
from src.pipeline_utils import RunLog, add_overwrite_arg


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scaffolds(scenarios_dir: str) -> dict:
    """scenario_id -> scaffold dict"""
    scaffolds = {}
    for f in Path(scenarios_dir).glob("scenario_*.json"):
        if f.name == "generation_log.json":
            continue
        data = json.load(open(f, encoding="utf-8"))
        scaffolds[data["scenario_id"]] = data
    return scaffolds


def run_matching(entities_dir: str, scenarios_dir: str, overwrite: bool = False):
    entities_path = Path(entities_dir)
    scaffolds = load_scaffolds(scenarios_dir)

    closed_files = sorted(entities_path.glob("*_closed.json"))
    run_log = RunLog()

    for f in closed_files:
        data = json.load(open(f, encoding="utf-8"))
        sample_id = data["sample_id"]
        scenario_id = "_".join(sample_id.split("_")[:2])

        if scenario_id not in scaffolds:
            print(f"경고: {scenario_id}에 대한 Scaffold 없음, 건너뜀")
            run_log.record(sample_id, "failed", error="scaffold missing")
            continue

        matched_file = entities_path / f"{sample_id}_matched.json"
        if matched_file.exists():
            combined = json.load(open(matched_file, encoding="utf-8"))
        else:
            combined = {"sample_id": sample_id}

        if combined.get("closed_vocab_matches") is not None and not overwrite:
            print(f"{sample_id} closed_vocab_matches 이미 존재, 건너뜀 (--overwrite로 재생성 가능)")
            run_log.record(sample_id, "skipped")
            continue

        gold_entities = scaffold_to_closed_vocab(scaffolds[scenario_id])
        whisper_entities = data["whisper_entities"]

        matches = match_closed_vocab(gold_entities, whisper_entities)
        combined["closed_vocab_matches"] = matches

        with open(matched_file, "w", encoding="utf-8") as fh:
            json.dump(combined, fh, ensure_ascii=False, indent=2)

        run_log.record(sample_id, "processed")
        print(f"[{len(run_log.entries)}] {sample_id} -> {matched_file}")

    run_log.print_summary()
    log_path = run_log.save(entities_path, "closed_vocab_matching_log.json")
    print(f"Closed-vocabulary Matching 완료 (Gold=Scaffold 기준) -> {entities_dir}")
    print(f"실행 로그 저장: {log_path}")
    return run_log


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    add_overwrite_arg(parser)
    args = parser.parse_args()

    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    scenarios_dir = config["paths"]["scenarios_dir"]
    run_matching(entities_dir, scenarios_dir, overwrite=args.overwrite)