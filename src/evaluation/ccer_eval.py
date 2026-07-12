"""
Clinical Critical Error Rate (CCER) Evaluation

[Methodological Note]
Error Type별 위험도 가중치는 NCC MERP(National Coordinating Council for
Medication Error Reporting and Prevention)의 환자 안전 중심 철학(오류가
환자에게 도달했는지, 도달했다면 얼마나 심각한 결과로 이어지는지)을
개념적으로 참고하여 설계하였다. 본 연구는 합성 데이터 기반 파일럿으로
실제 환자 결과(patient outcome) 데이터가 없으므로, NCC MERP의 A~I
카테고리를 직접 매핑하지 않았다. 대신 각 Error Type이 잠재적으로 야기할
수 있는 임상적 영향의 상대적 크기를 3단계로 연구자가 직접 판단하여
가중치를 부여하였다. 이는 검증된 임상 심각도 척도가 아니라 연구 목적의
근사적 가중치이다.

CCER Score = sum(weight_i * count_i) / total_gold_entities

[Known Limitation]
whisper_only(Whisper의 환각성 삽입)는 현재 가중치 체계에서 penalize하지
않는다 (weight=0, 집계에서 제외). Future Work로 남긴다.
"""

import json
from pathlib import Path
from collections import defaultdict, Counter

import yaml
import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches

ERROR_WEIGHTS = {
    "numeric_error": 3,
    "negation_flip": 3,
    "severity_shift": 3,
    "omission": 2,
    "substitution": 2,
    "route_error": 2,
    "frequency_error": 2,
    "unit_error": 2,
    "device_error": 2,
    "formatting_error": 1,
}


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_style_lookup(generated_text_dir: str) -> dict:
    lookup = {}
    for f in Path(generated_text_dir).glob("*.json"):
        if f.name == "generation_log.json":
            continue
        data = json.load(open(f, encoding="utf-8"))
        lookup[data["sample_id"]] = data["style_condition"]
    return lookup


def compute_ccer(records: list) -> dict:
    gold_count = sum(1 for r in records if r["gold_value"] is not None)

    error_type_counts = Counter(
        r["error_type"] for r in records if r["error_type"] is not None
    )

    entity_type_error_counts = defaultdict(int)
    entity_type_totals = defaultdict(int)
    for r in records:
        if r["gold_value"] is not None:
            entity_type_totals[r["entity_type"]] += 1
            if r["match_status"] == "error" or r["match_status"] == "omission":
                entity_type_error_counts[r["entity_type"]] += 1

    weighted_sum = sum(
        ERROR_WEIGHTS.get(error_type, 0) * count
        for error_type, count in error_type_counts.items()
    )

    ccer_score = weighted_sum / gold_count if gold_count > 0 else 0.0

    entity_error_profile = {
        etype: {
            "error_count": entity_type_error_counts[etype],
            "total_count": total,
            "error_rate": round(entity_type_error_counts[etype] / total, 4) if total > 0 else 0.0
        }
        for etype, total in entity_type_totals.items()
    }

    return {
        "ccer_score": round(ccer_score, 4),
        "gold_entity_count": gold_count,
        "error_type_profile": dict(error_type_counts),
        "entity_error_profile": entity_error_profile
    }


def run_ccer_evaluation(entities_dir: str, generated_text_dir: str, results_dir: str):
    style_lookup = load_style_lookup(generated_text_dir)

    sample_rows = []
    style_records = defaultdict(list)

    for f in sorted(Path(entities_dir).glob("*_matched.json")):
        matched_data = json.load(open(f, encoding="utf-8"))
        sample_id = matched_data["sample_id"]
        style = style_lookup.get(sample_id, "unknown")

        records = flatten_all_matches(matched_data)
        style_records[style].extend(records)

        result = compute_ccer(records)
        sample_rows.append({
            "sample_id": sample_id,
            "style_condition": style,
            "ccer_score": result["ccer_score"],
            "gold_entity_count": result["gold_entity_count"],
            "error_type_profile": json.dumps(result["error_type_profile"], ensure_ascii=False)
        })

    out_path = Path(results_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(sample_rows)
    df.to_csv(out_path / "ccer_results.csv", index=False, encoding="utf-8-sig")

    style_summary = {}
    for style, records in style_records.items():
        style_summary[style] = compute_ccer(records)

    with open(out_path / "ccer_summary.json", "w", encoding="utf-8") as f:
        json.dump(style_summary, f, ensure_ascii=False, indent=2)

    print("=== Style별 CCER ===")
    for style, stats in style_summary.items():
        print(f"{style}: CCER = {stats['ccer_score']} (gold_entities={stats['gold_entity_count']})")
        print(f"  Error Type Profile: {stats['error_type_profile']}")

    print(f"\n결과 저장: {out_path}/ccer_results.csv, ccer_summary.json")


if __name__ == "__main__":
    config = load_config()
    entities_dir = config["paths"]["entities_dir"]
    generated_text_dir = config["paths"]["generated_text_dir"]
    results_dir = config["paths"]["results_dir"]

    run_ccer_evaluation(entities_dir, generated_text_dir, results_dir)