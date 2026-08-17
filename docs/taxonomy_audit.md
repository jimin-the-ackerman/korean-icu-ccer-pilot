# CCER Clinical Entity Taxonomy — Independent Audit

**작성 원칙**: 이 문서는 현재 파이프라인에서 관찰된 오류(hallucination 개수 등)를
줄이기 위한 사후 패치가 아니라, CCER이 다뤄야 할 clinical information taxonomy를
독립적으로 먼저 정립하고 그 기준으로 현재 구현을 감사(audit)한 결과다.
**§1~8은 분석·설계 문서이며, §6 실제 코드 반영 전까지는 코드를 수정하지 않는다.**

---

## 1. Content Scaffold의 전체 Clinical Field 목록 및 임상적 의미

`data/scenarios/scenario_*.json`에 실제로 존재하는 모든 필드를 코드로 스캔하여
누락 없이 확인했다.

| Scaffold Field | 임상적 의미 |
|---|---|
| `patient_context` | 환자 배경(연령, 성별, 진단명 등) — 반복 측정/보고되는 "사건성" 정보가 아니라 서술적 배경 정보. Entity 매칭 대상 여부 자체를 별도로 검토해야 함(§5 참고) |
| `vital_signs` (BP/HR/RR/BT/SpO2) | 활력징후 — 시점별로 측정되는 생리학적 수치 |
| `symptom` (name/negation/severity) | 환자가 호소하거나 관찰된 임상 증상·소견, 부정(negation)·중증도(severity) 속성 포함 |
| `clinical_status` | 의식 수준 등 환자의 전반적 임상 상태 (예: alert, drowsy) |
| `medication.name` | 투여된 약물의 정체(**어떤 약물인가**) |
| `medication.dose` | 투여 용량 |
| `medication.route` | 투여 경로 |
| `medication.frequency` | 투여 빈도 |
| `intervention` | 투약을 제외한 능동적 임상 처치/시술 (예: fluid resuscitation, cardiac monitoring) |
| `device` | 환자에게 사용 중인 의료기기 (예: ventilator, Foley, C-line) |
| `oxygen_support` | 산소 공급 방식 (예: nasal cannula) |
| `io` | 섭취/배설량, 체액 균형 관측 데이터 (예: urine output, negative fluid balance) |
| `notification` | 의료진 간 통보 행위 (예: "Respiratory therapist notified of low SpO2") |
| `scenario_id` | 메타데이터, 임상 정보 아님 |

**5개 시나리오 실측 기준 non-null 비율**: patient_context/vital_signs/symptom/
medication/clinical_status/notification = 5/5(100%), device = 4/5, oxygen_support = 3/5,
intervention = 3/5, io = 3/5.

---

## 2. Gold Transformation Audit (`scaffold_as_gold.py`)

`scaffold_to_closed_vocab()`, `scaffold_to_open_vocab()`를 field-by-field로 대조했다.

| Scaffold Field | Gold Entity Type | Open/Closed | 비고 |
|---|---|---|---|
| medication.route | `route` | closed | 정상 |
| medication.frequency | `frequency` | closed | 정상 |
| medication.dose | `dose` | closed | 정상 |
| **medication.name** | **없음** | - | **현재 평가 불가능 — 어떤 코드 경로에도 존재하지 않음** |
| vital_signs | `vital_sign` | closed | 정상 |
| device | `device` | closed | 정상이나 §3에서 Whisper 측과 대조 시 문제 발견 |
| oxygen_support | `device` (normalized `"nc"`) | closed | device와 동일 카테고리로 정규화됨 |
| intervention | `interventions` | open | 정상 |
| **io** | **없음** | - | **현재 평가 불가능 — 어떤 코드 경로에도 존재하지 않음** |
| symptom | `symptoms` | open | 정상 |
| clinical_status | `clinical_status` | open | 정상 |
| notification | `notification` | open | 정상 |
| patient_context | (해당 없음) | - | 애초에 entity 변환 대상으로 설계되지 않음 |

---

## 3. Whisper-side Extraction Taxonomy 목록화 및 대조

### 3.1 Closed-vocabulary (`closed_vocab_extractor.py`, 정규식 기반)

| Entity Type | 정의/범위 |
|---|---|
| `route` | 투여 경로 약어 사전 매칭 (IV/PO/IM/SC/SL/PR) |
| `frequency` | 투여 빈도 약어 사전 매칭 (BID/TID/QID/PRN/STAT, q{n}h) |
| `device` | 의료기기 정규식 매칭 (foley, c-line, ventilator, ng tube, nasal cannula/nc) |
| `vital_sign` | 활력징후 라벨+수치 패턴 매칭 (BP/HR/RR/BT/SpO2/SAT) |
| `dose` | 숫자+단위 패턴 매칭 (mg/mL/cc/g/mcg/L/min) |

### 3.2 Open-vocabulary (`open_vocab_extractor.py`, Claude 기반)

| Entity Type | 정의/범위 (SYSTEM_PROMPT 기준) |
|---|---|
| `symptoms` | 텍스트에 명시적으로 언급된 증상 (negation/severity 포함) |
| `clinical_status` | 의식/전반적 상태 (단일 nullable 문자열) |
| `interventions` | "명시적으로 언급된 임상 처치나 시술 (**투약 제외**)" — 범위가 넓게 정의되어 있어 device/oxygen_support/io 관련 표현도 포괄적으로 흡수함 |
| `notification` | 의료진 통보 문구 (단일 nullable 문자열) |

### 3.3 Gold ↔ Whisper 교차 대조 결과

| 임상 개념 | Gold Entity Type | Whisper Entity Type | 판정 |
|---|---|---|---|
| medication.route | `route` (closed) | `route` (closed) | 일치 |
| medication.frequency | `frequency` (closed) | `frequency` (closed) | 일치 |
| medication.dose | `dose` (closed) | `dose` (closed) | 일치 |
| **medication.name** | 없음 | 없음 (`interventions`에서 명시적으로 제외) | **양측 누락 (missing category, both sides)** |
| vital_signs | `vital_sign` (closed) | `vital_sign` (closed) | 일치 |
| device | `device` (closed) | `device` (closed) **+** `interventions` (open, 중복 추출) | **duplicated concept** |
| oxygen_support | `device` (closed) | `device` (closed) **+** `interventions` (open, 중복 추출) | **duplicated concept** |
| intervention | `interventions` (open) | `interventions` (open) | 일치 |
| **io** | 없음 | `interventions` (open, 흡수됨) | **one-side-only (missing on Gold side)** |
| symptom | `symptoms` (open) | `symptoms` (open) | 일치 |
| clinical_status | `clinical_status` (open) | `clinical_status` (open) | 일치 |
| notification | `notification` (open) | `notification` (open) | 일치 |

**확인된 불일치는 3건**: (a) medication.name 양측 누락, (b) device/oxygen_support가
Whisper 측에서 device와 interventions 두 곳으로 중복 추출(duplicated concept),
(c) io가 Gold 측에만 없어 Whisper의 자유 추출과 대응 불가(one-side-only).

---

## 4. 외부 임상 표준(FHIR / SNOMED CT) 매핑

FHIR resource 정의(HL7 FHIR R4/R5 공식 스펙)와 SNOMED CT top-level hierarchy를
근거로, 각 카테고리가 **독립된 임상 개념 축인지 아니면 다른 카테고리에 속하는지**를
검토했다. FHIR/SNOMED CT를 그대로 taxonomy로 채택하는 것이 아니라, "이 구분이
임상 정보학 관점에서 이미 존재하는 구분인가"를 확인하는 근거 자료로만 사용한다.

| CCER 후보 카테고리 | 대응 FHIR Resource | 대응 SNOMED CT Hierarchy | 근거 및 시사점 |
|---|---|---|---|
| Vital sign | `Observation` (category=`vital-signs`) | Observable entity | FHIR·SNOMED 모두에서 독립된 표준 카테고리. 현재 설계와 일치 |
| Symptom / clinical finding | `Condition` 또는 `Observation` | Clinical finding | 독립된 표준 카테고리. 현재 설계와 일치 |
| Clinical status (의식수준) | `Observation` | Observable entity | Symptom과는 다른 관측 축(생리 신호가 아닌 의식 상태)으로 별도 취급이 타당 |
| **Medication identity (약물 정체)** | `MedicationRequest`/`MedicationStatement`의 **`medicationCodeableConcept`** | Pharmaceutical/biologic product, Substance | FHIR는 "무엇을 투여했는가(medicationCodeableConcept)"와 "어떻게 투여했는가(dosageInstruction: dose/route/frequency)"를 **명확히 별도 필드로 분리**한다. 즉 표준 자체가 "약물 정체성"과 "투여 속성"을 서로 다른 정보 축으로 규정하고 있음 — medication.name을 별도 카테고리로 두는 것은 임의의 추가가 아니라 표준과의 정합성 문제임 |
| Medication dose/route/frequency | `MedicationRequest.dosageInstruction` (Dosage 데이터타입) | Qualifier value(경로) | 위와 동일 근거로, 이미 별도 sub-field로 분리되어 있는 것이 표준 |
| Intervention / procedure | `Procedure` | Procedure | 독립된 표준 카테고리 |
| **Device / respiratory support** | `Device`, `DeviceUseStatement` | **Physical object** | device와 oxygen_support는 SNOMED CT 기준으로 **동일한 상위 계층(Physical object — 환자에게 사용 중인 물리적 장치)**에 속함. Scaffold에서 별도 필드로 나뉜 것은 시나리오 생성 편의상의 구분일 뿐, taxonomy 관점에서는 **하나의 카테고리로 합치는 것이 표준에 더 부합** |
| **Intake/Output (체액 균형)** | `Observation` (fluid intake/output 계열 LOINC) | Observable entity | Vital sign과는 다른 측정 계열이지만, 임상 워크플로우 상 독립적으로 모니터링되는 표준 관측 카테고리. Device/Procedure와는 별개 축이므로 **intervention에 편입시키는 것은 개념적으로 부정확** — 별도 카테고리가 표준에 더 부합 |
| Notification / communication | `Communication` | (대응 없음 — 임상 사실이 아닌 워크플로우 행위) | 유일하게 "임상 사실"이 아니라 "임상 커뮤니케이션 행위"를 담는 카테고리. 이는 기존 설계에서도 이미 그렇게 다뤄지고 있었으며, 이번 audit으로 새로 발견된 문제는 아님 |

---

## 5. 확정된 CCER Operational Taxonomy

아래 3가지 결정에 따라 taxonomy를 확정한다.

### 5.1 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| `medication_identity` | **open-vocab** | 약물명은 폐쇄 사전보다 자유 매칭이 적절 (`Ceftriaxone` ↔ `세프트리아손`). 기존 semantic matcher/phonetic_artifact 로직 재사용 가능 |
| `intake_output` | **open-vocab** (독립 카테고리, intervention에 편입하지 않음) | 표현 다양성이 커서(`urine output 200 mL/4h`, `U/O 200cc/4hr`, `negative fluid balance`) 자유 매칭이 적절. §4의 FHIR Observation(fluid I/O) 근거상 intervention과는 별도 축 |
| `patient_context` | **CCER 평가 범위에서 명시적으로 제외** | Demographic/진단 정보는 성격이 다르고 범위가 크게 확장되므로, "clinically actionable information의 보존/왜곡 평가"라는 현재 연구 범위에서 의도적으로 제외. 향후 확장 시 재검토 (`docs/limitations.md`에 explicit scope exclusion으로 기록 예정) |

### 5.2 최종 Taxonomy (11개 Entity Type)

| # | Category | Open/Closed | 값 개수 | 비고 |
|---|---|---|---|---|
| 1 | `vital_sign` | closed | 다수(항목별) | 변경 없음 |
| 2 | `symptom` | open | 0~1 (Scaffold 제약상) | 변경 없음 |
| 3 | `clinical_status` | open | 단일값 | 변경 없음. §5.3의 `value_substitution` 신설 적용 대상 |
| 4 | **`medication_identity`** | open | 단일값 | **신설**. §5.3의 `value_substitution` 신설 적용 대상 |
| 5 | `medication_dose` | closed | 단일값 | 기존 `dose` |
| 6 | `medication_route` | closed | 단일값 | 기존 `route` |
| 7 | `medication_frequency` | closed | 단일값 | 기존 `frequency` |
| 8 | `intervention` | open | 0~1 | 프롬프트에 device/oxygen_support/medication/io 사용은 제외한다고 명시 (SNOMED Procedure ≠ Physical object ≠ Observable entity 근거) |
| 9 | **`device`** | closed | 다수 | device + oxygen_support 완전 통합 (SNOMED Physical object 단일 계층 근거) |
| 10 | **`intake_output`** | open | 0~1 | **신설**. §5.4 참고 |
| 11 | `notification` | open | 단일값 | 변경 없음. "임상 사실이 아닌 워크플로우 카테고리" 성격 명시 |

`patient_context`는 목록에서 제외한다.

### 5.3 medication_identity — "값이 둘 다 있는데 다른 경우"를 위한 매칭 설계

기존 `flatten_matches.py`에 이미 기록되어 있던 Known Limitation을 이번에 함께 해소한다:

> clinical_status_match / notification_match 스키마는 "값이 존재하지만 서로 다른
> 경우(예: alert vs drowsy)"에 대한 명시적 오류 카테고리가 없다.

closed-vocab의 `match_dose()`는 이미 이 패턴을 지원한다 — Gold/Whisper 양쪽에
값이 하나씩 남으면 omission+hallucination 두 사건으로 쪼개지 않고, **하나의
`error` 레코드**(예: `numeric_error`/`unit_error`/`substitution`)로 묶는다.
같은 원리를 단일값 open-vocab 필드(`clinical_status_match`, `notification_match`,
신설되는 `medication_identity_match`)에도 동일하게 적용한다.

**설계**: `match_basis` enum에 `value_substitution`을 신설한다 — "Gold와 Whisper
양쪽에 값이 있고, `semantic`도 `phonetic_artifact`도 아닌, 서로 다른 실제 값인
경우"를 가리킨다. 이 하나의 match_basis를 clinical_status/notification/
medication_identity 세 곳에 공통 적용하되, 최종 `error_type`은 **entity_type에
따라 다르게 매핑**한다:

| entity_type | `value_substitution` → error_type | weight | 근거 |
|---|---|---|---|
| `medication_identity` | **`medication_identity_error`** (신설) | **3 (최상위)** | 다른 약물로 오인식되는 것은 실제 투약 오류로 이어질 수 있는 최고 위험군. numeric_error/negation_flip/hallucination과 동일 등급 |
| `clinical_status` | `substitution` (기존) | 2 | 기존 등급 유지 |
| `notification` | `substitution` (기존) | 2 | 기존 등급 유지 |

이렇게 하면 요청하신 "medication identity 오류를 별도 error_type/profile에서
명확히 확인"이 두 층위에서 동시에 충족된다:
1. **Profile 축(entity_type × error_type 교차표)**: `medication_identity`가 독립
   entity_type이므로, 이미 구축된 교차표 분석에 자동으로 별도 행(row)으로 나타남
2. **Severity 축**: `medication_identity_error`가 최상위 가중치(3)를 가지므로,
   critical error rate 계산에도 명확히 반영됨

### 5.4 intake_output — 향후 구조화를 고려한 설계

이번 taxonomy에서는 `symptom`/`intervention`과 동일하게 **단일 자유 텍스트
open-vocab entity**로 정의한다 (예: `"urine output 200 mL over 4 hours"`).
다만 향후 `type`(intake/output/balance) / `value`(수치) / `unit`(mL, cc 등) /
`time_window`(4h 등)로 구조화할 수 있는 여지를 남겨둔다 — 이는 지금 당장 구현하지
않고, `intake_output` 필드 자체를 독립 카테고리로 먼저 확정하는 이번 단계와
분리하여 별도 future work로 `docs/limitations.md`에 기록한다.

### 5.5 patient_context — Explicit Scope Exclusion

`patient_context`(연령, 성별, 진단명 등)는 CCER entity taxonomy에 포함하지
않는다. 이는 누락이 아니라 **의도적 범위 제한(explicit scope exclusion)**이며,
사유는 다음과 같다:
- CCER의 연구 범위는 "clinically actionable information(증상·처치·투약·수치 등
  임상적 판단/행동에 직결되는 정보)의 보존/왜곡 평가"로 한정
- Demographic/진단 정보는 성격이 다르고(정적 배경 정보 vs 시점별 관찰/행위),
  포함 시 taxonomy 범위가 크게 확장됨
- `docs/limitations.md`에 explicit scope exclusion으로 기록하고, Future Work로
  demographic/diagnosis 정보 확장 가능성을 남겨둔다 (코드 반영은 이번 단계에서
  하지 않음)

---

## 6. Versioning & Traceability 계획 (설계 단계 — 아직 실행하지 않음)

taxonomy 확정(§5) 이후 진행할 §6-구현(pipeline 전체 정렬)과 15샘플 재실행을
위해, 어떤 방법론적 변경이 어떤 결과 변화를 만들었는지 추적 가능하도록 버전을
분리해서 보존하는 계획을 먼저 정리한다.

### 6.1 버전 정의

| 버전 | 범위 | 상태 |
|---|---|---|
| **v1 — Original** | 최초 파일럿. Gold를 텍스트에서 직접 추출(§1의 "Design Change" 이전 방식), whisper_only 미반영(weight 0), phonetic_artifact 미구분 | git 히스토리로 재구성 가능 (커밋 `8b8988a` 이전 로직) |
| **v2 — Hallucination + Phonetic-artifact fix** | 이번 세션 1~2주차. Scaffold 기반 Gold 유지, hallucination penalty(weight 3) + phonetic_artifact 구분 반영 | **완료, 현재 상태** (`results/pilot_15/ccer_results_v2_partial.csv`) |
| **v3 — Taxonomy-aligned** | 이번 §5에서 확정한 11개 카테고리 전체 정렬 (medication_identity, intake_output 신설, intervention 범위 축소, value_substitution 매칭 추가) | **미착수** — §5 확정 후 진행 |

### 6.2 저장 구조 제안

```
results/pilot_15/
  v1_baseline/            # git 커밋 8b8988a 시점 로직으로 재구성, 참고용
  v2_hallucination_phonetic/
    ccer_results.csv
    error_type_counts_by_style.csv
    entity_x_error_crosstab_*.csv
  v3_taxonomy_aligned/
    ccer_results.csv
    error_type_counts_by_style.csv
    entity_x_error_crosstab_*.csv
    VERSION_NOTES.md      # v2 대비 변경점과 각 변경이 CCER 값에 미친 영향 요약
```

기존 `results/pilot_15/ccer_results_v2_partial.csv` 등은 `v2_hallucination_phonetic/`
폴더로 이동하며 덮어쓰지 않는다.

### 6.3 추적성(traceability) 확보 방법

- 각 버전은 **git commit/tag**와 1:1 대응시킨다 (예: `v2-hallucination-phonetic-fix`,
  `v3-taxonomy-aligned` 태그를 해당 커밋에 부여)
- `VERSION_NOTES.md`에는 "이 버전에서 무엇이 바뀌었는가"뿐 아니라 "그 결과 CCER/
  entity 개수/error_type 분포가 v2 대비 어떻게, 왜 바뀌었는가"까지 기록 (design_decisions.md
  의 서술 방식과 동일)
- `docs/design_decisions.md`에 taxonomy 확정 과정 자체를 항목으로 추가 (이번
  audit → 결정 → 반영까지의 전체 과정을 하나의 design decision으로 문서화)

### 6.4 원칙 — v3 실행 이후

v3 결과가 v1/v2와 다른 방향으로 나오더라도, **그 결과에 맞춰 taxonomy를 다시
수정하지 않는다.** §5에서 확정된 taxonomy는 외부 표준 근거로 독립적으로 정해진
것이며, v3는 그 taxonomy를 있는 그대로 적용한 결과를 해석하는 단계다. "기존
결과와 비슷한 방향이 나오는가"는 taxonomy 재수정의 기준이 아니다.

### 6.5 이번 단계에서 하지 않는 것

- `scaffold_as_gold.py`, `open_vocab_extractor.py`, `semantic_matcher.py`,
  `flatten_matches.py`, `ccer_eval.py` 코드 수정 — §5·§8 taxonomy가 이 문서로
  확정된 것을 최종 확인한 뒤 진행
- 15샘플 v3 재실행 — 위 코드 수정 완료 후 진행

---

## 7. 외부 표준 참고 근거 종합 (Methodological Grounding Summary)

CCER 설계 전반(taxonomy뿐 아니라 severity 가중치까지)에서 세 개의 서로 다른
외부 표준을 서로 다른 목적으로 참고했다. **셋 다 "그대로 구현"한 것이 아니라
"개념적으로 참고"한 것**이며, 이 절에서 그 경계를 명확히 한다 — methodological
validity를 논문에서 방어하려면 "정확히 무엇을 빌렸고 무엇을 빌리지 않았는지"를
분명히 하는 것이 중요하다.

### 7.1 FHIR — Entity Taxonomy의 "카테고리 경계"를 정하는 데 사용

| 참고한 것 | CCER에 반영된 방식 |
|---|---|
| Resource 단위로 정보가 구분된다는 구조적 원칙 (Observation/Condition/Procedure/Device/MedicationRequest/Communication이 서로 다른 resource) | 11개 entity_type을 "서로 다른 resource가 다루는 서로 다른 정보 축"으로 대응시킴 |
| `MedicationRequest`가 **`medicationCodeableConcept`**(약물 정체)와 **`dosageInstruction`**(Dosage datatype 안의 dose/route/frequency/timing)을 별도 필드로 분리하는 구조 | `medication_identity`를 `medication_dose`/`route`/`frequency`와 별도 category로 분리하는 핵심 근거 (§5.1) |
| `Observation`의 `category=vital-signs` 프로파일이 활력징후를 독립 카테고리로 다루는 방식 | `vital_sign` category 근거 |
| `Communication` resource가 Condition/Observation/Procedure류와 별도 계열이라는 구조 | `notification`이 "임상 사실이 아닌 워크플로우 행위"라는 성격 규정 근거 (§5.2) |

**참고하지 않은 것**: 실제 FHIR resource의 JSON 스키마, cardinality, 필수 필드,
LOINC/기타 코드 시스템, valueSet binding. CCER은 FHIR 호환 데이터 모델이
아니며, "정보를 나누는 경계가 어디 있는지"에 대한 구조적 아이디어만 가져왔다.

### 7.2 SNOMED CT — 같은 개념인지 다른 개념인지 "판별"하는 데 사용

| 참고한 것 | CCER에 반영된 방식 |
|---|---|
| Top-level hierarchy 구조 (Clinical finding / Procedure / Physical object / Observable entity / Substance·Pharmaceutical product 등, 138875005 |SNOMED CT Concept| 하위) | 어떤 두 scaffold 필드가 "같은 상위 개념에 속하는가"를 판별하는 기준으로 사용 |
| device와 oxygen_support가 둘 다 **Physical object** 계층에 속한다는 사실 | 두 필드를 하나의 `device` category로 통합하기로 한 결정의 직접 근거 (§5.2, #9) |
| medication_identity가 **Substance/Pharmaceutical product** 계층인 반면 dose/route/frequency는 별도 attribute(속성) 성격이라는 구분 | medication_identity 분리 근거를 FHIR 근거와 이중으로 뒷받침 |

**참고하지 않은 것**: 실제 SNOMED CT concept ID(숫자 코드), attribute-relationship
model(예: `|has active ingredient|`, `|route of administration|` 같은 formal
relationship), 실제 Description/용어사전. CCER은 SNOMED CT 코딩 시스템을 채택하지
않으며, "이 두 표현이 상위 계층에서 같은 카테고리에 속하는가"라는 구조적 판별
논리만 가져왔다.

### 7.3 NCC MERP — Severity 가중치 체계의 "철학적 구조"를 참고

NCC MERP(National Coordinating Council for Medication Error Reporting and
Prevention)의 Index for Categorizing Medication Errors는 의료 오류를 아래와
같이 9단계(Category A~I)로 분류한다:

| 단계 | 의미 |
|---|---|
| A | 오류 발생 가능성은 있었으나 실제 오류는 없음 |
| B–D | 오류가 환자에게 도달했으나 위해(harm) 없음 (D는 모니터링 필요) |
| E–H | 오류가 환자에게 위해를 초래 — 일시적 위해(E) → 입원/처치 필요(F) → 영구적 위해(G) → 생명유지 개입 필요(H) |
| I | 사망에 기여하거나 사망을 초래 |

| 참고한 것 | CCER에 반영된 방식 |
|---|---|
| "오류가 환자에게 도달했는가" + "도달했다면 결과가 얼마나 심각한가"라는 **2단계 철학적 구조** — 오류를 이진법(맞음/틀림)이 아니라 잠재적 임상 영향의 크기라는 연속 척도로 다룬다는 원칙 | `ERROR_WEIGHTS`를 3단계(1/2/3)로 설계하는 철학적 근거 (`ccer_eval.py` Methodological Note에 기존부터 명시) |
| 오류의 "잠재적 결과"에 따라 등급을 매긴다는 접근 자체 | `medication_identity_error`를 최상위 가중치(3)로 두는 근거 — 약물 오인은 NCC MERP상 E~I(실제 위해로 이어질 잠재력이 큰) 범주에 해당할 개연성이 높다는 임상적 판단 |

**참고하지 않은 것**: NCC MERP의 실제 A~I 9단계를 CCER의 1/2/3 가중치에 직접
매핑하지 않았다. NCC MERP는 "실제 환자에게 도달했는가/실제로 위해가
발생했는가"라는 **실제 임상 결과(patient outcome)** 기반 분류인데, 본 연구는
합성 데이터 파일럿이라 애초에 "환자"도 "실제 결과"도 존재하지 않는다. 따라서
CCER의 가중치는 검증된 임상 심각도 척도가 아니라, NCC MERP의 철학만 빌려
연구자가 직접 판단한 **연구 목적의 근사치**임을 `ccer_eval.py`와
`docs/limitations.md`에 이미 명시하고 있다 (한계 #8, 임상 전문가 검증 부재와
함께 기록).

### 7.4 종합 — CCER 설계 결정 대 참고 표준 매핑

| CCER 설계 결정 | 근거 표준 | 참고한 것 | 참고하지 않은 것 |
|---|---|---|---|
| 11개 entity_type 경계 설정 | FHIR | resource 단위 "정보 축" 구분 논리 | 실제 스키마·cardinality |
| medication_identity를 dose/route/frequency와 분리 | FHIR | medicationCodeableConcept ≠ dosageInstruction 필드 분리 | 실제 필드명·valueSet |
| device + oxygen_support 통합 | SNOMED CT | 둘 다 Physical object 계층이라는 구조적 판별 | 실제 concept ID·relationship model |
| medication_identity가 dose 등과 다른 축이라는 근거 | SNOMED CT | Substance/Pharmaceutical product ≠ attribute 성격 구분 | 실제 concept ID |
| notification의 "비임상 워크플로우" 성격 | FHIR | Communication vs Observation/Condition/Procedure 구분 | - |
| error_type 3단계 가중치 철학 | NCC MERP | "도달 여부 + 심각도"라는 2단계 철학적 뼈대 | A~I 실제 카테고리, 환자 결과 기반 판정 |
| medication_identity_error 최상위 가중치(3) 부여 | NCC MERP | 약물 오인은 위해로 이어질 잠재력이 큰 범주라는 철학 | 실제 위해도 검증(합성 데이터라 불가) |

이 표는 그대로 논문 Methods 섹션의 "Taxonomy and severity weighting were
conceptually informed by, but not directly mapped from, FHIR, SNOMED CT, and
the NCC MERP Index" 서술의 근거 자료로 사용할 수 있다.

---

## 8. Full Pipeline Taxonomy Alignment Table (구현 전 최종 검증)

**목적**: §5에서 확정한 taxonomy가 파이프라인 전 구간(Scaffold → Gold →
Whisper → Matching → Evaluation)에서 논리적으로 일관되는지, 코드를 건드리기
**전에** 표로 먼저 검증한다. "정합 여부" 열이 ✗인 행만 실제로 코드를
고치게 되며, 이 표 자체가 코드 구현의 체크리스트가 된다.

### 8.1 Scaffold → Gold → Whisper 대응표 (전체 11개 필드 + 제외 1개)

| Scaffold Field | 최종 Category | Gold 표현 (목표 상태) | Whisper 표현 (목표 상태) | 정합 여부 | 비고 |
|---|---|---|---|---|---|
| `patient_context` | **제외** | 없음 | 없음 | N/A (설계상 양측 모두 미대상) | §5.5 explicit scope exclusion |
| `vital_signs` | `vital_sign` | closed, 항목별 다수값 | closed, 항목별 다수값 (regex) | ✅ 이미 정합 | 변경 불필요 |
| `symptom` | `symptom` | open, 단일 리스트(0~1) | open, 리스트(Claude) | ✅ 이미 정합 | 변경 불필요 |
| `clinical_status` | `clinical_status` | open, 단일값 | open, 단일값(Claude) | ✅ 이미 정합 | `value_substitution` match_basis만 신규 추가 (§5.3) |
| `medication.name` | **`medication_identity`** | open, 단일값 — **신규 매핑 필요** | open, 단일값 — **신규 스키마 필드 필요** | ❌ **현재 양측 모두 없음** → 구현 후 정합 목표 | `scaffold_to_open_vocab()` + `open_vocab_extractor.py` 양쪽 수정 필요 |
| `medication.dose` | `medication_dose` | closed | closed (regex) | ✅ 이미 정합 | 필드명만 `dose`→개념적으로 `medication_dose` (코드상 키는 유지 가능) |
| `medication.route` | `medication_route` | closed | closed (regex) | ✅ 이미 정합 | 상동 |
| `medication.frequency` | `medication_frequency` | closed | closed (regex) | ✅ 이미 정합 | 상동 |
| `intervention` | `intervention` | open, 단일 리스트(0~1) | open, 리스트 — **범위 축소 필요** | ❌ **현재 범위가 과도하게 넓음** (device/oxygen_support/io를 흡수) → 구현 후 정합 목표 | `open_vocab_extractor.py`의 SYSTEM_PROMPT에서 device/oxygen_support/io 명시적 제외 필요 |
| `device` | `device` | closed, 다수값 | closed, 다수값 (regex) | ✅ **이미 정합** (아래 8.2 참고) | 변경 불필요 — 문제는 `intervention` 쪽 중복 추출 |
| `oxygen_support` | `device` (통합) | closed, `device`로 정규화(`"nc"`) | closed, `device`로 매칭 (regex) | ✅ **이미 정합** | 상동 |
| `io` | **`intake_output`** | open, 단일값 — **신규 매핑 필요** | open, 단일값 — **신규 스키마 필드 필요** | ❌ **현재 Gold 측 완전 누락** → 구현 후 정합 목표 | `scaffold_to_open_vocab()` + `open_vocab_extractor.py` 양쪽 수정 필요, `intervention` 범위에서도 명시적 제외 |
| `notification` | `notification` | open, 단일값 | open, 단일값(Claude) | ✅ 이미 정합 | `value_substitution` match_basis만 신규 추가 |

### 8.2 요청하신 5개 경계 사례 — 명확화

- **`device`/`oxygen_support`**: closed-vocab 경로 자체는 **이미 정합**임을
  8.1에서 확인했다 (Gold·Whisper 양쪽 모두 규칙 기반으로 정확히 매칭됨 —
  §3에서 실제 `closed_vocab_matches` 데이터로도 검증됨). 문제는 device/
  oxygen_support가 잘못 정의된 게 아니라, **`intervention`의 Whisper 측 정의가
  과도하게 넓어서** 같은 정보를 자유 텍스트로 또 한 번 흡수하는 것이다. 따라서
  이 경계 문제의 수정은 `device` 카테고리 자체가 아니라 `intervention`
  카테고리의 범위 축소로 해결된다.
- **`intervention`**: 최종 범위는 "투약, device/oxygen_support 사용, io 관측을
  **모두 제외**한, 그 외의 능동적 임상 처치/시술"로 명확히 좁힌다. 즉
  intervention은 나머지 카테고리(medication, device, intake_output)에 속하지
  않는 "잔여" 카테고리로 재정의된다.
- **`medication_identity`**: intervention과 명확히 분리된 독립 카테고리.
  "무엇을 투여했는가"라는 정체성 정보만 다루며, 투여 행위 자체의 서술(예:
  "IV 투여함")은 intervention에도 medication_identity에도 속하지 않고
  route/dose/frequency(closed-vocab)로 이미 별도 처리된다.
- **`intake_output`**: intervention과 명확히 분리된 독립 카테고리. "체액
  섭취/배설 관측값"만 다루며, Foley 카테터 자체의 존재(device)와 그 카테터를
  통한 배액량 관측(intake_output)은 서로 다른 카테고리에 속한다 — 같은
  물리적 상황(Foley 카테터)에서 나온 두 개의 서로 다른 임상 정보 축이라는
  점을 §4에서 SNOMED CT/FHIR 근거로 이미 확인했다.
- **`patient_context`**: 파이프라인의 어느 단계에도 관여하지 않는다.
  Scaffold에는 존재하지만 Gold 변환, Whisper 추출, 매칭, 평가 전 구간에서
  의도적으로 제외된다.

### 8.3 Matching / Evaluation 단계 처리 방식

| Category | 매칭 방식 | match_basis (신규 항목 굵게) | 발생 가능 error_type |
|---|---|---|---|
| `vital_sign` | closed-vocab 규칙 (`entity_matcher.py`) | (값·단위 비교) | numeric_error, unit_error, omission, hallucination |
| `symptom` | open-vocab Claude (`symptom_matches`) | exact/normalized/semantic/phonetic_artifact/omission | negation_flip, severity_shift, omission, hallucination |
| `clinical_status` | open-vocab Claude (단일값) | exact/normalized/semantic/phonetic_artifact/**value_substitution**/omission/whisper_only/both_null | substitution, omission, hallucination |
| `medication_identity` | open-vocab Claude (단일값, 신규) | 상동 | **medication_identity_error(신규, weight 3)**, omission, hallucination |
| `medication_dose` | closed-vocab 규칙 (기존 `match_dose`) | (값·단위 비교) | numeric_error, unit_error, substitution, omission, hallucination |
| `medication_route` | closed-vocab 규칙 | (값 비교) | route_error, omission, hallucination |
| `medication_frequency` | closed-vocab 규칙 | (값 비교) | frequency_error, omission, hallucination |
| `intervention` | open-vocab Claude (리스트) | exact/normalized/semantic/phonetic_artifact/omission | omission, hallucination |
| `device` | closed-vocab 규칙 (기존, device+oxygen_support 통합 유지) | (값 비교) | device_error, omission, hallucination |
| `intake_output` | open-vocab Claude (단일값, 신규) | exact/normalized/semantic/phonetic_artifact/**value_substitution**/omission/whisper_only/both_null | substitution, omission, hallucination |
| `notification` | open-vocab Claude (단일값) | 상동 | substitution, omission, hallucination |

### 8.4 이 표에서 확인된 것

- ❌ 표시된 3개 행(`medication_identity`, `intervention` 범위, `intake_output`)만
  실제 코드 수정이 필요하다. 나머지 8개 카테고리는 이미 정합 상태이므로
  **손대지 않는다** — 이는 이번 taxonomy 확정이 "전체를 갈아엎는" 것이 아니라
  "실제로 불일치가 확인된 지점만 표준 근거에 따라 좁게 수정"하는 것임을
  보여준다 (methodological validity 방어 근거로 사용 가능)
- `device`/`oxygen_support` 문제는 `device` 카테고리 자체가 아니라
  `intervention` 카테고리 범위 축소로 해결되므로, **`scaffold_as_gold.py`의
  closed-vocab 변환 로직은 수정하지 않는다** — 수정 대상은
  `open_vocab_extractor.py`(Whisper 측 intervention 정의)뿐이다
- `medication_identity`, `intake_output` 두 신규 카테고리는 **동일한 코드
  패턴**(단일값 open-vocab, `clinical_status_match`/`notification_match`와
  동형 구조)을 재사용하므로 구현 리스크가 낮다

---

## 참고 문헌

- HL7 FHIR R4/R5 Specification — Observation, Procedure, Device, MedicationRequest,
  Communication resources (https://hl7.org/fhir/)
- SNOMED International — SNOMED CT Concept Model, Top-level Hierarchies
  (https://docs.snomed.org/)
- NCC MERP — Index for Categorizing Medication Errors (2022 Revision)
  (https://www.nccmerp.org/types-medication-errors)