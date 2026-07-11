"""
Word Error Rate Evaluation (paper Section 5.2, Transcript-level Evaluation)

[Limitation]
jiwer의 기본 WER 계산은 공백 기준 단어 분리를 전제로 한다. 한국어는 교착어
특성상(조사가 단어에 결합) 영어만큼 단어 경계가 명확하지 않으며, 특히
Telegraphic Style처럼 압축된 문장에서는 WER 수치가 실제 정보 손실을
과대/과소평가할 수 있다. 이 한계는 Entity-level Evaluation과 CCER로
보완된다.

Pipeline:
data/generated_text/{sample_id}.json  (Gold Transcript)
data/stt_transcripts/{sample_id}.json (Whisper Transcript)
    -> jiwer WER computation
    -> results/pilot_15/wer_results.csv
"""

import json
import re
from pathlib import Path
from collections import defaultdict

import yaml
import jiwer
import pandas as pd


def normalize_text(text: str) -> str:
    """
    WER 계산 전 정규화. 임상적으로 무의미한 표기 차이(대소문자, 구두점, 중복 공백)를
    제거하여, WER이 실제 정보 손실에 더 가깝게 반영되도록 한다.

    주의: 이 정규화는 WER 계산 전용이며, Entity Extraction 단계에서는
    원문(gold_text, whisper_text)을 그대로 사용한다 — 대소문자 등이
    약어 인식(예: IV vs iv)에 영향을 줄 수 있기 때문이다.
    """
    text = text.lower()
    text = re.sub(r"[.,!?;:]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_gold_transcripts(generated_text_dir: str) -> dict:
    """sample_id -> {text, style_condition, scenario_id}"""
    gold = {}
    for f in sorted(Path(generated_text_dir).glob("*.json")):
        if f.name == "generation_log.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        gold[record["sample_id"]] = {
            "text": record["text"],
            "style_condition": record["style_condition"],
            "scenario_id": record["scenario_id"]
        }
    return gold


def load_whisper_transcripts(stt_dir: str) -> dict:
    """sample_id -> whisper_transcript text"""
    whisper = {}
    for f in sorted(Path(stt_dir).glob("*.json")):
        if f.name == "generation_log.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        whisper[record["sample_id"]] = record["whisper_transcript"]
    return whisper


def compute_wer_results(gold: dict, whisper: dict) -> list[dict]:
    results = []

    for sample_id, gold_data in gold.items():
        if sample_id not in whisper:
            print(f"경고: {sample_id}에 대한 Whisper transcript 없음, 건너뜀")
            continue

        gold_text = gold_data["text"]
        whisper_text = whisper[sample_id]

        wer_raw = jiwer.wer(gold_text, whisper_text)
        wer_normalized = jiwer.wer(normalize_text(gold_text), normalize_text(whisper_text))

        results.append({
            "sample_id": sample_id,
            "scenario_id": gold_data["scenario_id"],
            "style_condition": gold_data["style_condition"],
            "wer_raw": round(wer_raw, 4),
            "wer_normalized": round(wer_normalized, 4),
            "gold_text": gold_text,
            "whisper_text": whisper_text
        })

    return results


def summarize_by_style(results: list[dict]) -> dict:
    grouped = defaultdict(list)
    for r in results:
        grouped[r["style_condition"]].append(r)

    summary = {}
    for style, rows in grouped.items():
        raw_list = [r["wer_raw"] for r in rows]
        norm_list = [r["wer_normalized"] for r in rows]
        summary[style] = {
            "mean_wer_raw": round(sum(raw_list) / len(raw_list), 4),
            "mean_wer_normalized": round(sum(norm_list) / len(norm_list), 4),
            "n_samples": len(rows)
        }
    return summary


def run_wer_evaluation(generated_text_dir, stt_dir, results_dir):
    gold = load_gold_transcripts(generated_text_dir)
    whisper = load_whisper_transcripts(stt_dir)

    results = compute_wer_results(gold, whisper)

    out_path = Path(results_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)
    csv_path = out_path / "wer_results.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"개별 결과 저장: {csv_path}")

    summary = summarize_by_style(results)
    summary_path = out_path / "wer_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n=== Style별 평균 WER (raw / normalized) ===")
    for style, stats in summary.items():
        print(f"{style}: raw = {stats['mean_wer_raw']}, normalized = {stats['mean_wer_normalized']} (n={stats['n_samples']})")

    print(f"\n요약 저장: {summary_path}")


if __name__ == "__main__":
    config = load_config()
    generated_text_dir = config["paths"]["generated_text_dir"]
    stt_dir = config["paths"]["stt_transcripts_dir"]
    results_dir = config["paths"]["results_dir"]

    run_wer_evaluation(generated_text_dir, stt_dir, results_dir)