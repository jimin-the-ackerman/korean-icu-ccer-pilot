"""
Cross-ASR analysis (docs/cross_asr_spec.md Sections 6, 7, 11.4, 11.5, 12.3). No API call.

Reads the per-sample match files written by the v4 evaluator and recomputes, with the v4 weights
(src.evaluation.ccer_eval.ERROR_WEIGHTS) and the v4 record definitions
(src.evaluation.flatten_matches.flatten_all_matches):

  1. pooled micro-CCER per condition x style (sum of weighted errors / sum of gold entities), with
     sample-level mean CCER reported separately (labelled);
  2. Delta_FC = Formal - Clinical, Delta_FT = Formal - Telegraphic (primary) and Delta_CT =
     Clinical - Telegraphic (secondary), each with a 95% percentile CI from a joint scenario-level
     bootstrap (same resampled scenario indices for every condition and style; pooled values
     recomputed in each resample);
  3. between-system differences of Delta (secondary, same joint bootstrap);
  4. Friedman + Kendall's W and Wilcoxon signed-rank + Holm with matched-pairs rank-biserial
     correlation on sample-level CCER, as in v4 (src/analysis/statistical_tests.py);
  5. sensitivity analysis without the suspected TTS-defect scenarios 007 and 063 (all three styles);
  6. cross-run comparison of the September v4 whisper-1 evaluation with the November re-evaluation;
  7. Condition B (language not specified): descriptive only, for the pre-specified pilot 30 and for
     the 300-sample extension (labelled as such).

The pooled values are checked against each condition's ccer_summary.json (rounded to 4 decimals);
any mismatch stops the analysis.

Output: results/cross_asr/analysis/  (stops if the folder already exists; use --out for another)
Usage:  python -m src.cross_asr.analysis
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.cross_asr.common import load_cross_asr_config, primary_samples, git_commit, now_utc
from src.evaluation.ccer_eval import ERROR_WEIGHTS
from src.evaluation.flatten_matches import flatten_all_matches

warnings.filterwarnings("ignore", category=FutureWarning)

STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]
SHORT = {"formal_template": "F", "clinical_charting": "C", "telegraphic_icu": "T"}
COND_A = ["whisper1", "gpt4o_transcribe", "chirp3_ko"]
COND_B = ["whisper1_auto", "gpt4o_transcribe_auto", "chirp3_auto"]
B_PAIR = dict(zip(COND_B, COND_A))
V4_LABEL = "whisper1_v4_sept"          # September v4 evaluation of the same whisper-1 transcripts
TTS_SUSPECT_SCENARIOS = ["scenario_007", "scenario_063"]   # spec 12.3
DELTAS = {"Delta_FC": ("formal_template", "clinical_charting"),
          "Delta_FT": ("formal_template", "telegraphic_icu"),
          "Delta_CT": ("clinical_charting", "telegraphic_icu")}


# ---------- data ----------

def sample_scores(match_path: Path) -> tuple[float, int]:
    """Weighted error sum and gold count of one sample, exactly as compute_ccer() counts them."""
    recs = flatten_all_matches(json.load(open(match_path, encoding="utf-8")))
    gold = sum(1 for r in recs if r["gold_value"] is not None)
    weighted = sum(ERROR_WEIGHTS.get(r["error_type"], 0) for r in recs if r["error_type"] is not None)
    return float(weighted), gold


def load_condition(ent_dir: Path, samples: list) -> pd.DataFrame | None:
    rows = []
    for s in samples:
        p = ent_dir / f"{s['sample_id']}_matched.json"
        if not p.exists():
            return None
        w, g = sample_scores(p)
        rows.append({**s, "weighted": w, "gold": g, "ccer": w / g if g else 0.0})
    return pd.DataFrame(rows)


def check_against_summary(df: pd.DataFrame, summary_path: Path, label: str) -> None:
    summ = json.load(open(summary_path, encoding="utf-8"))
    for st in STYLES:
        d = df[df.style_condition == st]
        pooled = round(d.weighted.sum() / d.gold.sum(), 4)
        if pooled != summ[st]["ccer_score"] or int(d.gold.sum()) != summ[st]["gold_entity_count"]:
            raise SystemExit(f"STOP: {label} {st}: recomputed {pooled} (gold {int(d.gold.sum())}) vs "
                             f"{summary_path} {summ[st]['ccer_score']} (gold {summ[st]['gold_entity_count']})")


# ---------- pooled CCER and bootstrap ----------

def arrays(df: pd.DataFrame, scenarios: list) -> tuple[np.ndarray, np.ndarray]:
    """W, G with shape (3 styles, n scenarios)."""
    w = df.pivot(index="scenario_id", columns="style_condition", values="weighted").loc[scenarios, STYLES]
    g = df.pivot(index="scenario_id", columns="style_condition", values="gold").loc[scenarios, STYLES]
    return w.to_numpy().T, g.to_numpy(dtype=float).T


def pooled_table(data: dict, scenarios: list) -> pd.DataFrame:
    rows = []
    for cond, df in data.items():
        d = df[df.scenario_id.isin(scenarios)]
        for st in STYLES:
            x = d[d.style_condition == st]
            rows.append({"condition": cond, "style": st, "n_samples": len(x),
                         "gold_entities": int(x.gold.sum()), "weighted_errors": x.weighted.sum(),
                         "pooled_micro_ccer": round(x.weighted.sum() / x.gold.sum(), 4),
                         "sample_mean_ccer": round(x.ccer.mean(), 4)})
    return pd.DataFrame(rows)


def joint_bootstrap(data: dict, scenarios: list, n_boot: int, seed: int, ci: float) -> tuple[pd.DataFrame, dict]:
    """Same resampled scenario indices for every condition and style (spec Section 7)."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(scenarios), size=(n_boot, len(scenarios)))
    lo_q, hi_q = 100 * (1 - ci) / 2, 100 * (1 + ci) / 2
    rows, boot = [], {}
    for cond, df in data.items():
        W, G = arrays(df, scenarios)
        point = W.sum(1) / G.sum(1)
        bw, bg = W[:, idx].sum(2), G[:, idx].sum(2)          # (3, n_boot)
        bc = bw / bg
        boot[cond] = bc
        for name, (a, b) in DELTAS.items():
            ia, ib = STYLES.index(a), STYLES.index(b)
            dist = bc[ia] - bc[ib]
            rows.append({"condition": cond, "contrast": name,
                         "role": "primary" if name != "Delta_CT" else "secondary",
                         "estimate": round(point[ia] - point[ib], 4),
                         "ci_low": round(np.percentile(dist, lo_q), 4),
                         "ci_high": round(np.percentile(dist, hi_q), 4),
                         "ci_excludes_0": bool(np.percentile(dist, lo_q) > 0 or np.percentile(dist, hi_q) < 0)})
    return pd.DataFrame(rows), boot


def delta_differences(boot: dict, data: dict, scenarios: list, pairs: list, ci: float) -> pd.DataFrame:
    lo_q, hi_q = 100 * (1 - ci) / 2, 100 * (1 + ci) / 2
    rows = []
    for c1, c2 in pairs:
        if c1 not in boot or c2 not in boot:
            continue
        W1, G1 = arrays(data[c1], scenarios)
        W2, G2 = arrays(data[c2], scenarios)
        p1, p2 = W1.sum(1) / G1.sum(1), W2.sum(1) / G2.sum(1)
        for name, (a, b) in DELTAS.items():
            ia, ib = STYLES.index(a), STYLES.index(b)
            dist = (boot[c1][ia] - boot[c1][ib]) - (boot[c2][ia] - boot[c2][ib])
            rows.append({"comparison": f"{c1} - {c2}", "contrast": name,
                         "estimate": round((p1[ia] - p1[ib]) - (p2[ia] - p2[ib]), 4),
                         "ci_low": round(np.percentile(dist, lo_q), 4),
                         "ci_high": round(np.percentile(dist, hi_q), 4)})
    return pd.DataFrame(rows)


# ---------- tests (as in v4) ----------

def v4_tests(df: pd.DataFrame, label: str) -> tuple[dict, pd.DataFrame]:
    import pingouin as pg
    from statsmodels.stats.multitest import multipletests
    long = df[["scenario_id", "style_condition", "ccer"]].rename(columns={"ccer": "ccer_score"})
    fr = pg.friedman(data=long, dv="ccer_score", within="style_condition", subject="scenario_id").iloc[0]
    wide = long.pivot(index="scenario_id", columns="style_condition", values="ccer_score")[STYLES]
    rows = []
    for i in range(3):
        for j in range(i + 1, 3):
            res = pg.wilcoxon(wide[STYLES[i]], wide[STYLES[j]])
            rows.append({"condition": label, "pair": f"{SHORT[STYLES[i]]} vs {SHORT[STYLES[j]]}",
                         "W_stat": res["W_val"].iloc[0], "p_unc": res["p_val"].iloc[0],
                         "RBC": res["RBC"].iloc[0]})
    w = pd.DataFrame(rows)
    w["p_holm"] = multipletests(w["p_unc"], method="holm")[1]
    fr_row = {"condition": label, "n_scenarios": wide.shape[0], "Q": fr["Q"], "p_unc": fr["p_unc"],
              "kendalls_W": fr["W"]}
    return fr_row, w


def rank_string(pooled: pd.DataFrame, cond: str) -> str:
    d = pooled[pooled.condition == cond].sort_values("pooled_micro_ccer")
    return " < ".join(SHORT[s] for s in d["style"])


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="output folder (default results/cross_asr/analysis)")
    args = ap.parse_args()

    cfg = load_cross_asr_config()
    acfg = cfg["analysis"]
    n_boot, seed, ci = int(acfg["bootstrap_iterations"]), int(acfg["bootstrap_seed"]), float(acfg["ci_level"])
    out = Path(args.out or Path(cfg["paths"]["results_root"]) / "analysis")
    if out.exists():
        print(f"STOP: {out} already exists (not overwritten) - use --out for a new folder")
        return 1

    samples = primary_samples(cfg)
    scenarios = sorted({s["scenario_id"] for s in samples})
    root, res_root = Path(cfg["paths"]["output_root"]), Path(cfg["paths"]["results_root"])

    data, missing = {}, []
    v4 = load_condition(Path(cfg["paths"]["original_entities_dir"]), samples)
    check_against_summary(v4, Path(cfg["paths"]["original_results_dir"]) / "ccer_summary.json", V4_LABEL)
    data[V4_LABEL] = v4
    for cond in COND_A + COND_B:
        df = load_condition(root / cond / "entities", samples)
        if df is None:
            missing.append(cond)
            continue
        check_against_summary(df, res_root / cond / "ccer_summary.json", cond)
        data[cond] = df
    print(f"conditions analysed : {list(data)}")
    print(f"not complete (skipped): {missing or 'none'}")
    print(f"check vs ccer_summary.json: OK for all analysed conditions")
    print(f"bootstrap: {n_boot} resamples of {len(scenarios)} scenarios, seed {seed}, {int(ci * 100)}% percentile CI")

    out.mkdir(parents=True)
    a_conds = [c for c in [V4_LABEL] + COND_A if c in data]
    sens_scen = [s for s in scenarios if s not in TTS_SUSPECT_SCENARIOS]

    # 1-3: primary (Condition A + September reference) and sensitivity
    results = {}
    for tag, scen in (("primary", scenarios), ("sensitivity_excl_007_063", sens_scen)):
        sub = {c: data[c] for c in a_conds}
        pooled = pooled_table(sub, scen)
        deltas, boot = joint_bootstrap(sub, scen, n_boot, seed, ci)
        ddiff = delta_differences(boot, sub, scen,
                                  [(a, b) for i, a in enumerate(COND_A) for b in COND_A[i + 1:]], ci)
        pooled.to_csv(out / f"condA_pooled_ccer_{tag}.csv", index=False)
        deltas.to_csv(out / f"condA_delta_bootstrap_{tag}.csv", index=False)
        ddiff.to_csv(out / f"condA_delta_between_systems_{tag}.csv", index=False)
        fr_rows, wil = [], []
        for c in a_conds:
            f, w = v4_tests(sub[c][sub[c].scenario_id.isin(scen)], c)
            fr_rows.append(f)
            wil.append(w)
        pd.DataFrame(fr_rows).to_csv(out / f"condA_friedman_{tag}.csv", index=False)
        pd.concat(wil).to_csv(out / f"condA_wilcoxon_holm_{tag}.csv", index=False)
        results[tag] = (pooled, deltas, ddiff, pd.DataFrame(fr_rows), pd.concat(wil))

    # 6: cross-run (September v4 vs November re-evaluation of the same whisper-1 transcripts)
    if "whisper1" in data:
        m = data[V4_LABEL].merge(data["whisper1"], on=["sample_id", "scenario_id", "style_condition"],
                                 suffixes=("_v4", "_nov"))
        xr = {"identical_sample_ccer": int((m.ccer_v4 == m.ccer_nov).sum()), "n_samples": len(m),
              "max_abs_sample_change": round(float((m.ccer_nov - m.ccer_v4).abs().max()), 4),
              "gold_count_changed": m.loc[m.gold_v4 != m.gold_nov, "sample_id"].tolist()}
        json.dump(xr, open(out / "crossrun_whisper1_sept_vs_nov.json", "w", encoding="utf-8"), indent=2)

    # 7: Condition B descriptive (pilot 30 = pre-specified; 300 = extension, spec 11.5)
    pilot = json.load(open(root / "pilot_samples.json", encoding="utf-8"))["sample_ids"]
    pilot_scen = sorted({"_".join(s.split("_")[:2]) for s in pilot})
    b_rows = []
    for b in COND_B:
        a = B_PAIR[b]
        if b not in data or a not in data:
            continue
        for scope, scen in (("pilot30_prespecified", pilot_scen), ("all300_extension", scenarios)):
            pa, pb = pooled_table({a: data[a]}, scen), pooled_table({b: data[b]}, scen)
            for st in STYLES:
                va = pa[pa["style"] == st].pooled_micro_ccer.iloc[0]
                vb = pb[pb["style"] == st].pooled_micro_ccer.iloc[0]
                b_rows.append({"scope": scope, "system": a, "style": st, "ko_specified": va,
                               "not_specified": vb, "difference_B_minus_A": round(vb - va, 4)})
    bdf = pd.DataFrame(b_rows)
    if len(bdf):
        bdf.to_csv(out / "condB_descriptive.csv", index=False)

    meta = {"created_at": now_utc(), "git_commit": git_commit(), "config_version": cfg["version"],
            "bootstrap": {"iterations": n_boot, "seed": seed, "ci": ci}, "conditions": list(data),
            "skipped_incomplete": missing, "sensitivity_excluded_scenarios": TTS_SUSPECT_SCENARIOS,
            "note": "pooled micro-CCER = sum weighted errors / sum gold entities (v4 formula); "
                    "sample_mean_ccer is the mean of sample-level CCER (used by Friedman/Wilcoxon, as in v4)"}
    json.dump(meta, open(out / "analysis_meta.json", "w", encoding="utf-8"), indent=2)

    # ---------- console summary ----------
    pd.set_option("display.width", 160)
    for tag in results:
        pooled, deltas, ddiff, fr, wil = results[tag]
        print("\n" + "=" * 100 + f"\n[{tag}] pooled micro-CCER (rank by style)")
        tab = pooled.pivot(index="condition", columns="style", values="pooled_micro_ccer")[STYLES].loc[a_conds]
        tab["rank"] = [rank_string(pooled, c) for c in tab.index]
        print(tab.to_string())
        print(f"\n[{tag}] Delta with {int(ci * 100)}% joint scenario bootstrap CI (negative = first style lower)")
        print(deltas.to_string(index=False))
        print(f"\n[{tag}] between-system differences of Delta (secondary)")
        print(ddiff.to_string(index=False))
        print(f"\n[{tag}] Friedman (sample-level CCER, as in v4)")
        print(fr.round(6).to_string(index=False))
        print(f"\n[{tag}] Wilcoxon signed-rank + Holm")
        print(wil.round(6).to_string(index=False))
    if "whisper1" in data:
        print("\n" + "=" * 100 + f"\ncross-run whisper-1 (Sept v4 vs Nov): {xr}")
    if len(bdf):
        print("\n" + "=" * 100 + "\nCondition B (descriptive; pilot30 pre-specified, all300 = extension)")
        print(bdf.to_string(index=False))
    print(f"\nwritten: {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
