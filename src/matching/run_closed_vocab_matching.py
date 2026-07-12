"""
Closed-vocabulary Entity Matching - 전체 데이터셋 실행

[Design Change] Gold Standard를 Gold Transcript 추출 결과 대신
Content Scaffold로 사용한다 (사유: scaffold_as_gold.py 참고).
"""

import json
from pathlib import Path

import yaml

from src.matching.entity_matcher import match_closed_vocab
from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab


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


def run_matching(entities_dir: str, scenarios_dir: str):
    entities_path = Path(entities_dir)
    scaffolds = load_scaffolds(scenarios_dir)

    closed_files = sorted(entities_path.glob("*_closed.json"))

    count = 0
    for f in closed_files:
        data = json.load(open(f, encoding="utf-8"))
        sample_id = data["sample_id"]
        scenario_id = "_".join(sample_id.split("_")[:2])

        if scenario_id not in scaffolds:
            print(f"경고: {scenario_id}에 대한 Scaffold 없음, 건너뜀")
            continue

        gold_entities = scaffold_to_closed_vocab(scaffolds[scenario_id])
        whisper_entities = data["whisper_entities"]

        matches = match_closed_vocab(gold_entities, whisper_entities)

        matched_file = entities_path / f"{sample_id}_matched.json"
        if matched_file.exists():
            combined = json.load(open(matched_file, encoding="utf-8"))
        else:
            combined = {"sample_id": sample_id}

        combined["closed_vocab_matches"] = matches

        with open(matched_file, "w", encoding="utf-8") as fh:
            json.dump(combined, fh, ensure_ascii=False, indent=2)

        count += 1
        print(f"[{count}] {sample_id} -> {matched_file}")

    print(f"\n총 {count}개 샘플에 대해 Closed-vocabulary Matching 완료 (Gold=Scaffold 기준) -> {entities_dir}")


if __name__ == "__main__":
    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    scenarios_dir = config["paths"]["scenarios_dir"]
    run_matching(entities_dir, scenarios_dir)