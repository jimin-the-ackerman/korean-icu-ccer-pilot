"""
Error Profile 분석 (Score/Profile/Severity/Signature 4축 중 Profile 축)

목적:
1. 스타일별 error_type 분포 — "어떤 종류의 오류가 스타일마다 얼마나 다르게 나타나는가"
2. entity_type × error_type 교차표 — "어떤 종류의 임상 정보가 어떤 오류에 특히 취약한가"

recompute_pilot15_v2partial.py와 마찬가지로 data/entities/*_matched.json을
직접 읽어 flatten_all_matches()를 적용하며, 별도 API 호출은 없다.

사용법:
    python -m src.analysis.error_profile
"""

import json
from pathlib import Path
from collections import defaultdict

import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches

ENTITIES_DIR = Path("data/entities")
OUTPUT_DIR = Path("results/pilot_15")


def load_all_records():
    """모든 matched.json을 flatten하여 (style_condition, entity_type, error_type) 레코드 목록 생성."""
    all_records = []
    for path in sorted(ENTITIES_DIR.glob("scenario_*_matched.json")):
        with open(path, encoding="utf-8") as f:
            matched_data = json.load(f)

        sample_id = matched_data["sample_id"]
        parts = sample_id.split("_")
        scenario_id = parts[1]
        style_condition = "_".join(parts[2:])

        for r in flatten_all_matches(matched_data):
            all_records.append({
                "scenario_id": scenario_id,
                "style_condition": style_condition,
                "entity_type": r["entity_type"],
                "match_status": r["match_status"],
                "error_type": r["error_type"],
            })
    return pd.DataFrame(all_records)


def error_type_by_style(df: pd.DataFrame) -> pd.DataFrame:
    """스타일별 error_type 분포 (건수 + 해당 스타일 내 비율).

    분모는 "그 스타일에서 발생한 전체 오류 건수"(error_type이 not null인 레코드 수)이다.
    즉 "오류가 발생했다면, 그중 몇 %가 어떤 유형이었는가"를 보여준다
    (CCER 분모인 gold_entity_count와는 다른 관점).
    """
    errors = df[df["error_type"].notna()]
    counts = errors.groupby(["style_condition", "error_type"]).size().unstack(fill_value=0)
    proportions = counts.div(counts.sum(axis=1), axis=0).round(4)
    return counts, proportions


def entity_type_x_error_type(df: pd.DataFrame) -> pd.DataFrame:
    """entity_type × error_type 교차표 (전체 스타일 합산 기준 건수)."""
    errors = df[df["error_type"].notna()]
    crosstab = pd.crosstab(errors["entity_type"], errors["error_type"])
    return crosstab


def entity_type_x_error_type_by_style(df: pd.DataFrame) -> dict:
    """스타일별로 entity_type × error_type 교차표를 따로 계산."""
    result = {}
    for style in df["style_condition"].unique():
        sub = df[(df["style_condition"] == style) & (df["error_type"].notna())]
        result[style] = pd.crosstab(sub["entity_type"], sub["error_type"])
    return result


def main():
    df = load_all_records()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== 스타일별 Error Type 분포 (건수) ===")
    counts, proportions = error_type_by_style(df)
    print(counts)
    counts.to_csv(OUTPUT_DIR / "error_type_counts_by_style.csv")

    print("\n=== 스타일별 Error Type 분포 (비율, 그 스타일 전체 오류 대비) ===")
    print(proportions)
    proportions.to_csv(OUTPUT_DIR / "error_type_proportions_by_style.csv")

    print("\n=== Entity Type × Error Type 교차표 (전체 스타일 합산) ===")
    crosstab = entity_type_x_error_type(df)
    print(crosstab)
    crosstab.to_csv(OUTPUT_DIR / "entity_x_error_crosstab_overall.csv")

    print("\n=== 스타일별 Entity Type × Error Type 교차표 ===")
    by_style = entity_type_x_error_type_by_style(df)
    for style, table in by_style.items():
        print(f"\n--- {style} ---")
        print(table)
        table.to_csv(OUTPUT_DIR / f"entity_x_error_crosstab_{style}.csv")

    print(f"\n저장 완료: {OUTPUT_DIR}/ 에 CSV 5종")


if __name__ == "__main__":
    main()
