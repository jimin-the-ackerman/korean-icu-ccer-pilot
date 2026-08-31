"""
v3 (taxonomy-aligned) CCER 재계산

docs/taxonomy_audit.md §6(Versioning & Traceability 계획)에 따라, 15샘플
전체를 v3 코드(scaffold_as_gold.py/open_vocab_extractor.py/semantic_matcher.py/
flatten_matches.py/ccer_eval.py 전부 반영)로 재매칭한 뒤, 그 결과를
results/pilot_15/v3_taxonomy_aligned/에 별도로 저장한다. 기존
v2_hallucination_phonetic/ 결과는 덮어쓰지 않는다.

전제: 이 스크립트를 돌리기 전에 로컬에서 아래 두 단계를 먼저 실행해서
data/entities/*_open.json, *_matched.json이 v3 코드로 갱신되어 있어야 한다.
    python -m src.entity_extraction.run_open_vocab_extraction
    python -m src.matching.run_semantic_matching

사용법:
    python -m src.analysis.recompute_pilot15_v3
"""

import json
from pathlib import Path

import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.ccer_eval import compute_ccer

ENTITIES_DIR = Path("data/entities")
OUTPUT_DIR = Path("results/pilot_15/v3_taxonomy_aligned")

# v2와 비교용 (이미 있으면 로드, 없으면 비교 생략)
V2_RESULT_PATH = Path("results/pilot_15/ccer_results_v2_partial.csv")


def main():
    rows = []
    matched_files = sorted(ENTITIES_DIR.glob("scenario_*_matched.json"))
    print(f"발견된 matched.json 파일 수: {len(matched_files)}")

    for path in matched_files:
        with open(path, encoding="utf-8") as f:
            matched_data = json.load(f)

        sample_id = matched_data["sample_id"]
        parts = sample_id.split("_")
        scenario_id = parts[1]
        style_condition = "_".join(parts[2:])

        records = flatten_all_matches(matched_data)
        result = compute_ccer(records)

        rows.append({
            "scenario_id": scenario_id,
            "style_condition": style_condition,
            "ccer_score": result["ccer_score"],
            "gold_entity_count": result["gold_entity_count"],
            "hallucination_count": result["error_type_profile"].get("hallucination", 0),
            "medication_identity_error_count": result["error_type_profile"].get("medication_identity_error", 0),
            "error_type_profile": json.dumps(result["error_type_profile"], ensure_ascii=False),
            "entity_types_present": json.dumps(sorted(result["entity_error_profile"].keys()), ensure_ascii=False),
        })

    df = pd.DataFrame(rows).sort_values(["scenario_id", "style_condition"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "ccer_results.csv", index=False)

    print(f"\n저장 완료: {OUTPUT_DIR / 'ccer_results.csv'}")
    print(f"\n=== v3 스타일별 요약 ===")
    summary = df.groupby("style_condition").agg(
        mean_ccer=("ccer_score", "mean"),
        std_ccer=("ccer_score", "std"),
        total_hallucinations=("hallucination_count", "sum"),
        total_medication_identity_errors=("medication_identity_error_count", "sum"),
    ).round(4)
    print(summary)
    summary.to_csv(OUTPUT_DIR / "style_summary.csv")

    # medication_identity/intake_output이 실제로 entity_error_profile에 등장하는지 확인
    all_entity_types = set()
    for et_json in df["entity_types_present"]:
        all_entity_types.update(json.loads(et_json))
    print(f"\n=== 전체 샘플에서 확인된 entity_type 목록 ===")
    print(sorted(all_entity_types))
    new_categories_present = {"medication_identity", "intake_output"} & all_entity_types
    print(f"신규 카테고리 등장 여부: {new_categories_present or '(둘 다 등장 안 함 - 데이터/코드 확인 필요)'}")

    # v2와 비교 (있으면)
    if V2_RESULT_PATH.exists():
        v2 = pd.read_csv(V2_RESULT_PATH)
        merged = df.merge(v2, on=["scenario_id", "style_condition"], suffixes=("_v3", "_v2"))
        merged["ccer_diff"] = merged["ccer_score_v3"] - merged["ccer_score_v2"]
        print(f"\n=== v2 대비 CCER 변화 (샘플별) ===")
        print(merged[["scenario_id", "style_condition", "ccer_score_v2", "ccer_score_v3", "ccer_diff"]]
              .to_string(index=False))
        merged.to_csv(OUTPUT_DIR / "v2_vs_v3_comparison.csv", index=False)
    else:
        print(f"\n(v2 결과 파일({V2_RESULT_PATH})을 찾을 수 없어 비교는 생략)")

    print(f"\n=== 전체 데이터 ===")
    print(df[["scenario_id", "style_condition", "ccer_score",
              "hallucination_count", "medication_identity_error_count"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
