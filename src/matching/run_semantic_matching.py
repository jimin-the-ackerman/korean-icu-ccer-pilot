"""
Open-vocabulary Semantic Matching - 전체 데이터셋 실행

[Design Change] Gold Standard를 Gold Transcript 추출 결과 대신
Content Scaffold로 사용한다 (사유: scaffold_as_gold.py 참고).
"""

import json
import os
import time
from pathlib import Path

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from src.matching.semantic_matcher import match_open_vocab, is_valid_match_result
from src.entity_extraction.scaffold_as_gold import scaffold_to_open_vocab

load_dotenv()

MAX_RETRIES = 3


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scaffolds(scenarios_dir: str) -> dict:
    scaffolds = {}
    for f in Path(scenarios_dir).glob("scenario_*.json"):
        if f.name == "generation_log.json":
            continue
        data = json.load(open(f, encoding="utf-8"))
        scaffolds[data["scenario_id"]] = data
    return scaffolds


def match_with_retry(client, model, gold_entities, whisper_entities, sample_id):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = match_open_vocab(client, model, gold_entities, whisper_entities)
        except Exception as e:
            print(f"  재시도 {attempt}/{MAX_RETRIES}: API 오류 {e}")
            time.sleep(1)
            continue

        if is_valid_match_result(result):
            return result

        print(f"  재시도 {attempt}/{MAX_RETRIES}: 응답 구조 검증 실패")
        time.sleep(1)

    raise RuntimeError(f"MAX_RETRIES 초과 ({sample_id})")


def run_matching(entities_dir: str, scenarios_dir: str, model: str):
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    entities_path = Path(entities_dir)
    scaffolds = load_scaffolds(scenarios_dir)

    open_files = sorted(entities_path.glob("*_open.json"))

    count = 0
    for f in open_files:
        data = json.load(open(f, encoding="utf-8"))
        sample_id = data["sample_id"]
        scenario_id = "_".join(sample_id.split("_")[:2])

        if scenario_id not in scaffolds:
            print(f"경고: {scenario_id}에 대한 Scaffold 없음, 건너뜀")
            continue

        count += 1
        print(f"[{count}/{len(open_files)}] {sample_id} 매칭 중...")

        gold_entities = scaffold_to_open_vocab(scaffolds[scenario_id])
        whisper_entities = data["whisper_entities"]

        try:
            match_result = match_with_retry(client, model, gold_entities, whisper_entities, sample_id)
        except RuntimeError as e:
            print(f"  실패, 건너뜀: {e}")
            continue

        matched_file = entities_path / f"{sample_id}_matched.json"
        if matched_file.exists():
            combined = json.load(open(matched_file, encoding="utf-8"))
        else:
            combined = {"sample_id": sample_id}

        combined["open_vocab_matches"] = match_result

        with open(matched_file, "w", encoding="utf-8") as fh:
            json.dump(combined, fh, ensure_ascii=False, indent=2)

        print(f"  생성됨: {matched_file}")

    print(f"\n총 {count}개 샘플에 대해 Open-vocabulary Matching 완료 (Gold=Scaffold 기준) -> {entities_dir}")


if __name__ == "__main__":
    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    scenarios_dir = config["paths"]["scenarios_dir"]
    model = config["entity_extraction"]["claude_model"]

    run_matching(entities_dir, scenarios_dir, model)