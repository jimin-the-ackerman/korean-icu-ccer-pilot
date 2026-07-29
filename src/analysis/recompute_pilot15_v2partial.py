"""
2주차: 기존 15샘플 매칭 데이터에 v2 CCER 로직(hallucination penalty) 재적용

주의(중요): 이 스크립트는 hallucination penalty 수정만 반영한다.
phonetic_artifact 재판정(limitation #5)은 semantic_matcher.py의 프롬프트가
바뀐 것이라, Claude API를 다시 호출해 open_vocab_matches를 재생성해야
반영된다 — 이 샌드박스에는 API 키가 없어 실행할 수 없으므로, 사용자의
로컬 환경에서 `src/matching/run_semantic_matching.py`를 재실행한 뒤
이 스크립트를 다시 돌려야 완전한 v2 숫자가 된다.

지금 이 스크립트가 만드는 숫자는 "hallucination penalty만 반영된 v2 잠정치"이며,
검정력 분석의 방향성(50 vs 100 결정)을 위한 참고용이다. phonetic_artifact까지
반영되면 숫자는 소폭 달라질 수 있다(주로 omission 쪽으로 재분류되는 항목이
늘어나 CCER이 다소 상승할 가능성).
"""

import json
from pathlib import Path

import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.ccer_eval import compute_ccer

ENTITIES_DIR = Path("data/entities")
OUTPUT_CSV = Path("results/pilot_15/ccer_results_v2_partial.csv")


def main():
    rows = []
    matched_files = sorted(ENTITIES_DIR.glob("scenario_*_matched.json"))
    print(f"발견된 matched.json 파일 수: {len(matched_files)}")

    for path in matched_files:
        with open(path, encoding="utf-8") as f:
            matched_data = json.load(f)

        sample_id = matched_data["sample_id"]  # e.g. scenario_001_formal_template
        parts = sample_id.split("_")
        scenario_id = parts[1]  # "001"
        style_condition = "_".join(parts[2:])  # "formal_template" 등

        records = flatten_all_matches(matched_data)
        result = compute_ccer(records)

        rows.append({
            "scenario_id": scenario_id,
            "style_condition": style_condition,
            "ccer_score": result["ccer_score"],
            "gold_entity_count": result["gold_entity_count"],
            "hallucination_count": result["error_type_profile"].get("hallucination", 0),
            "error_type_profile": json.dumps(result["error_type_profile"], ensure_ascii=False),
        })

    df = pd.DataFrame(rows).sort_values(["scenario_id", "style_condition"])
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)

    print(f"\n저장 완료: {OUTPUT_CSV}")
    print(f"\n=== 스타일별 요약 ===")
    summary = df.groupby("style_condition").agg(
        mean_ccer=("ccer_score", "mean"),
        std_ccer=("ccer_score", "std"),
        total_hallucinations=("hallucination_count", "sum"),
    ).round(4)
    print(summary)

    print(f"\n=== 전체 데이터 ===")
    print(df[["scenario_id", "style_condition", "ccer_score", "hallucination_count"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
