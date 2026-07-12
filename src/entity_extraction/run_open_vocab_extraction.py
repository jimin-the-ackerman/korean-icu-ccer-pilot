"""
Open-vocabulary Entity Extraction — 전체

Pipeline:
data/generated_text/{sample_id}.json  (Gold Transcript)
data/stt_transcripts/{sample_id}.json (Whisper Transcript)
    -> Claude Structured Extraction, 각각 독립적으로 수행
    -> data/entities/{sample_id}_open.json
"""

import json
import os
import time
from pathlib import Path

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from src.entity_extraction.open_vocab_extractor import extract_open_vocab_entities

load_dotenv()

MAX_RETRIES = 3

def is_valid_extraction(result: dict) -> bool:
    """
    Claude 응답이 예상한 타입 구조를 지키는지 검증.
    (Content Scaffold의 jsonschema.validate()와 동일한 목적의 이중 안전장치)
    """
    if not isinstance(result, dict):
        return False
    if not isinstance(result.get("symptoms"), list):
        return False
    for s in result["symptoms"]:
        if not isinstance(s, dict) or "name" not in s or "negation" not in s:
            return False
    if not isinstance(result.get("interventions"), list):
        return False
    if "clinical_status" in result and not isinstance(result["clinical_status"], (str, type(None))):
        return False
    if "notification" in result and not isinstance(result["notification"], (str, type(None))):
        return False
    return True

def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_gold_texts(generated_text_dir: str) -> dict:
    gold = {}
    for f in sorted(Path(generated_text_dir).glob("*.json")):
        if f.name == "generation_log.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        gold[record["sample_id"]] = record["text"]
    return gold


def load_whisper_texts(stt_dir: str) -> dict:
    whisper = {}
    for f in sorted(Path(stt_dir).glob("*.json")):
        if f.name == "generation_log.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        whisper[record["sample_id"]] = record["whisper_transcript"]
    return whisper


def extract_with_retry(client, model, text, label):
    from src.entity_extraction.open_vocab_extractor import repair_nested_json_string

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = extract_open_vocab_entities(client, model, text)
        except Exception as e:
            print(f"  재시도 {attempt}/{MAX_RETRIES} ({label}): API 오류 [{type(e).__name__}] {e}")
            time.sleep(1)
            continue

        result = repair_nested_json_string(result)

        if is_valid_extraction(result):
            if attempt > 1:
                print(f"  복구 성공 ({label}), attempt {attempt}")
            return result

        print(f"  재시도 {attempt}/{MAX_RETRIES} ({label}): 응답 구조 검증 실패")
        print(f"  실제 응답: {json.dumps(result, ensure_ascii=False)[:300]}")
        time.sleep(1)

    raise RuntimeError(f"MAX_RETRIES 초과 ({label})")


def run_extraction(generated_text_dir, stt_dir, entities_dir, model):
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    gold_texts = load_gold_texts(generated_text_dir)
    whisper_texts = load_whisper_texts(stt_dir)

    out_path = Path(entities_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    count = 0
    total = len(gold_texts)

    for sample_id, gold_text in gold_texts.items():
        if sample_id not in whisper_texts:
            print(f"경고: {sample_id}에 대한 Whisper transcript 없음, 건너뜀")
            continue

        count += 1
        print(f"[{count}/{total}] {sample_id} 추출 중...")

        whisper_text = whisper_texts[sample_id]

        try:
            gold_entities = extract_with_retry(client, model, gold_text, "gold")
            whisper_entities = extract_with_retry(client, model, whisper_text, "whisper")
        except RuntimeError as e:
            print(f"  실패, 건너뜀: {e}")
            continue

        record = {
            "sample_id": sample_id,
            "gold_entities": gold_entities,
            "whisper_entities": whisper_entities
        }

        file_path = out_path / f"{sample_id}_open.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        print(f"  생성됨: {file_path}")

    print(f"\n총 {count}개 샘플에 대해 Open-vocabulary Entity Extraction 완료 -> {entities_dir}")


if __name__ == "__main__":
    config = load_config()
    generated_text_dir = config["paths"]["generated_text_dir"]
    stt_dir = config["paths"]["stt_transcripts_dir"]
    entities_dir = config["paths"]["entities_dir"]
    model = config["entity_extraction"]["claude_model"]

    run_extraction(generated_text_dir, stt_dir, entities_dir, model)