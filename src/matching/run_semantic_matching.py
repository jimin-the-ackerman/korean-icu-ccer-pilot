"""
Open-vocabulary Semantic Matching - 전체 데이터셋 실행 

Pipeline:
data/entities/{sample_id}_open.json
    -> match_open_vocab() (Claude)
    -> data/entities/{sample_id}_matched.json (open_vocab_matches 키로 병합 저장)
"""

import json
import os
import time
from pathlib import Path

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from src.matching.semantic_matcher import match_open_vocab, is_valid_match_result

load_dotenv()

MAX_RETRIES = 3


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def run_matching(entities_dir: str, model: str):
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    entities_path = Path(entities_dir)
    open_files = sorted(entities_path.glob("*_open.json"))

    count = 0
    for f in open_files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        sample_id = data["sample_id"]
        count += 1
        print(f"[{count}/{len(open_files)}] {sample_id} 매칭 중...")

        try:
            match_result = match_with_retry(
                client, model, data["gold_entities"], data["whisper_entities"], sample_id
            )
        except RuntimeError as e:
            print(f"  실패, 건너뜀: {e}")
            continue

        matched_file = entities_path / f"{sample_id}_matched.json"
        if matched_file.exists():
            with open(matched_file, "r", encoding="utf-8") as fh:
                combined = json.load(fh)
        else:
            combined = {"sample_id": sample_id}

        combined["open_vocab_matches"] = match_result

        with open(matched_file, "w", encoding="utf-8") as fh:
            json.dump(combined, fh, ensure_ascii=False, indent=2)

        print(f"  생성됨: {matched_file}")

    print(f"\n총 {count}개 샘플에 대해 Open-vocabulary Matching 완료 -> {entities_dir}")


if __name__ == "__main__":
    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    model = config["entity_extraction"]["claude_model"]

    run_matching(entities_dir, model)