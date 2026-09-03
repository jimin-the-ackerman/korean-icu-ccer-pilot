"""
SAP #3: CCER Weight Sensitivity Analysis

docs/statistical_analysis_plan.md §3 확정 내용을 그대로 구현.
5개 weighting scheme은 결과 확인 전에 이미 문서로 고정되어 있으며,
이 스크립트는 그 문서의 표를 코드로 옮긴 것뿐이다 (결과 보고 조정하지 않음).

사용법:
    python -m src.analysis.sap3_weight_sensitivity
"""

import json
import glob

import pandas as pd
import pingouin as pg

from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.ccer_eval import compute_ccer as _compute_ccer_default

STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]

# docs/statistical_analysis_plan.md §3에서 확정한 5개 scheme
TIER3_BASE = {"numeric_error", "negation_flip", "severity_shift",
              "hallucination", "medication_identity_error"}
TIER2_BASE = {"omission", "substitution", "route_error", "frequency_error",
              "unit_error", "device_error"}
TIER1_BASE = {"formatting_error"}

WEIGHT_SCHEMES = {
    "Primary": {**{k: 3 for k in TIER3_BASE}, **{k: 2 for k in TIER2_BASE},
                **{k: 1 for k in TIER1_BASE}},
    "A_Equal": {**{k: 1 for k in TIER3_BASE}, **{k: 1 for k in TIER2_BASE},
                **{k: 1 for k in TIER1_BASE}},
    "B_Wide": {**{k: 5 for k in TIER3_BASE}, **{k: 2 for k in TIER2_BASE},
               **{k: 1 for k in TIER1_BASE}},
    "C_Narrow": {**{k: 1.5 for k in TIER3_BASE}, **{k: 1.2 for k in TIER2_BASE},
                 **{k: 1 for k in TIER1_BASE}},
    "D_Hallucination_downweighted": {
        **{k: 3 for k in TIER3_BASE if k != "hallucination"},
        "hallucination": 2,
        **{k: 2 for k in TIER2_BASE},
        **{k: 1 for k in TIER1_BASE},
    },
}


def compute_ccer_with_weights(records: list, weights: dict) -> dict:
    """ccer_eval.compute_ccer()과 동일한 로직이나 ERROR_WEIGHTS를 인자로 받는 버전."""
    from collections import defaultdict, Counter

    gold_records = [r for r in records if r["gold_value"] is not None]
    total_gold = len(gold_records)

    error_counter = Counter(r["error_type"] for r in records if r["error_type"] is not None)
    weighted_sum = sum(weights.get(err, 0) * cnt for err, cnt in error_counter.items())

    ccer_score = round(weighted_sum / total_gold, 4) if total_gold > 0 else 0.0
    return {"ccer_score": ccer_score, "gold_entity_count": total_gold,
            "error_type_profile": dict(error_counter)}


def load_all_flattened_records():
    """sample_id -> flattened records 캐시 (5개 scheme 반복 계산 시 재사용)."""
    cache = {}
    for path in sorted(glob.glob("data/entities/scenario_*_matched.json")):
        with open(path, encoding="utf-8") as f:
            matched_data = json.load(f)
        sample_id = matched_data["sample_id"]
        parts = sample_id.split("_")
        scenario_id = "_".join(parts[:2])
        style_condition = "_".join(parts[2:])
        cache[sample_id] = {
            "scenario_id": scenario_id,
            "style_condition": style_condition,
            "records": flatten_all_matches(matched_data),
        }
    return cache


def run_scheme(cache: dict, weights: dict) -> pd.DataFrame:
    rows = []
    for sample_id, info in cache.items():
        result = compute_ccer_with_weights(info["records"], weights)
        rows.append({
            "sample_id": sample_id,
            "scenario_id": info["scenario_id"],
            "style_condition": info["style_condition"],
            "ccer_score": result["ccer_score"],
        })
    return pd.DataFrame(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=str, default="results/full_100")
    args = parser.parse_args()
    output_dir = args.output_dir
    import os
    os.makedirs(output_dir, exist_ok=True)

    cache = load_all_flattened_records()
    print(f"로드된 샘플 수: {len(cache)}")

    scheme_summaries = {}
    scheme_style_means = {}

    for scheme_name, weights in WEIGHT_SCHEMES.items():
        df = run_scheme(cache, weights)
        style_means = df.groupby("style_condition")["ccer_score"].mean()
        ranking = style_means.sort_values().index.tolist()  # 낮은 순 = 좋은 순

        friedman = pg.friedman(data=df, dv="ccer_score", within="style_condition",
                                subject="scenario_id")
        kendalls_w = friedman.iloc[0]["W"]
        friedman_p = friedman.iloc[0]["p_unc"]

        formal_is_ccer_best = ranking[0] == "formal_template"

        scheme_style_means[scheme_name] = style_means.to_dict()
        scheme_summaries[scheme_name] = {
            "mean_ccer_formal": style_means["formal_template"],
            "mean_ccer_clinical": style_means["clinical_charting"],
            "mean_ccer_telegraphic": style_means["telegraphic_icu"],
            "ranking_best_to_worst": " < ".join(ranking),
            "formal_is_ccer_best": formal_is_ccer_best,
            "kendalls_w": round(kendalls_w, 4),
            "friedman_p": round(friedman_p, 4),
        }

        print(f"\n=== Scheme: {scheme_name} (tier3/tier2/tier1 예시 가중치) ===")
        print(f"  Style별 mean CCER: {style_means.round(4).to_dict()}")
        print(f"  순위(좋은순->나쁜순): {' < '.join(ranking)}")
        print(f"  Formal Template이 CCER 최선인가: {formal_is_ccer_best}")
        print(f"  Kendall's W: {kendalls_w:.4f}, Friedman p: {friedman_p:.4f}")

    summary_df = pd.DataFrame(scheme_summaries).T
    print(f"\n{'=' * 70}\n종합 요약\n{'=' * 70}")
    print(summary_df)

    print(f"\n{'=' * 70}\nPrimary robustness criterion 확인\n{'=' * 70}")
    any_formal_best = summary_df["formal_is_ccer_best"].any()
    print(f"5개 scheme 중 Formal Template이 CCER 최선이 된 적이 있는가: {any_formal_best}")
    if not any_formal_best:
        print("-> Formal Template은 WER 기준 최선임에도 불구하고, 사전 정의된 5개 "
              "weighting scheme 전반에서 단 한 번도 CCER 기준 최선이 되지 않음 "
              "(robustness criterion 충족)")

    print(f"\n{'=' * 70}\nSecondary: Exact ranking 유지 여부\n{'=' * 70}")
    rankings = summary_df["ranking_best_to_worst"].unique()
    print(f"5개 scheme에서 나온 서로 다른 순위 패턴 수: {len(rankings)}")
    for r in rankings:
        schemes_with_r = summary_df[summary_df["ranking_best_to_worst"] == r].index.tolist()
        print(f"  '{r}': {schemes_with_r}")

    summary_df.to_csv(f"{output_dir}/sap3_weight_sensitivity_summary.csv")
    print(f"\n저장 완료: {output_dir}/sap3_weight_sensitivity_summary.csv")


if __name__ == "__main__":
    main()
