"""
Entity-level Evaluation

Precision/Recall/F1 정의:
- True Positive: match_status == "matched" (값까지 정확히 일치)
- Gold entity 수: gold_value가 존재하는 모든 레코드 (matched + error + omission)
- Whisper entity 수: whisper_value가 존재하는 모든 레코드 (matched + error + whisper_only)

Precision = TP / Whisper entity 수
Recall = TP / Gold entity 수
F1 = 조화평균
"""

import json
from pathlib import Path
from collections import defaultdict

import yaml
import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_style_lookup(generated_text_dir: str) -> dict:
    """sample_id -> style_condition 매핑."""
    lookup = {}
    for f in Path(generated_text_dir).glob("*.json"):
        if f.name == "generation_log.json":
            continue
        data = json.load(open(f, encoding="utf-8"))
        lookup[data["sample_id"]] = data["style_condition"]
    return lookup


def compute_prf1(records: list) -> dict:
    gold_count = sum(1 for r in records if r["gold_value"] is not None)
    whisper_count = sum(1 for r in records if r["whisper_value"] is not None)
    tp = sum(1 for r in records if r["match_status"] == "matched")

    precision = tp / whisper_count if whisper_count > 0 else 0.0
    recall = tp / gold_count if gold_count > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "gold_entity_count": gold_count,
        "whisper_entity_count": whisper_count,
        "true_positive": tp
    }


def run_entity_evaluation(entities_dir: str, generated_text_dir: str, results_dir: str):
    style_lookup = load_style_lookup(generated_text_dir)

    sample_rows = []
    style_records = defaultdict(list)

    for f in sorted(Path(entities_dir).glob("*_matched.json")):
        matched_data = json.load(open(f, encoding="utf-8"))
        sample_id = matched_data["sample_id"]
        style = style_lookup.get(sample_id, "unknown")

        records = flatten_all_matches(matched_data)
        style_records[style].extend(records)

        stats = compute_prf1(records)
        sample_rows.append({"sample_id": sample_id, "style_condition": style, **stats})

    out_path = Path(results_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(sample_rows)
    df.to_csv(out_path / "entity_eval_results.csv", index=False, encoding="utf-8-sig")

    style_summary = {}
    for style, records in style_records.items():
        style_summary[style] = compute_prf1(records)

    with open(out_path / "entity_eval_summary.json", "w", encoding="utf-8") as f:
        json.dump(style_summary, f, ensure_ascii=False, indent=2)

    print("=== Style별 Entity-level P/R/F1 ===")
    for style, stats in style_summary.items():
        print(f"{style}: P={stats['precision']}, R={stats['recall']}, F1={stats['f1']} "
              f"(gold={stats['gold_entity_count']}, whisper={stats['whisper_entity_count']})")

    print(f"\n결과 저장: {out_path}/entity_eval_results.csv, entity_eval_summary.json")


if __name__ == "__main__":
    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    generated_text_dir = config["paths"]["generated_text_dir"]
    results_dir = config["paths"]["results_dir"]

    run_entity_evaluation(entities_dir, generated_text_dir, results_dir)