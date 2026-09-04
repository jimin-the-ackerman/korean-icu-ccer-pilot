"""
Macro-CCER Sensitivity Analysis (SAP 확정 이후 사후 추가)

docs/statistical_analysis_plan.md는 4개 분석(WER-CCER association,
within-scenario disagreement, weight sensitivity, error profile)으로
freeze되었다. 이 스크립트는 그 이후, v4 최종 결과 해석 과정에서 제기된
질문 — "Formal Template의 aggregate CCER 우위가 단지 vital_sign(gold
entity 500개, 전체의 약 35%)의 높은 빈도 때문 아닌가?" — 에 답하기 위해
**사후에(post-hoc) 추가**된 것임을 명시한다. Primary metric(micro-CCER,
빈도 가중)을 대체하는 게 아니라, weight-sensitivity analysis(SAP #3)와
같은 성격의 **robustness check 하나를 추가**하는 것이다.

Micro-CCER(기존): sum(weight_i * error_count_i) / total_gold_entities
  -> entity_type의 등장 빈도에 비례해 영향력이 커짐(예: vital_sign처럼
     자주 나오는 정보가 CCER을 지배)

Macro-CCER(이 스크립트): 먼저 entity_type별로 micro-CCER을 각각 계산한
뒤, 11개 entity_type에 동일한 가중치를 주어 평균낸다. 이는 "어느 쪽이
정답이냐"의 문제가 아니라(빈도가 높은 정보를 잘 지키는 것도 임상적으로
의미가 있을 수 있음), 결론이 특정 entity_type의 빈도에 좌우되는지
확인하는 보조 렌즈다.

사용법:
    python -m src.analysis.sap5_macro_ccer
"""

import json
import glob
from collections import defaultdict

import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.ccer_eval import ERROR_WEIGHTS

STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]


def compute_entity_type_ccer_table():
    data = defaultdict(lambda: defaultdict(lambda: {"weighted_error": 0, "gold_count": 0}))

    for path in sorted(glob.glob("data/entities/scenario_*_matched.json")):
        d = json.load(open(path, encoding="utf-8"))
        style = "_".join(d["sample_id"].split("_")[2:])
        for r in flatten_all_matches(d):
            et = r["entity_type"]
            if r["gold_value"] is not None:
                data[style][et]["gold_count"] += 1
            if r["error_type"] is not None:
                data[style][et]["weighted_error"] += ERROR_WEIGHTS.get(r["error_type"], 0)

    entity_types = sorted(data["formal_template"].keys())
    rows = []
    for et in entity_types:
        row = {"entity_type": et}
        for style in STYLES:
            info = data[style][et]
            gold_n = info["gold_count"]
            row[f"gold_n_{style}"] = gold_n
            row[f"micro_ccer_{style}"] = (
                round(info["weighted_error"] / gold_n, 4) if gold_n > 0 else None
            )
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    table = compute_entity_type_ccer_table()

    print("=== entity_type별 micro-CCER(해당 type 기준) ===")
    print(table.to_string(index=False))

    print(f"\n{'=' * 70}\nMacro-CCER (entity_type 균등 가중) vs 기존 Micro-CCER(aggregate)\n{'=' * 70}")
    summary_rows = []
    win_count = {style: 0 for style in STYLES}
    for _, row in table.iterrows():
        vals = {style: row[f"micro_ccer_{style}"] for style in STYLES}
        valid_vals = {k: v for k, v in vals.items() if v is not None}
        if valid_vals:
            best = min(valid_vals, key=valid_vals.get)
            win_count[best] += 1

    for style in STYLES:
        macro_vals = table[f"micro_ccer_{style}"].dropna()
        macro_ccer = round(macro_vals.mean(), 4)
        summary_rows.append({
            "style_condition": style,
            "macro_ccer": macro_ccer,
            "n_entity_types_best_in": win_count[style],
        })
        print(f"{style:20s} Macro-CCER={macro_ccer:.4f}  "
              f"({win_count[style]}/{len(table)} entity_type에서 최선)")

    summary_df = pd.DataFrame(summary_rows)
    ranking = summary_df.sort_values("macro_ccer")["style_condition"].tolist()
    print(f"\nMacro-CCER 순위(좋은순): {' < '.join(ranking)}")

    output_dir = "results/full_100_v4"
    table.to_csv(f"{output_dir}/sap5_entity_type_ccer_table.csv", index=False)
    summary_df.to_csv(f"{output_dir}/sap5_macro_ccer_summary.csv", index=False)
    print(f"\n저장 완료: {output_dir}/sap5_entity_type_ccer_table.csv, sap5_macro_ccer_summary.csv")


if __name__ == "__main__":
    main()
