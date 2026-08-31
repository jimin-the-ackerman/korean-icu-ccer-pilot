"""
결과 폴더 정리: v2 결과를 v2_hallucination_phonetic/ 로 이동

docs/taxonomy_audit.md §6.2에서 계획한 저장 구조를 실제로 적용한다.
지금까지 results/pilot_15/ 바로 밑에 흩어져 있던 v2 관련 파일들을
버전별 폴더로 정리하고, 이후 v3 결과와 명확히 구분되게 한다.

이 스크립트는 파일을 삭제하지 않고 이동(move)만 한다.

사용법:
    python -m src.analysis.organize_results_by_version
"""

import shutil
from pathlib import Path

RESULTS_DIR = Path("results/pilot_15")
V2_DIR = RESULTS_DIR / "v2_hallucination_phonetic"

# results/pilot_15/ 바로 밑에 있는, v2 단계에서 생성된 파일들
V2_FILES = [
    "ccer_results_v2_partial.csv",
    "error_type_counts_by_style.csv",
    "error_type_proportions_by_style.csv",
    "entity_x_error_crosstab_overall.csv",
    "entity_x_error_crosstab_clinical_charting.csv",
    "entity_x_error_crosstab_formal_template.csv",
    "entity_x_error_crosstab_telegraphic_icu.csv",
]


def main():
    V2_DIR.mkdir(parents=True, exist_ok=True)
    moved, missing = [], []

    for filename in V2_FILES:
        src = RESULTS_DIR / filename
        if src.exists():
            dst = V2_DIR / filename
            shutil.move(str(src), str(dst))
            moved.append(filename)
        else:
            missing.append(filename)

    print(f"이동 완료 ({len(moved)}개): {moved}")
    if missing:
        print(f"찾지 못함 (이미 없거나 아직 생성 안 됨, {len(missing)}개): {missing}")
    print(f"\n{V2_DIR}/ 정리 완료. v3 결과는 python -m src.analysis.recompute_pilot15_v3 실행 시")
    print(f"results/pilot_15/v3_taxonomy_aligned/ 에 자동으로 별도 생성됩니다.")


if __name__ == "__main__":
    main()
