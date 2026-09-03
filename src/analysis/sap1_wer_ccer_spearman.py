"""
SAP #1: WER-CCER Association (Spearman, scenario-level cluster bootstrap CI)

docs/statistical_analysis_plan.md §1 확정 내용을 그대로 구현.

- Pooled Spearman rho (n=300) + scenario-level cluster bootstrap 95% CI
  (100개 scenario_id를 복원추출, 뽑힌 scenario의 3개 스타일 행을 전부 포함)
- Style별 Spearman rho (각 n=100) + scenario-level bootstrap 95% CI
  (100개 scenario_id를 복원추출, 해당 style의 값만 사용)
- 5,000 replicates, percentile method

사용법:
    python -m src.analysis.sap1_wer_ccer_spearman --results-dir results/full_100
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

N_BOOTSTRAP = 5000
RNG_SEED = 42
STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]


def load_merged(results_dir: Path) -> pd.DataFrame:
    wer = pd.read_csv(results_dir / "wer_results.csv", encoding="utf-8-sig",
                       dtype={"scenario_id": str})
    ccer = pd.read_csv(results_dir / "ccer_results.csv", encoding="utf-8-sig")
    ccer["scenario_id"] = ccer["sample_id"].str.split("_").str[1]
    merged = wer[["sample_id", "scenario_id", "style_condition", "wer_normalized"]].merge(
        ccer[["sample_id", "ccer_score"]], on="sample_id"
    )
    return merged


def pooled_bootstrap_ci(df: pd.DataFrame, n_boot: int = N_BOOTSTRAP, seed: int = RNG_SEED):
    scenario_ids = df["scenario_id"].unique()
    rng = np.random.default_rng(seed)
    boot_rhos = []
    for _ in range(n_boot):
        sampled_scenarios = rng.choice(scenario_ids, size=len(scenario_ids), replace=True)
        # 뽑힌 scenario의 3개 스타일 행 전부 포함 (repeated-measures 구조 보존)
        boot_df = pd.concat([df[df["scenario_id"] == sid] for sid in sampled_scenarios],
                             ignore_index=True)
        rho, _ = spearmanr(boot_df["wer_normalized"], boot_df["ccer_score"])
        boot_rhos.append(rho)
    boot_rhos = np.array(boot_rhos)
    ci_low, ci_high = np.percentile(boot_rhos, [2.5, 97.5])
    return ci_low, ci_high, boot_rhos


def style_bootstrap_ci(style_df: pd.DataFrame, n_boot: int = N_BOOTSTRAP, seed: int = RNG_SEED):
    scenario_ids = style_df["scenario_id"].values
    wer_vals = style_df.set_index("scenario_id")["wer_normalized"]
    ccer_vals = style_df.set_index("scenario_id")["ccer_score"]
    rng = np.random.default_rng(seed)
    boot_rhos = []
    for _ in range(n_boot):
        sampled = rng.choice(scenario_ids, size=len(scenario_ids), replace=True)
        rho, _ = spearmanr(wer_vals.loc[sampled], ccer_vals.loc[sampled])
        boot_rhos.append(rho)
    boot_rhos = np.array(boot_rhos)
    ci_low, ci_high = np.percentile(boot_rhos, [2.5, 97.5])
    return ci_low, ci_high, boot_rhos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=str, default="results/full_100")
    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    df = load_merged(results_dir)
    print(f"총 샘플 수: {len(df)} (시나리오 {df['scenario_id'].nunique()}개 x 스타일 {df['style_condition'].nunique()}개)")

    print(f"\n{'=' * 70}\nPooled Spearman (n={len(df)})\n{'=' * 70}")
    rho, p = spearmanr(df["wer_normalized"], df["ccer_score"])
    ci_low, ci_high, _ = pooled_bootstrap_ci(df)
    print(f"Spearman rho = {rho:.4f} (p={p:.4g}, 참고용)")
    print(f"95% CI (scenario-level cluster bootstrap, {N_BOOTSTRAP} replicates): [{ci_low:.4f}, {ci_high:.4f}]")

    results = {"pooled": {"n": len(df), "rho": rho, "ci_low": ci_low, "ci_high": ci_high}}

    print(f"\n{'=' * 70}\nStyle별 Spearman\n{'=' * 70}")
    for style in STYLES:
        style_df = df[df["style_condition"] == style]
        rho_s, p_s = spearmanr(style_df["wer_normalized"], style_df["ccer_score"])
        ci_low_s, ci_high_s, _ = style_bootstrap_ci(style_df)
        print(f"{style:20s}: rho={rho_s:.4f} (n={len(style_df)}), "
              f"95% CI=[{ci_low_s:.4f}, {ci_high_s:.4f}]")
        results[style] = {"n": len(style_df), "rho": rho_s, "ci_low": ci_low_s, "ci_high": ci_high_s}

    out_path = results_dir / "sap1_wer_ccer_spearman.csv"
    pd.DataFrame(results).T.to_csv(out_path)
    print(f"\n저장 완료: {out_path}")

    return results


if __name__ == "__main__":
    main()
