"""
Sensitivity Check: Limitation #13(intervention 경계 누수) 14건 제외 시
스타일별 CCER 순위가 유지되는지 확인

목적: docs/limitations.md #13에서 규명한 14건의 intervention hallucination은
Whisper의 진짜 환각이 아니라 카테고리 경계 문제로 밝혀졌다(13건 taxonomy-
boundary + 1건 patient_context 변종). v3 taxonomy 자체는 이 발견 때문에
재수정하지 않지만(freeze 유지), 이 14건이 CCER 순위/유의성 결론에 실제로
영향을 미치는지는 별도로 확인할 가치가 있다 — 이는 taxonomy를 바꾸는 게
아니라, "이 14건을 포함해도/제외해도 핵심 결론이 바뀌지 않는가"라는
순수한 sensitivity(강건성) 확인이다.

v3 코드/데이터는 건드리지 않는다. 이 스크립트는 순수 분석용이며, 결과는
별도 CSV로 저장하고 기존 results/full_50/ccer_results.csv는 덮어쓰지
않는다.

사용법:
    python -m src.analysis.sensitivity_exclude_boundary_artifacts
"""

import json
import glob
from pathlib import Path

import pandas as pd

from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.ccer_eval import compute_ccer

ENTITIES_DIR = Path("data/entities")
OUTPUT_DIR = Path("results/full_50")

# docs/limitations.md #13에서 규명한 14건 (sample_id, whisper_value 정확히 매칭)
# 이 목록은 audit 과정에서 수작업으로 확인된 것이며, 코드가 자동으로
# "artifact"를 판별하는 것이 아니다 (그럴 경우 taxonomy를 결과에 맞춰
# 조정하는 것과 다를 바 없으므로, 이번 audit에서 사람이 직접 확인한
# 14건만 명시적으로 나열한다).
BOUNDARY_ARTIFACT_CASES = {
    ("scenario_020_clinical_charting", "Gastroenterology Consult 요청함"),
    ("scenario_021_clinical_charting", "스트릭트 모니터링 of intake and output"),
    ("scenario_021_telegraphic_icu", "IO 스트릭트 모니터링 (strict I/O monitoring)"),
    ("scenario_027_clinical_charting", "IV fluids initiated"),
    ("scenario_027_telegraphic_icu", "IV Fluids 시작"),
    ("scenario_029_clinical_charting", "호흡상태 밀착 모니터링"),
    ("scenario_031_telegraphic_icu", "GI specialist consult"),
    ("scenario_034_clinical_charting", "strict fluid balance monitoring"),
    ("scenario_034_telegraphic_icu", "Strict fluid balance monitoring"),
    ("scenario_044_clinical_charting", "PAIN TEAM CONSULT"),
    ("scenario_044_formal_template", "통증팀 컨설트"),
    ("scenario_048_clinical_charting", "strict monitoring of input and output"),
    ("scenario_048_telegraphic_icu", "strict monitoring"),
    ("scenario_049_telegraphic_icu", "ORTHOPEDIC CONSULT"),
}


def compute_both_versions():
    rows = []
    matched_files = sorted(ENTITIES_DIR.glob("scenario_*_matched.json"))
    excluded_count = 0

    for path in matched_files:
        with open(path, encoding="utf-8") as f:
            matched_data = json.load(f)
        sample_id = matched_data["sample_id"]
        parts = sample_id.split("_")
        scenario_id = parts[1]
        style_condition = "_".join(parts[2:])

        records = flatten_all_matches(matched_data)

        # 원본(as-is) CCER
        result_full = compute_ccer(records)

        # 14건 제외 버전
        filtered_records = [
            r for r in records
            if not (r["entity_type"] == "intervention"
                     and r["error_type"] == "hallucination"
                     and (sample_id, r["whisper_value"]) in BOUNDARY_ARTIFACT_CASES)
        ]
        n_removed = len(records) - len(filtered_records)
        excluded_count += n_removed
        result_filtered = compute_ccer(filtered_records)

        rows.append({
            "scenario_id": scenario_id,
            "style_condition": style_condition,
            "ccer_score_full": result_full["ccer_score"],
            "ccer_score_excl_boundary_artifacts": result_filtered["ccer_score"],
            "n_boundary_artifacts_removed": n_removed,
        })

    print(f"제외 대상으로 실제 매칭된 레코드 수: {excluded_count} / {len(BOUNDARY_ARTIFACT_CASES)}")
    if excluded_count != len(BOUNDARY_ARTIFACT_CASES):
        print("경고: 목록에 있는 건수와 실제 매칭된 건수가 다릅니다 - whisper_value 문자열을 다시 확인하세요.")

    return pd.DataFrame(rows).sort_values(["scenario_id", "style_condition"])


def main():
    df = compute_both_versions()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "sensitivity_exclude_boundary_artifacts.csv"
    df.to_csv(out_path, index=False)

    print(f"\n저장 완료: {out_path}")

    print("\n=== 스타일별 평균 CCER: 원본 vs 14건 제외 ===")
    summary = df.groupby("style_condition").agg(
        mean_ccer_full=("ccer_score_full", "mean"),
        mean_ccer_excl=("ccer_score_excl_boundary_artifacts", "mean"),
        total_removed=("n_boundary_artifacts_removed", "sum"),
    ).round(4)
    summary["rank_full"] = summary["mean_ccer_full"].rank()
    summary["rank_excl"] = summary["mean_ccer_excl"].rank()
    print(summary)

    rank_changed = not summary["rank_full"].equals(summary["rank_excl"])
    print(f"\n스타일 순위 변화 여부: {'변경됨' if rank_changed else '변경 없음 (강건함)'}")


if __name__ == "__main__":
    main()
