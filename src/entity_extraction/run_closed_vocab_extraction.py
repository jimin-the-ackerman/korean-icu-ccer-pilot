"""
Closed-vocabulary Entity Extraction — 전체 데이터셋 실행 

Pipeline:
data/generated_text/{sample_id}.json  (Gold Transcript)
data/stt_transcripts/{sample_id}.json (Whisper Transcript)
    -> extract_closed_vocab_entities() 각각 적용
    -> data/entities/{sample_id}_closed.json
"""

import json
from pathlib import Path

import yaml

from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities


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


def run_extraction(generated_text_dir, stt_dir, entities_dir):
    gold_texts = load_gold_texts(generated_text_dir)
    whisper_texts = load_whisper_texts(stt_dir)

    out_path = Path(entities_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for sample_id, gold_text in gold_texts.items():
        if sample_id not in whisper_texts:
            print(f"경고: {sample_id}에 대한 Whisper transcript 없음, 건너뜀")
            continue

        whisper_text = whisper_texts[sample_id]

        gold_entities = extract_closed_vocab_entities(gold_text)
        whisper_entities = extract_closed_vocab_entities(whisper_text)

        record = {
            "sample_id": sample_id,
            "gold_entities": gold_entities,
            "whisper_entities": whisper_entities
        }

        file_path = out_path / f"{sample_id}_closed.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        count += 1
        print(f"[{count}] {sample_id} -> {file_path}")

    print(f"\n총 {count}개 샘플에 대해 Closed-vocabulary Entity Extraction 완료 -> {entities_dir}")


if __name__ == "__main__":
    config = load_config()
    generated_text_dir = config["paths"]["generated_text_dir"]
    stt_dir = config["paths"]["stt_transcripts_dir"]
    entities_dir = config["paths"]["entities_dir"]

    run_extraction(generated_text_dir, stt_dir, entities_dir)