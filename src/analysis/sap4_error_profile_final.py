"""
SAP #4: 100-Scenario 최종 Error Profile (count + rate)

docs/statistical_analysis_plan.md §4 확정 내용을 그대로 구현.
기존 error_profile.py의 교차표 로직을 재사용하되, entity_type별 Gold entity
총 개수를 분모로 한 error rate를 추가로 계산한다.

사용법:
    python -m src.analysis.sap4_error_profile_final
"""

import json
import glob

import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches

STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]


def load_all_records():
    records = []
    for path in sorted(glob.glob("data/entities/scenario_*_matched.json")):
        with open(path, encoding="utf-8") as f:
            matched_data = json.load(f)
        sample_id = matched_data["sample_id"]
        parts = sample_id.split("_")
        style_condition = "_".join(parts[2:])
        for r in flatten_all_matches(matched_data):
            records.append({
                "style_condition": style_condition,
                "entity_type": r["entity_type"],
                "error_type": r["error_type"],
                "has_gold": r["gold_value"] is not None,
            })
    return pd.DataFrame(records)


def gold_counts_by_style_entity(df: pd.DataFrame) -> pd.DataFrame:
    """(style, entity_type)별 Gold entity 총 개수."""
    gold = df[df["has_gold"]]
    return gold.groupby(["style_condition", "entity_type"]).size()


def error_counts_by_style_entity_error(df: pd.DataFrame) -> pd.DataFrame:
    errors = df[df["error_type"].notna()]
    return errors.groupby(["style_condition", "entity_type", "error_type"]).size()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=str, default="results/full_100")
    args = parser.parse_args()
    output_dir = args.output_dir
    import os
    os.makedirs(output_dir, exist_ok=True)

    df = load_all_records()
    print(f"총 레코드 수: {len(df)}")

    gold_counts = gold_counts_by_style_entity(df)
    error_counts = error_counts_by_style_entity_error(df)

    rows = []
    for (style, entity_type, error_type), count in error_counts.items():
        gold_n = gold_counts.get((style, entity_type), None)
        rate = round(count / gold_n, 4) if gold_n and gold_n > 0 else None
        rows.append({
            "style_condition": style, "entity_type": entity_type, "error_type": error_type,
            "error_count": count, "gold_entity_count": gold_n, "error_rate": rate,
        })
    result_df = pd.DataFrame(rows).sort_values(
        ["style_condition", "entity_type", "error_type"]
    )

    result_df.to_csv(f"{output_dir}/sap4_error_profile_with_rates.csv", index=False)
    print(f"저장 완료: {output_dir}/sap4_error_profile_with_rates.csv")

    print(f"\n{'=' * 70}\nFormal Template의 omission이 어떤 entity_type에서 주로 발생하는가\n{'=' * 70}")
    formal_omission = result_df[
        (result_df["style_condition"] == "formal_template") & (result_df["error_type"] == "omission")
    ].sort_values("error_count", ascending=False)
    print(formal_omission[["entity_type", "error_count", "gold_entity_count", "error_rate"]]
          .to_string(index=False))

    print(f"\n{'=' * 70}\nClinical/Telegraphic의 numeric_error가 어떤 entity_type에서 주로 발생하는가\n{'=' * 70}")
    for style in ["clinical_charting", "telegraphic_icu"]:
        sub = result_df[
            (result_df["style_condition"] == style) & (result_df["error_type"] == "numeric_error")
        ].sort_values("error_count", ascending=False)
        print(f"\n--- {style} ---")
        print(sub[["entity_type", "error_count", "gold_entity_count", "error_rate"]]
              .to_string(index=False))

    print(f"\n{'=' * 70}\nentity_type별 error_rate 요약 (스타일 간 비교, error_type 무관 합산)\n{'=' * 70}")
    entity_total_errors = result_df.groupby(["style_condition", "entity_type"]).agg(
        total_errors=("error_count", "sum")
    ).reset_index()
    entity_total_errors = entity_total_errors.merge(
        gold_counts.rename("gold_entity_count").reset_index(),
        on=["style_condition", "entity_type"]
    )
    entity_total_errors["overall_error_rate"] = (
        entity_total_errors["total_errors"] / entity_total_errors["gold_entity_count"]
    ).round(4)
    pivot = entity_total_errors.pivot(index="entity_type", columns="style_condition",
                                       values="overall_error_rate")
    print(pivot[STYLES])

    pivot.to_csv(f"{output_dir}/sap4_entity_type_error_rate_by_style.csv")
    print(f"\n저장 완료: {output_dir}/sap4_entity_type_error_rate_by_style.csv")


if __name__ == "__main__":
    main()
