"""
Closed-vocabulary Entity Matching - 전체 데이터셋 실행

Pipeline:
data/entities/{sample_id}_closed.json
    -> match_closed_vocab()
    -> data/entities/{sample_id}_matched.json (closed_vocab_matches 키로 저장)
"""

import json
from pathlib import Path

import yaml

from src.matching.entity_matcher import match_closed_vocab


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_matching(entities_dir: str):
    entities_path = Path(entities_dir)
    closed_files = sorted(entities_path.glob("*_closed.json"))

    count = 0
    for f in closed_files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        sample_id = data["sample_id"]
        matches = match_closed_vocab(data["gold_entities"], data["whisper_entities"])

        matched_file = entities_path / f"{sample_id}_matched.json"

        if matched_file.exists():
            with open(matched_file, "r", encoding="utf-8") as fh:
                combined = json.load(fh)
        else:
            combined = {"sample_id": sample_id}

        combined["closed_vocab_matches"] = matches

        with open(matched_file, "w", encoding="utf-8") as fh:
            json.dump(combined, fh, ensure_ascii=False, indent=2)

        count += 1
        print(f"[{count}] {sample_id} -> {matched_file}")

    print(f"\n총 {count}개 샘플에 대해 Closed-vocabulary Matching 완료 -> {entities_dir}")


if __name__ == "__main__":
    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    run_matching(entities_dir)