"""
Hybrid Follow-up Analysis (docs/hybrid_followup_spec.md Sec 4)

Hybrid(exploratory) 100개 샘플을 기존 v4 frozen 결과(results/full_100_v4/)와
비교한다. results/full_100_v4/ 자체는 절대 재계산/덮어쓰지 않는다 —
기존 evaluation 스크립트의 순수 계산 함수만 import해 재사용하고, Hybrid
전용으로 새로 저장한다.

H1: Hybrid의 aggregate micro-CCER는 Formal Template보다 낮다.
H2 (방향성): Hybrid의 vital-sign error rate는 Formal 대비 실질적으로
    증가하지 않는 방향을 보일 것으로 예상한다.
H3 (방향성): Hybrid의 device/dose/route error rate는 Formal보다 낮아지고
    Clinical Charting 방향으로 이동할 것으로 예상한다.

Primary descriptive: aggregate micro-CCER (Formal/Clinical/Telegraphic와
나란히 비교)
Primary inferential: scenario-level paired Wilcoxon, Hybrid vs Formal (n=100)
Secondary: macro-CCER, Entity P/R/F1, normalized WER, entity_type별 오류율
    (H2/H3는 effect size로만 보고 - p>.05를 동등성 근거로 쓰지 않음)

사용법:
    python -m src.analysis.hybrid_followup
"""

import json
import glob
from collections import defaultdict

import pandas as pd
from scipy.stats import wilcoxon

from src.evaluation.wer_eval import (
    load_gold_transcripts, load_whisper_transcripts, compute_wer_results
)
from src.evaluation.entity_eval import compute_prf1
from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.ccer_eval import compute_ccer, ERROR_WEIGHTS

OUTPUT_DIR = "results/hybrid_followup"
V4_DIR = "results/full_100_v4"


def compute_hybrid_wer():
    gold = load_gold_transcripts("data/generated_text")
    whisper = load_whisper_transcripts("data/stt_transcripts")
    gold_hybrid = {k: v for k, v in gold.items() if v["style_condition"] == "hybrid"}
    whisper_hybrid = {k: v for k, v in whisper.items() if k in gold_hybrid}
    results = compute_wer_results(gold_hybrid, whisper_hybrid)
    df = pd.DataFrame(results)
    return df


def compute_hybrid_entity_and_ccer():
    """Hybrid 100개의 sample별 flatten_all_matches 레코드, CCER, entity_type 집계."""
    per_sample_records = {}
    per_sample_ccer = []

    for path in sorted(glob.glob("data/entities/scenario_*_hybrid_matched.json")):
        d = json.load(open(path, encoding="utf-8"))
        sample_id = d["sample_id"]
        scenario_id = sample_id.split("_hybrid")[0]
        records = flatten_all_matches(d)
        per_sample_records[sample_id] = records
        result = compute_ccer(records)
        per_sample_ccer.append({
            "sample_id": sample_id,
            "scenario_id": scenario_id,
            "ccer_score": result["ccer_score"],
            "gold_entity_count": result["gold_entity_count"],
        })

    all_records = [r for recs in per_sample_records.values() for r in recs]
    return per_sample_records, pd.DataFrame(per_sample_ccer), all_records


def compute_entity_type_table(all_records):
    data = defaultdict(lambda: {"weighted_error": 0, "gold_count": 0})
    for r in all_records:
        et = r["entity_type"]
        if r["gold_value"] is not None:
            data[et]["gold_count"] += 1
        if r["error_type"] is not None:
            data[et]["weighted_error"] += ERROR_WEIGHTS.get(r["error_type"], 0)

    rows = []
    for et, info in sorted(data.items()):
        gold_n = info["gold_count"]
        rows.append({
            "entity_type": et,
            "gold_n": gold_n,
            "micro_ccer_hybrid": round(info["weighted_error"] / gold_n, 4) if gold_n else None,
        })
    return pd.DataFrame(rows)


def main():
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=== 1. WER (descriptive) ===")
    wer_df = compute_hybrid_wer()
    wer_df.to_csv(f"{OUTPUT_DIR}/wer_results.csv", index=False)
    print(f"Hybrid mean WER: raw={wer_df['wer_raw'].mean():.4f}, "
          f"normalized={wer_df['wer_normalized'].mean():.4f} (n={len(wer_df)})")

    print("\n=== 2. Entity-level P/R/F1 (descriptive) ===")
    per_sample_records, ccer_df, all_records = compute_hybrid_entity_and_ccer()
    prf1 = compute_prf1(all_records)
    print(f"Hybrid: P={prf1['precision']:.4f}, R={prf1['recall']:.4f}, F1={prf1['f1']:.4f}")

    print("\n=== 3. Micro-CCER (Primary descriptive outcome) ===")
    ccer_df.to_csv(f"{OUTPUT_DIR}/ccer_results.csv", index=False)
    total_gold = ccer_df["gold_entity_count"].sum()
    total_weighted = sum(
        ERROR_WEIGHTS.get(r["error_type"], 0) for r in all_records if r["error_type"] is not None
    )
    hybrid_micro_ccer = round(total_weighted / total_gold, 4)
    print(f"Hybrid aggregate micro-CCER: {hybrid_micro_ccer} (gold_entities={total_gold})")

    # v4 frozen 결과와 나란히 비교 (파일만 읽음, 절대 재계산/덮어쓰기 안 함)
    v4_ccer_summary = json.load(open(f"{V4_DIR}/ccer_summary.json", encoding="utf-8"))
    print("\n--- 4-way descriptive 비교 ---")
    for style in ["formal_template", "clinical_charting", "telegraphic_icu"]:
        print(f"{style:20s} micro-CCER={v4_ccer_summary[style]['ccer_score']}")
    print(f"{'hybrid':20s} micro-CCER={hybrid_micro_ccer}  <- H1 대상")

    print("\n=== 4. Macro-CCER (secondary robustness) ===")
    et_table = compute_entity_type_table(all_records)
    macro_ccer = et_table["micro_ccer_hybrid"].dropna().mean()
    et_table.to_csv(f"{OUTPUT_DIR}/entity_type_ccer_table.csv", index=False)
    print(f"Hybrid Macro-CCER (entity_type 균등 가중): {macro_ccer:.4f}")

    print("\n=== 5. Primary Inferential: scenario-level paired Wilcoxon (Hybrid vs Formal, n=100) ===")
    formal_ccer_df = pd.read_csv(f"{V4_DIR}/ccer_results.csv", encoding="utf-8-sig")
    formal_ccer_df = formal_ccer_df[formal_ccer_df["sample_id"].str.contains("formal_template")].copy()
    formal_ccer_df["scenario_id"] = formal_ccer_df["sample_id"].str.split("_formal_template").str[0]

    merged = ccer_df.merge(
        formal_ccer_df[["scenario_id", "ccer_score"]], on="scenario_id",
        suffixes=("_hybrid", "_formal")
    )
    merged.to_csv(f"{OUTPUT_DIR}/hybrid_vs_formal_paired.csv", index=False)

    stat, p = wilcoxon(merged["ccer_score_hybrid"], merged["ccer_score_formal"])
    diffs = merged["ccer_score_hybrid"] - merged["ccer_score_formal"]
    n_lower = (diffs < 0).sum()
    n_higher = (diffs > 0).sum()
    n_tied = (diffs == 0).sum()
    print(f"n={len(merged)}쌍, Wilcoxon W={stat:.2f}, p={p:.4g}")
    print(f"Hybrid < Formal(CCER 개선): {n_lower}건, Hybrid > Formal(악화): {n_higher}건, 동률: {n_tied}건")
    print(f"평균 차이(Hybrid - Formal): {diffs.mean():.4f}")

    print("\n=== 6. H2/H3: entity_type별 effect size (Formal/Clinical과 3-way 비교) ===")
    v4_et_table = pd.read_csv(f"{V4_DIR}/sap5_entity_type_ccer_table.csv", encoding="utf-8-sig")
    compare = et_table.merge(
        v4_et_table[["entity_type", "micro_ccer_formal_template", "micro_ccer_clinical_charting"]],
        on="entity_type", how="left"
    )
    compare["hybrid_minus_formal"] = compare["micro_ccer_hybrid"] - compare["micro_ccer_formal_template"]
    compare.to_csv(f"{OUTPUT_DIR}/entity_type_comparison_h2_h3.csv", index=False)
    print(compare[["entity_type", "micro_ccer_formal_template", "micro_ccer_hybrid",
                    "micro_ccer_clinical_charting", "hybrid_minus_formal"]].to_string(index=False))

    print(f"\n저장 완료: {OUTPUT_DIR}/ 에 6개 파일")


if __name__ == "__main__":
    main()
