# Design Decisions

*[English version here](design_decisions.md)*

본 문서는 Project Proposal 대비 파일럿 구현 과정에서 변경된 설계 결정을
정리한다. 각 항목은 원래 설계, 구현 중 발견된 문제, 변경된 결정, 사유,
평가 파이프라인에 미친 영향을 기록한다.

---

## 1. Text-to-Speech Provider

| 항목 | 내용 |
|---|---|
| **Original Design** | Google Cloud Text-to-Speech |
| **Design Decision** | OpenAI TTS(`tts-1`)로 대체. 단일 화자(voice) 고정 원칙은 그대로 유지 |
| **Reason** | GPT-4o 생성 단계와 동일한 OpenAI API로 의존성을 통일하여 인증/설정 관리를 단순화 |
| **Impact on the evaluation pipeline** | 없음. TTS 엔진 선택은 연구의 핵심 독립변수(Documentation Register)가 아니므로 평가 결과 해석에 영향을 주지 않음 |

---

## 2. Speech-to-Text Engine 및 언어 설정

| 항목 | 내용 |
|---|---|
| **Original Design** | 로컬 Whisper 모델 사용, Auto Detect와 한국어 고정(`language="ko"`)을 사전 비교 후 채택 |
| **Issue observed during implementation** | 로컬 GPU/모델 다운로드 없이 API 기반으로 빠르게 검증하는 것이 파일럿 규모에 더 효율적이라 판단 |
| **Design Decision** | OpenAI Whisper API(`whisper-1`)로 대체. `language="ko"` 고정으로 바로 진행하고, Auto Detect와의 비교 실험은 생략 |
| **Reason** | API 의존성 통일. 비교 실험은 파일럿의 핵심 목표(end-to-end 파이프라인 검증)에 필수적이지 않다고 판단 |
| **Impact on the evaluation pipeline** | Auto Detect 대비 한국어 고정이 코드스위칭 환경에서 어떤 차이를 보이는지에 대한 정량적 근거는 확보하지 못함(Future Work로 이월) |

---

## 3. Entity Matching의 Gold Standard

| 항목 | 내용 |
|---|---|
| **Original Design** | Gold Transcript(생성된 간호기록 텍스트)와 Whisper Transcript 양쪽에서 각각 Entity를 추출하여 비교 |
| **Issue observed during implementation** | Documentation Register(문장 구조)에 따라 Gold Transcript에서 추출되는 Entity 개수 자체가 달라지는 현상을 발견함. 동일 시나리오 기준, Formal Template Style은 평균 7~10개, Clinical Charting/Telegraphic ICU Style은 평균 12~17개로 약 2배 차이가 확인됨. 원인은 완전한 문장형 서술을 정규식 기반 추출기가 포착하지 못하는 데 있었음(예: "산소포화도는 88%로 확인되었으며" 형태는 `VITAL_SIGN_PATTERN`이 인식하지 못함) |
| **Design Decision** | Gold Standard를 Gold Transcript 대신 **Content Scaffold**(생성 시점의 구조화된 JSON)로 전환. Content Scaffold를 기존 Entity 추출 결과와 동일한 포맷으로 변환하는 어댑터(`src/entity_extraction/scaffold_as_gold.py`)를 추가하고, Closed/Open-vocabulary Matching 스크립트가 이를 사용하도록 변경 |
| **Reason** | Content Scaffold는 Documentation Register와 무관하게 Style 생성 이전 단계에서 고정되므로, Style 간 비교의 기준이 되는 Gold Entity 집합을 동일하게 유지할 수 있음 |
| **Impact on the evaluation pipeline** | 재설계 후 동일 시나리오 내 Gold Entity 개수가 Style에 관계없이 완전히 일치함을 확인(예: Scenario 001의 경우 세 Style 모두 13개). Recall 분모가 실제 임상 정보량을 정확히 반영하게 되면서 전체 Entity-level F1은 하락하였음(예: Clinical Charting Style 0.657 → 0.546). 이는 평가의 엄밀성이 향상된 결과로 해석하며, 재설계 이전 수치는 방법론적 결함으로 인해 과대평가되어 있었던 것으로 판단함. 이 변경은 WER 계산에는 영향을 주지 않음(WER은 Gold Transcript와 Whisper Transcript 간 비교를 그대로 유지) |

---

## 4. Semantic Matcher: 음차 전사 오류(Phonetic Artifact) 처리

| 항목 | 내용 |
|---|---|
| **Original Design** | Open-vocabulary Semantic Matcher(`src/matching/semantic_matcher.py`)는 모든 Gold/Whisper 쌍을 `exact / normalized / semantic / omission`(단일값 필드는 `whisper_only`/`both_null` 포함)으로만 분류 |
| **Issue observed during implementation** | 한계 5로 기록됨. Claude가 남은 Gold Entity에 대해 "가장 가까운" 매칭을 찾도록 요청받았을 때, Gold 용어의 영어/외래어 발음을 음차로만 재현한 Whisper 문자열(예: Gold "chest pain" vs Whisper "체스파인")을 `semantic` 매칭으로 잘못 분류하는 사례가 관찰됨. 이런 문자열은 Gold 텍스트 없이는 독자가 이해할 수 없는, 임상적으로 무의미한 표기임 |
| **Design Decision** | `symptom_matches`, `intervention_matches`, `clinical_status_match`, `notification_match`의 tool schema에 `semantic`과 구분되는 네 번째 match_basis 값 `phonetic_artifact`를 추가. `SYSTEM_PROMPT`에 "Gold를 보지 않고 Whisper 문자열만으로 한국어 화자가 임상 개념을 이해할 수 있는가?"를 기준으로 한 명시적 판정 규칙과 실제 파일럿에서 관찰된 "체스파인" 사례를 포함한 예시를 추가. 평가 단계(`src/evaluation/flatten_matches.py`)에서는 `phonetic_artifact`를 `omission`과 동일하게 처리(`OMISSION_EQUIVALENT_BASES`) — 어느 쪽이든 임상 정보가 실질적으로 보존되지 않았기 때문 |
| **Reason** | Claude가 이런 사례를 곧바로 `omission`으로 출력하게 하는 대신 `phonetic_artifact`라는 별도 카테고리로 남긴 이유는 감사(audit) 추적성 때문임: 원본 `*_matched.json`에 "왜" 해당 항목이 정보 손실로 처리되었는지가 남아, KOSMI 논문에서 "파일럿 symptom 매칭 M건 중 N건이 semantic에서 phonetic_artifact로 재분류됨" 같은 보고를 할 수 있음 |
| **Impact on the evaluation pipeline** | 이는 프롬프트 레벨의 완화 조치일 뿐, Claude의 판단과 독립적인 음성 유사도 탐지기를 추가한 것은 아니므로 경계 사례(부분적으로만 인식 가능한 외래어 등)에서는 여전히 Claude의 최종 판단에 의존하며 잔여 오판 가능성을 완전히 배제할 수 없음. 2주차에 기존 15샘플을 재실행하여 몇 건의 symptom/intervention/status/notification 매칭이 재분류되는지, 그리고 Style별 CCER 순위에 영향이 있는지 정량화할 예정 |

---

## 5. CCER 공식: Whisper-only(환각성 삽입) 페널티 반영

| 항목 | 내용 |
|---|---|
| **Original Design** | `src/evaluation/ccer_eval.py`는 `CCER = sum(weight_i * count_i) / gold_entity_count`를 Gold 대응이 있는 레코드에 대해서만 계산했으며, `whisper_only` 레코드(Gold 대응 없이 Whisper 전사에만 존재하는 Entity)는 `error_type=None`으로 남아 분자 집계에서 조용히 제외됨 |
| **Issue observed during implementation** | 한계 6으로 기록됨. Whisper/추출 파이프라인이 Gold에 없는 임상 정보(가짜 증상, 장치, 용량 등)를 환각으로 추가 삽입해도 전혀 페널티를 받지 않았음. 이런 삽입은 기록을 읽는 사람을 실제로 오도할 수 있음에도 그러함 |
| **Design Decision** | `src/evaluation/flatten_matches.py`가 `match_status="whisper_only"`인 모든 레코드(Closed/Open-vocabulary 양쪽 경로 전부)에 `error_type="hallucination"`을 부여하도록 변경. `src/evaluation/ccer_eval.py`의 `ERROR_WEIGHTS`에 `"hallucination": 3`을 추가(`numeric_error`/`negation_flip`/`severity_shift`와 동일 등급). 분모(`gold_entity_count`)는 변경하지 않음 — `whisper_only` 레코드는 애초에 `gold_value=None`이라 분모에 포함된 적이 없었음 |
| **Reason** | 환각성 삽입은 기존 값을 왜곡하는 것(numeric/negation/severity 오류)과 유사한 수준의 환자 안전 위험을 갖는다고 판단함 — 하나는 사실을 바꾸고, 다른 하나는 없는 사실을 만들어낸다는 차이가 있을 뿐, 둘 다 독자가 환자의 실제 상태와 다른 정보에 기반해 행동하게 만들 수 있음. 이는 검증된 임상 심각도 척도가 아닌 연구자의 근사적 판단이며(기존 `ERROR_WEIGHTS` 설계와 동일한 한계), 임상 전문가 검토(한계 8) 이후 조정될 수 있는 후보임 |
| **Impact on the evaluation pipeline** | Whisper-only 삽입이 있는 샘플의 CCER 점수는 v1 대비 반드시 같거나 높아짐(분자만 증가할 수 있고 분모는 그대로이므로). 파일럿에서 보고된 WER-CCER 역전 현상(Telegraphic ICU가 CCER 기준 최우수, WER 기준 최저)이 이 변경 이후에도 유지되는지는 환각성 삽입이 Style별로 어떻게 분포하는지에 달려 있으며, 이는 정확히 2주차에 15샘플을 재실행하며 50샘플 확장 이전에 확인하고자 하는 지점임 |

---

## 6. Clinical Entity Taxonomy: 독립 감사, 외부 표준 근거, v3 파이프라인 정렬

| 항목 | 내용 |
|---|---|
| **Original Design** | v2 taxonomy는 파이프라인을 만드는 과정에서 Content Scaffold의 필드로부터 유기적으로 파생된 8개 entity type(`vital_sign`, `symptom`, `clinical_status`, `dose`, `route`, `frequency`, `intervention`, `notification`, `device`)으로 구성되었으며, 외부 임상 정보 표준과 독립적으로 대조 검증한 적은 없었음 |
| **Issue observed during implementation** | 스타일 간 hallucination 건수가 우연히 정확히 일치하는 이상 징후를 계기로 구조적 조사를 진행한 결과, Gold/Whisper 간 두 가지 카테고리 불일치를 발견함: ① `device`/`oxygen_support` scaffold 필드가 Gold 쪽에서는 closed-vocab `device`로만 잡히는데, Whisper 쪽 open-vocab `interventions` 추출기는 같은 실제 사실을 자유 텍스트 intervention으로 독립적으로 재추출하고 있었고, Gold 쪽엔 대응하는 open-vocab 항목이 없어 체계적인 가짜 hallucination을 만들어내고 있었음. ② scaffold의 `io`(intake/output) 필드는 애초에 Gold entity type 어디에도 매핑되지 않아, Whisper가 이를 정확히 전사해도 무조건 hallucination으로 집계됨. 이어진 체계적 audit(`docs/taxonomy_audit.md`)에서는 `medication.name`(약물 정체)도 Gold·Whisper 양쪽 어디에도 표현되지 않아, CCER이 약물 오인 오류를 탐지할 방법 자체가 없다는, 세 가지 중 가장 환자안전상 중대할 수 있는 공백도 추가로 발견함 |
| **Design Decision** | 이 세 발견을 곧바로 패치하는 대신, 독립적인 taxonomy audit을 먼저 수행함(`docs/taxonomy_audit.md` §1–§4): Scaffold의 모든 필드를 임상적 의미와 함께 목록화하고, 기존 Gold/Whisper 변환 코드를 필드 단위로 감사했으며, 각 후보 카테고리를 HL7 FHIR R4/R5 resource 경계 및 SNOMED CT 최상위 계층과 대조함(개념적 참고에 한정 — FHIR/SNOMED 코드나 스키마를 그대로 채택하지 않음. 빌린 것/안 빌린 것의 명확한 경계는 `taxonomy_audit.md` §7 참고). 그 결과 11개 카테고리로 확정된 taxonomy가 나왔음(§5): `medication_identity`, `intake_output`을 신규 open-vocab 카테고리로 추가, `device`/`oxygen_support`를 하나의 `device` 카테고리로 통합(SNOMED의 "Physical object" 계층에 둘 다 속함), `intervention`의 범위를 투약/장치/섭취배설 관련 내용을 명시적으로 제외하도록 축소, `patient_context`를 CCER 범위에서 명시적으로 제외(인구통계·진단 정보는 CCER이 다루는 "임상적으로 실행 가능한 정보"와는 성격이 다른 정보). 전체 pipeline alignment table(§8)로 11개 카테고리 중 실제로 코드 수정이 필요한 건 3개뿐임을 확인했고, 나머지 8개는 손대지 않음. `medication_identity`에는 다른 자유 텍스트 필드보다 엄격한 매칭 규칙을 추가로 부여했으며, 이는 ISMP의 Confused Drug Names 목록(LASA — Look-Alike, Sound-Alike 약물)에 근거함: 철자·발음의 유사성만으로는 매칭 근거가 되지 않는다는 것을 명시하여, 실제 약물 오인 오류가 은폐되는 것을 방지함 |
| **Reason** | 이 프로젝트의 방법론적 원칙은 관찰된 오류 건수를 줄이기 위해 taxonomy를 사후적으로 조정하지 않는다는 것이었으며, 그렇게 하면 논문에서 임상적 타당성을 방어하기 어려워짐. Taxonomy를 외부의 독립적인 표준에(비록 개념적으로만이라도) 근거하고, 전체 pipeline alignment table로 실제로 불일치가 확인된 카테고리에만 수정이 적용됐음을 검증한 것은 "왜 하필 이 카테고리들이고, 왜 지금인가"라는 질문에 관찰된 hallucination 건수만이 아니라 방어 가능한 답을 제공함 |
| **Impact on the evaluation pipeline** | 5개 구현 단계(`scaffold_as_gold.py`, `open_vocab_extractor.py`, `semantic_matcher.py`, `flatten_matches.py`, `ccer_eval.py`) 전부 API 호출 없이 유닛 테스트를 거쳤고, 실제 15샘플 재실행 전에 실제 파일럿 전사문으로 spot-check까지 완료함. 재실행 후 pipeline sanity audit(`results/pilot_15/v3_taxonomy_aligned/VERSION_NOTES.md`)에서 의도한 3가지 수정이 실제 데이터에서 전부 설계대로 작동함을 확인함(`medication_identity`: 15/15 정상 매칭, `intake_output`: 9/9 정상 매칭, device/oxygen_support의 intervention 중복: 28건 → 0건), 손대지 않은 8개 카테고리는 회귀 없이 v2와 완전히 동일한 건수를 유지함. CCER은 15개 샘플 전부에서 큰 폭으로 하락했고(스타일별 평균 -0.62~-0.69로 균일 — 특정 스타일을 봐준 게 아니라 구조적 오염을 고르게 제거했다는 근거), WER-CCER 역전 순위(Telegraphic ICU 최우수, Formal Template 최악)는 v1/v2/v3 내내 유지되어 이 발견이 파이프라인 결함이 아닌 진짜 현상이라는 확신을 강화함. Audit 과정에서 v3와 무관한 사전 존재 잔여 문제 3건(dose 정규식의 vital_sign/intake_output 수치 오염, 한 노트 내 동일 장치 중복 언급, symptom/patient_context/clinical_status 경계 누수)도 추가로 발견했으며, 이는 taxonomy를 사후적으로 계속 넓히지 않는다는 원칙에 따라 v3 범위에서 의도적으로 제외하고 한계 #10~12 / Future Work로 기록함. v1/v2/v3 결과는 각각 별도로 보존되어(`results/pilot_15/v1_baseline`은 git 히스토리로 재구성 가능, `v2_hallucination_phonetic/`, `v3_taxonomy_aligned/`) `taxonomy_audit.md` §6의 버전 관리 계획에 따라, 이후 분석(Error Profile, effect size, power analysis)에서 관찰되는 어떤 차이든 그 원인이 된 구체적인 방법론적 변경까지 추적 가능함 |