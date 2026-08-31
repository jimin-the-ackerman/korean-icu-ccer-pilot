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

**스타일별 평균 CCER (v2 → v3)**

| 스타일 | v2 | v3 | 변화 |
|---|---|---|---|
| Formal Template | 1.9546 (최악) | 1.3324 (최악) | -0.6222 |
| Clinical Charting | 1.7714 | 1.0857 | -0.6857 |
| Telegraphic ICU | 1.6432 (최선) | 0.9924 (최선) | -0.6509 |

15개 샘플 전부에서 CCER이 감소했고(예외 없음), 스타일별 평균 감소폭이
-0.62~-0.69로 균일함 — 특정 스타일에 유리하게 taxonomy가 작동한 게 아니라
파이프라인 전체의 구조적 오염이 고르게 제거됐음을 시사.

**WER-CCER 역전 현상 유지 여부**: 유지됨. v1/v2/v3 세 버전 내내 순위
(Telegraphic ICU < Clinical Charting < Formal Template)가 한 번도 바뀌지
않음.

**hallucination 총 건수 (v2 → v3)**: 39건(13/13/13) → 8건. intervention
카테고리만 놓고 보면 28건 → 0건으로 완전히 해소됨 — device/oxygen_support
중복 추출 버그가 v2 hallucination의 대부분을 차지하고 있었음이 확인됨.

**medication_identity_error 발생 건수**: 0건 (15/15 전부 exact/semantic로
정상 매칭, omission/hallucination/value_substitution 없음). 이번 15샘플
파일럿 규모에서는 LASA류 약물 오인 사례가 우연히 없었을 뿐이며, 판정
메커니즘 자체는 3단계 spot-check(Hydralazine/Hydroxyzine)에서 이미 검증됨.

**intake_output, medication_identity가 entity_error_profile에 정상 등장하는지**:
정상 등장 확인. entity_type 목록:
`['clinical_status', 'device', 'dose', 'frequency', 'intake_output',
'intervention', 'medication_identity', 'notification', 'route', 'symptom',
'vital_sign']` — medication_identity(15건), intake_output(9건, 값이 있는
시나리오 002/004/005 기준) 모두 독립 entity_type으로 Profile 축에 정상
편입됨.

**v2 대비 entity_type별 hallucination 건수 비교 (pipeline sanity audit)**:

| entity_type | v2 | v3 | 비고 |
|---|---|---|---|
| intervention | 28 | 0 | **완전 해소** (이번 v3의 목표) |
| symptom | 6 | 3 | 개선(원인은 사전 존재 문제, 한계 #12 참고) |
| device | 1 | 1 | 변화 없음 (사전 존재, 한계 #11 참고) |
| dose | 4 | 4 | 변화 없음 (사전 존재, 한계 #10 참고) |
| vital_sign / route / frequency / clinical_status / notification | 0 | 0 | 완전히 동일 (v3가 건드리지 않은 경로, 회귀 없음 확인) |

**v2 대비 CCER 점수가 오른/내린 샘플 및 이유**: 15개 전부 하락. 가장 크게
하락한 건 scenario_003_clinical_charting(2.3571 → 1.1333, -1.2238)이며,
해당 시나리오는 io가 없고 device="C-line"/oxygen_support="nasal cannula"만
있어 device/oxygen_support 중복 추출 버그의 영향이 특히 컸던 것으로 파악.

## Pipeline Sanity Audit 결론

taxonomy_audit.md §5에서 확정한 3가지 수정 대상(medication_identity 신설,
intake_output 신설, intervention 범위 축소)은 전부 의도대로 정확히
작동했고, 의도치 않은 다른 카테고리의 회귀는 없음을 15샘플 전수 검사로
확인. Audit 과정에서 taxonomy 범위 밖의 사전 존재 문제 3건(dose 정규식
카테고리 오염, device 중복 언급, symptom/patient_context·clinical_status
경계 누수)을 추가로 발견했으며, 이는 `docs/limitations.md` #10~12로
문서화하고 결과에 맞춰 taxonomy를 사후 확장하지 않는다는 원칙에 따라
v4 후보 Future Work로 남김. **v3 taxonomy/evaluation logic은 freeze.**

## 다음 단계

- [x] 위 TODO 채우기 (로컬 실행 결과 반영)
- [x] Pipeline sanity audit (hallucination 8건 전수, medication_identity/
      intake_output 전수, device 중복 스캔, 기존 카테고리 회귀 검사)
- [x] `docs/limitations.md`/.ko.md에 신규 한계 #10~12 추가
- [ ] `docs/design_decisions.md`에 taxonomy 확정 및 v3 반영 과정을 하나의
      design decision 항목으로 추가
- [ ] v3 기준 Error Profile 분석
- [ ] v3 기준 effect size 재계산 및 power analysis 재실행 (v2 대비 CCER
      절대값이 30~40% 하락했으므로 효과 크기도 달라질 가능성 있음)
