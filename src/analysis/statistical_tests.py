"""
50-Scenario Statistical Testing (Repeated-Measures)

목적: 시나리오 하나가 3개 스타일에 반복 측정되는 구조(repeated-measures)를
반영해서, 스타일 간 CCER 차이를 검정한다.

1. Friedman test (비모수, repeated-measures) — 3개 스타일 간 전체 차이
2. 유의하면 Wilcoxon signed-rank pairwise comparison (3쌍) + Holm 보정
3. 효과 크기: Friedman -> Kendall's W, Wilcoxon -> matched-pairs
   rank-biserial correlation(RBC)
4. 보조 분석: Mixed-effects model (CCER ~ style + (1|scenario_id))
   — random intercept per scenario, style를 고정효과로

Primary analysis는 원본 v3 CCER(results/full_50/ccer_results.csv)로 진행하고,
intervention artifact 14건 제외 버전(docs/limitations.md #13 대응,
results/full_50/sensitivity_exclude_boundary_artifacts.csv)은 별도
sensitivity analysis로 동일한 절차를 반복해 결과를 대조한다.

사용법:
    python -m src.analysis.statistical_tests
"""

import warnings
from pathlib import Path

import pandas as pd
import pingouin as pg
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

warnings.filterwarnings("ignore", category=FutureWarning)

RESULTS_DIR = Path("results/full_50")
STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]


def run_friedman(long_df: pd.DataFrame, label: str) -> dict:
    """Friedman test + Kendall's W."""
    result = pg.friedman(data=long_df, dv="ccer_score", within="style_condition",
                          subject="scenario_id")
    row = result.iloc[0]
    print(f"\n=== [{label}] Friedman Test ===")
    print(result)
    print(f"Kendall's W (효과 크기): {row['W']:.4f}")
    return {"label": label, "Q": row["Q"], "p_unc": row["p_unc"], "kendalls_w": row["W"]}


def run_wilcoxon_pairwise(wide_df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Wilcoxon signed-rank pairwise comparison (3쌍) + Holm 보정."""
    pairs = [(STYLES[i], STYLES[j]) for i in range(len(STYLES)) for j in range(i + 1, len(STYLES))]
    rows = []
    for a, b in pairs:
        res = pg.wilcoxon(wide_df[a], wide_df[b])
        rows.append({
            "pair": f"{a} vs {b}",
            "W_stat": res["W_val"].iloc[0],
            "p_unc": res["p_val"].iloc[0],
            "RBC_effect_size": res["RBC"].iloc[0],
        })
    df = pd.DataFrame(rows)
    reject, p_holm, _, _ = multipletests(df["p_unc"], method="holm")
    df["p_holm"] = p_holm
    df["significant_after_holm"] = reject

    print(f"\n=== [{label}] Wilcoxon Signed-Rank Pairwise (Holm 보정) ===")
    print(df.to_string(index=False))
    return df


def run_mixed_effects(long_df: pd.DataFrame, label: str):
    """보조 분석: CCER ~ style + (1|scenario_id)"""
    df = long_df.copy()
    df["style_condition"] = pd.Categorical(df["style_condition"], categories=STYLES)
    model = smf.mixedlm("ccer_score ~ style_condition", data=df, groups=df["scenario_id"])
    fit = model.fit()
    print(f"\n=== [{label}] Mixed-Effects Model (CCER ~ style + (1|scenario_id)) ===")
    print(fit.summary())
    return fit


def analyze(ccer_col: str, label: str, source_path: Path):
    df = pd.read_csv(source_path, dtype={"scenario_id": str}, encoding="utf-8-sig")

    # 공식 ccer_eval.py 출력은 scenario_id 대신 sample_id만 갖고 있으므로 파생한다
    # (sample_id 예: "scenario_001_clinical_charting" -> scenario_id "001")
    if "scenario_id" not in df.columns:
        df["scenario_id"] = df["sample_id"].str.split("_").str[1]

    long_df = df[["scenario_id", "style_condition", ccer_col]].rename(
        columns={ccer_col: "ccer_score"}
    )
    wide_df = long_df.pivot(index="scenario_id", columns="style_condition", values="ccer_score")
    wide_df = wide_df[STYLES]  # 열 순서 고정

    friedman_result = run_friedman(long_df, label)

    if friedman_result["p_unc"] < 0.05:
        print(f"\n[{label}] Friedman test 유의(p<0.05) -> Wilcoxon pairwise 진행")
        wilcoxon_result = run_wilcoxon_pairwise(wide_df, label)
    else:
        print(f"\n[{label}] Friedman test 비유의(p>=0.05) -> Wilcoxon pairwise는 참고용으로만 진행")
        wilcoxon_result = run_wilcoxon_pairwise(wide_df, label)

    run_mixed_effects(long_df, label)

    return friedman_result, wilcoxon_result


def main():
    print("#" * 70)
    print("# Primary Analysis: 원본 v3 CCER (results/full_50/ccer_results.csv)")
    print("#" * 70)
    analyze("ccer_score", "Primary (v3 원본)", RESULTS_DIR / "ccer_results.csv")

    print("\n\n")
    print("#" * 70)
    print("# Sensitivity Analysis: intervention artifact 14건 제외")
    print("# (docs/limitations.md #13 대응, results/full_50/sensitivity_exclude_boundary_artifacts.csv)")
    print("#" * 70)
    analyze("ccer_score_excl_boundary_artifacts", "Sensitivity (14건 제외)",
            RESULTS_DIR / "sensitivity_exclude_boundary_artifacts.csv")


if __name__ == "__main__":
    main()
