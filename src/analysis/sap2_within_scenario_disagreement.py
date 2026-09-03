"""
SAP #2: Within-Scenario Metric Disagreement

docs/statistical_analysis_plan.md §2 확정 내용을 그대로 구현.

Tie 정의: WER(normalized), CCER 값 모두 4자리 반올림 기준으로 완전히
동일한 경우.

Primary:
1. Complete ranking agreement (tie 구조 포함 완전 일치 비율)
2. Best-style agreement (최선 스타일 일치 비율, tie 별도 카테고리)
3. Pairwise concordant/discordant/tie (3개 style pair 각각)

Secondary/descriptive:
- 시나리오별 Kendall's tau-b(WER 순위 vs CCER 순위) 분포

사용법:
    python -m src.analysis.sap2_within_scenario_disagreement --results-dir results/full_100
"""

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]
ROUND_DECIMALS = 4


def load_merged(results_dir: Path) -> pd.DataFrame:
    wer = pd.read_csv(results_dir / "wer_results.csv", encoding="utf-8-sig",
                       dtype={"scenario_id": str})
    ccer = pd.read_csv(results_dir / "ccer_results.csv", encoding="utf-8-sig")
    # wer_results.csv의 scenario_id는 "scenario_001" 전체 접두사 포함 형식이므로 맞춰준다
    ccer["scenario_id"] = ccer["sample_id"].str.rsplit("_", n=1).str[0].str.extract(
        r"(scenario_\d+)"
    )[0]
    merged = wer[["scenario_id", "style_condition", "wer_normalized"]].merge(
        ccer[["sample_id", "scenario_id", "style_condition", "ccer_score"]],
        on=["scenario_id", "style_condition"]
    )
    merged["wer_normalized"] = merged["wer_normalized"].round(ROUND_DECIMALS)
    merged["ccer_score"] = merged["ccer_score"].round(ROUND_DECIMALS)
    return merged


def scenario_ranks(value_dict: dict) -> tuple:
    """{style: value} -> 순위 tuple (낮을수록 좋음=1등). 동률은 average rank."""
    s = pd.Series(value_dict)
    ranks = s.rank(method="min")  # tie는 같은(최소) 순위 공유
    return tuple(ranks[style] for style in STYLES)


def analyze(df: pd.DataFrame):
    scenarios = sorted(df["scenario_id"].unique())
    complete_agree = 0
    best_agree = 0
    best_tie_either = 0
    pair_records = {f"{a}_vs_{b}": {"concordant": 0, "discordant": 0, "tie": 0}
                     for a, b in combinations(STYLES, 2)}
    tau_values = []

    for sid in scenarios:
        sub = df[df["scenario_id"] == sid].set_index("style_condition")
        wer_vals = {s: sub.loc[s, "wer_normalized"] for s in STYLES}
        ccer_vals = {s: sub.loc[s, "ccer_score"] for s in STYLES}

        wer_ranks = scenario_ranks(wer_vals)
        ccer_ranks = scenario_ranks(ccer_vals)

        if wer_ranks == ccer_ranks:
            complete_agree += 1

        wer_min = min(wer_vals.values())
        ccer_min = min(ccer_vals.values())
        wer_best = {s for s, v in wer_vals.items() if v == wer_min}
        ccer_best = {s for s, v in ccer_vals.items() if v == ccer_min}
        if len(wer_best) > 1 or len(ccer_best) > 1:
            best_tie_either += 1
        elif wer_best == ccer_best:
            best_agree += 1

        for a, b in combinations(STYLES, 2):
            key = f"{a}_vs_{b}"
            wer_tie = wer_vals[a] == wer_vals[b]
            ccer_tie = ccer_vals[a] == ccer_vals[b]
            if wer_tie or ccer_tie:
                pair_records[key]["tie"] += 1
                continue
            wer_a_better = wer_vals[a] < wer_vals[b]
            ccer_a_better = ccer_vals[a] < ccer_vals[b]
            if wer_a_better == ccer_a_better:
                pair_records[key]["concordant"] += 1
            else:
                pair_records[key]["discordant"] += 1

        tau, _ = kendalltau(list(wer_ranks), list(ccer_ranks))
        tau_values.append(tau)

    n = len(scenarios)
    print(f"총 시나리오 수: {n}\n")

    print("=== Primary 1: Complete Ranking Agreement ===")
    print(f"{complete_agree}/{n} ({complete_agree / n:.1%})")

    print("\n=== Primary 2: Best-Style Agreement ===")
    print(f"일치: {best_agree}/{n} ({best_agree / n:.1%})")
    print(f"최선 tie(WER 또는 CCER 중 하나 이상): {best_tie_either}/{n} ({best_tie_either / n:.1%})")
    print(f"불일치(tie 아니면서 다름): {n - best_agree - best_tie_either}/{n} "
          f"({(n - best_agree - best_tie_either) / n:.1%})")

    print("\n=== Primary 3: Pairwise Concordance/Discordance/Tie ===")
    pair_df = pd.DataFrame(pair_records).T
    pair_df["total"] = pair_df.sum(axis=1)
    pair_df["concordant_pct"] = (pair_df["concordant"] / pair_df["total"]).round(4)
    pair_df["discordant_pct"] = (pair_df["discordant"] / pair_df["total"]).round(4)
    pair_df["tie_pct"] = (pair_df["tie"] / pair_df["total"]).round(4)
    print(pair_df)

    print("\n=== Secondary: Kendall's tau-b (WER 순위 vs CCER 순위) 분포 ===")
    tau_arr = np.array(tau_values)
    print(f"평균: {tau_arr.mean():.4f}, 중앙값: {np.median(tau_arr):.4f}, 표준편차: {tau_arr.std():.4f}")
    print(f"tau=+1(완전 일치)인 시나리오: {(tau_arr == 1).sum()}/{n} ({(tau_arr == 1).sum() / n:.1%})")
    print(f"tau=-1(완전 역전)인 시나리오: {(tau_arr == -1).sum()}/{n} ({(tau_arr == -1).sum() / n:.1%})")
    print(f"tau<0(역전 방향)인 시나리오: {(tau_arr < 0).sum()}/{n} ({(tau_arr < 0).sum() / n:.1%})")

    return {
        "complete_agreement_rate": complete_agree / n,
        "best_style_agreement_rate": best_agree / n,
        "best_style_tie_rate": best_tie_either / n,
        "pairwise": pair_df,
        "tau_mean": tau_arr.mean(),
        "tau_median": np.median(tau_arr),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=str, default="results/full_100")
    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    df = load_merged(results_dir)
    result = analyze(df)

    result["pairwise"].to_csv(results_dir / "sap2_pairwise_disagreement.csv")
    print(f"\n저장 완료: {results_dir / 'sap2_pairwise_disagreement.csv'}")


if __name__ == "__main__":
    main()
