# v3 — Taxonomy-Aligned Pipeline

**커밋 범위**: `d27ce56`(step 1) ~ `2fda468`(step 5) — 5개 커밋
**기준 문서**: `docs/taxonomy_audit.md` §5(확정 taxonomy), §8(pipeline alignment table)

## v2 대비 변경 사항

| 파일 | 변경 내용 |
|---|---|
| `scaffold_as_gold.py` | `medication_identity`, `intake_output` Gold 매핑 신설 |
| `open_vocab_extractor.py` | Whisper 측 동일 필드 신설, `intervention` 범위를 device/oxygen_support/medication/io 제외하도록 축소 |
| `semantic_matcher.py` | `medication_identity_match`, `intake_output_match` 신설, `value_substitution` match_basis 4개 단일값 필드 공통 추가, medication_identity 전용 LASA 안전 규칙(ISMP 근거) |
| `flatten_matches.py` | `value_substitution` → entity_type별 error_type 매핑 (`medication_identity_error` vs 기존 `substitution`) |
| `ccer_eval.py` | `ERROR_WEIGHTS["medication_identity_error"] = 3` (최상위 등급) 추가 |

## 실행 전 로컬 spot-check 결과 (합성/대표 샘플, 15샘플 재실행 전 사전 검증)

- `open_vocab_extractor.py`: 대표 transcript 3개(scenario_001/004/002) 전부 의도한 대로 동작 확인 — medication_identity 축어적 추출, intake_output 정확 추출, device 관련 표현이 intervention에 중복 안 됨
- `semantic_matcher.py`: 합성 케이스 6개 전부 통과 — 특히 `Hydralazine`/`Hydroxyzine`(ISMP 공식 LASA 쌍)이 정확히 `value_substitution`으로 판정되어 핵심 안전장치 확인

## 15샘플 v3 재실행 결과

<!-- 아래는 로컬 실행 후 results/pilot_15/v3_taxonomy_aligned/ccer_results.csv,
     style_summary.csv, v2_vs_v3_comparison.csv 내용을 보고 채워넣을 자리 -->

- 스타일별 평균 CCER (v2 대비):
  - TODO
- WER-CCER 역전 현상 유지 여부:
  - TODO
- medication_identity_error 발생 건수 (스타일별):
  - TODO
- intake_output, medication_identity가 entity_error_profile에 정상적으로 나타나는지:
  - TODO
- v2 대비 CCER 점수가 오른 샘플 / 내린 샘플 및 그 이유:
  - TODO (device/oxygen_support 중복 제거로 하락 예상되는 샘플들, io 반영으로 상승 예상되는 샘플들 등)

## 다음 단계

- [ ] 위 TODO 채우기 (로컬 실행 결과 반영)
- [ ] `docs/design_decisions.md`에 taxonomy 확정 및 v3 반영 과정을 하나의 design decision 항목으로 추가
- [ ] v3 결과 확정 후에만 통계 검정 / weight sensitivity / power analysis 재실행 (§6.4 원칙: 결과에 맞춰 taxonomy 재수정하지 않음)
