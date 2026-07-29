"""
Repeated-Measures Power Analysis

목적: 15샘플(시나리오 15개 × 스타일 3개) 파일럿의 CCER 결과로부터 효과 크기를
추정하고, 3주차 config 확장 시 몇 개의 시나리오가 필요한지(50 vs 100 vs 그 이상)를
"감"이 아니라 통계적 근거로 결정한다.

전제: 이 스크립트는 2주차에 CCER v2 공식(hallucination penalty 반영)으로
15샘플을 재실행한 결과를 입력으로 받는다. v1 결과로 계산하면 안 된다 —
공식이 바뀌었으므로 효과 크기 자체가 달라질 수 있다.

입력 형식 (long format CSV, results/pilot_15/ccer_results.csv와 동일 스키마 가정):
    scenario_id, style_condition, ccer_score
    001, formal_template, 0.42
    001, clinical_charting, 0.31
    001, telegraphic_icu, 0.18
    002, formal_template, ...

사용법:
    python -m src.analysis.power_analysis --input results/pilot_15/ccer_results.csv
"""

import argparse
import sys

import numpy as np
import pandas as pd
import pingouin as pg


def compute_effect_size(df: pd.DataFrame) -> dict:
    """15샘플 파일럿 데이터로 repeated-measures ANOVA를 돌려 효과 크기를 구한다."""
    aov = pg.rm_anova(
        data=df, dv="ccer_score", within="style_condition", subject="scenario_id",
        detailed=True
    )
    # pingouin의 rm_anova는 generalized eta-squared(ng2)를 반환한다 (pingouin 0.6.1 기준)
    row = aov.iloc[0]
    partial_eta_sq = row["ng2"]
    n_scenarios = df["scenario_id"].nunique()
    n_styles = df["style_condition"].nunique()

    # 스타일 반복측정 간 평균 상관계수 (검정력 계산에 필요)
    # 상관계수는 정규분포를 따르지 않으므로 Fisher z-변환 후 평균, 다시 역변환한다
    # (pingouin.power_rm_anova 공식 예제에서 권장하는 방식)
    pivot = df.pivot(index="scenario_id", columns="style_condition", values="ccer_score")
    corr_matrix = pivot.corr()
    off_diag_mask = ~np.eye(corr_matrix.shape[0], dtype=bool)
    off_diag_vals = corr_matrix.values[off_diag_mask]
    mean_corr = np.tanh(np.arctanh(off_diag_vals).mean())

    return {
        "partial_eta_sq": partial_eta_sq,
        "n_scenarios_pilot": n_scenarios,
        "n_styles": n_styles,
        "mean_within_scenario_corr": mean_corr,
        "anova_table": aov,
    }


def required_n_for_power(partial_eta_sq: float, n_styles: int, mean_corr: float,
                          target_power: float = 0.8, alpha: float = 0.05):
    """목표 검정력(기본 0.8)을 달성하기 위해 필요한 시나리오 수를 역산한다.

    효과 크기가 매우 커서 solver의 기본 탐색 범위(n이 매우 작은 영역) 안에
    해가 없는 경우 NaN이 나올 수 있다. 이 경우 n=3..20 구간을 직접 스캔하여
    각 n에서 달성되는 power를 보여주는 fallback으로 대체한다.
    """
    result = pg.power_rm_anova(
        eta_squared=partial_eta_sq,
        m=n_styles,
        corr=mean_corr,
        power=target_power,
        alpha=alpha,
        n=None,  # n을 비워두면 필요한 표본 수를 역산
    )
    if result is not None and not pd.isna(result):
        return int(round(result)), None

    # Fallback: 효과가 너무 커서 통상적 탐색 범위 밖(예: n<2)에 해가 있는 경우
    scan = {}
    for n in range(3, 21):
        achieved = pg.power_rm_anova(
            eta_squared=partial_eta_sq, m=n_styles, n=n, corr=mean_corr, alpha=alpha
        )
        scan[n] = round(achieved, 4)
    return None, scan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="15샘플 재실행 결과 CSV 경로")
    parser.add_argument("--target-power", type=float, default=0.8)
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    required_cols = {"scenario_id", "style_condition", "ccer_score"}
    if not required_cols.issubset(df.columns):
        sys.exit(f"입력 CSV에 다음 컬럼이 필요합니다: {required_cols}")

    stats = compute_effect_size(df)
    print("=== 15샘플 파일럿 기반 효과 크기 추정 ===")
    print(f"Partial eta-squared: {stats['partial_eta_sq']:.4f}")
    print(f"파일럿 시나리오 수: {stats['n_scenarios_pilot']}")
    print(f"스타일 수: {stats['n_styles']}")
    print(f"스타일 간 평균 상관계수: {stats['mean_within_scenario_corr']:.4f}")
    print()
    print(stats["anova_table"])
    print()

    needed_n, scan = required_n_for_power(
        stats["partial_eta_sq"], stats["n_styles"], stats["mean_within_scenario_corr"],
        target_power=args.target_power, alpha=args.alpha
    )
    print(f"=== Power={args.target_power}, alpha={args.alpha} 달성에 필요한 시나리오 수 ===")
    if needed_n is not None:
        print(f"필요 시나리오 수(scenario, 시나리오당 3스타일): {needed_n}")
        print(f"→ 총 샘플 수(시나리오 × 스타일 3): {needed_n * stats['n_styles']}")
    else:
        print("효과 크기가 매우 커서 통상적 탐색 범위 밖에 해가 있습니다.")
        print("대신 시나리오 수(n)별 달성 power를 스캔한 결과:")
        for n, power in scan.items():
            flag = "  <- 목표 달성" if power >= args.target_power else ""
            print(f"  n={n:>2} (총 샘플 {n*stats['n_styles']:>3}): power={power}{flag}")


if __name__ == "__main__":
    main()
