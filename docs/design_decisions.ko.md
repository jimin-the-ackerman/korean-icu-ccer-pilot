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

---

## 7. Closed-Vocabulary Extraction: 스타일 의존적 편향 발견 및 Style-Invariant 수정 (v4)

| 항목 | 내용 |
|---|---|
| **Original Design** | `closed_vocab_extractor.py`의 `vital_sign`/`route`/`frequency`/`device` 정규식은 영어 약어(`BP`, `IV`, `q4h`, `NC` 등)만 인식했다. "임상 entity label은 Documentation Register와 무관하게 이 형태로 일관되게 나올 것"이라는, 독립적으로 검증된 적 없는 가정에 기반한 설계였다 |
| **Issue observed during implementation** | 100개 시나리오 데이터셋에 사전 등록된 Statistical Analysis Plan(`docs/statistical_analysis_plan.md`)을 실행하던 중, SAP #4(Error Profile)에서 Formal Template의 `vital_sign` 오류율이 100%(500/500)로 나왔다 — 지나치게 딱 떨어지는 숫자였다. 실제 샘플 하나를 Gold Scaffold → 생성 텍스트 → Whisper 전사 → 추출 entity → 최종 매칭까지 끝까지 추적한 결과 근본 원인이 드러났다: `style_controller.py`의 `CODE_SWITCHING_RULE`은 모든 스타일에서 임상 entity label에 영어/표준 약어를 쓰라고 지시하지만, 이는 Formal Template 고유 규칙("완전한 임상 용어 선호")과 충돌했고, GPT-4o가 이 충돌을 스타일별로 일관되지 않게 해소했다 — Formal Template은 활력징후 라벨, 투여경로, 빈도, 장치를 한국어 완전 표기(`혈압`, `정맥으로`, `매 4시간마다`, `비강 캐뉼라`)로 자주 렌더링했는데, 이는 Whisper가 그 숫자를 정확히 전사했는지와 무관하게 영어 전용 정규식이 절대 인식할 수 없는 형태였다. 100개 시나리오 전수 스캔으로 이것이 우발적 사례가 아니라 체계적임을 확인함: 영향받은 4개 entity type 전부에서 Formal Template의 Whisper 전사문에 영어 약어가 아예 없는 비율이 87~100%였다 |
| **Design Decision** | 관찰된 오류 건수를 줄이기 위해 한국어 정규식을 즉흥적으로 추가하는 대신(사용자가 명시적으로 post-hoc tuning 위험으로 지적함), §6의 taxonomy audit과 동일한 audit-then-freeze 절차를 따랐다: (1) 모든 closed-vocabulary entity type과 현재 인식 가능한 surface form을 전수 목록화; (2) `docs/reference_analysis.md`의 약어 출처, `style_controller.py`의 스타일 설계 의도, 표준 한국어 임상 용어에 근거해 `surface form → canonical concept/value → 비교` 구조와 canonical lexicon을 설계 — 100개 시나리오의 실패 문자열을 보고 역산한 게 아님; (3) 코드 재검토로 `entity_matcher.py`가 이미 canonical 값만 놓고 비교하는 구조임을 확인해 매칭 로직은 전혀 안 건드리고 추출기만 수정하는 것으로 범위를 좁힘; (4) 구현 전에, `medication_dose`의 기존 문맥 무관 매칭 버그(주변 숫자를 문맥과 무관하게 dose로 잡는 문제)도 같은 수정에 포함시키기로 명시적으로 결정 — `medication_dose`의 ownership을 "특정 명명된 약물의 투여량"으로 재정의하고, route/frequency/투약 동사는 그 정의 자체가 아니라 문맥을 추정하는 deterministic proxy로 규정했으며, 섭취/배설량 값과 범용 IV 수액 volume은 명시적으로 제외(후자는 이미 확정된 `intervention` 카테고리 소관); (5) 확정 전에 사소하지 않은 모든 추가 사항을 실제 100개 데이터로 실증 검증 — 예를 들어 한국어 route 표현 "정맥" 단독형은 100개 시나리오 전체를 스캔한 결과 실제 등장의 29%가 다른 카테고리(device 또는 symptom, route 아님)였음을 확인해 단순 substring 매칭 대신 접미사 기반 인정 규칙을 채택했고, SpO2의 label-value 문법(라벨 뒤에 산소 맥락 수식어가 낀 뒤 퍼센트 값이 오는 구조)은 실제 omission 55건을 군집화해 82%를 커버하는 단일 일반화 문법으로 구성했으며 임의 폭의 윈도우가 아니라 닫힌 whitelist로 구현했고, 인식 못한 수식어 표현 때문에 파서가 무관한 유량 숫자를 SpO2 값으로 잘못 포착한 false positive를 발견한 뒤 값 끝에 `%`를 요구하도록 보강함 |
| **Reason** | 이 프로젝트의 `docs/taxonomy_audit.md` §6.4 원칙 — 관찰된 결과에 맞춰 evaluator를 사후 조정하지 않는다 — 는 taxonomy 자체뿐 아니라 추출 계층에도 똑같이 적용된다. CCER 지표가 taxonomy 수준(§6)에서 아무리 건전하게 설계돼도, 그 밑의 추출 계층이 특정 실험 조건에 구조적으로 불리하다면 임상적으로 오도하는 결론을 낼 수 있다. 이를 고치는 데도 같은 원칙이 필요했다 — 코드를 작성하기 *전에* 독립적 근거(설계 문서, 외부 용어집, 실제 데이터 검증)에 기반한 spec을 먼저 확정하고, 숫자가 원하는 대로 나올 때까지 반복 조정하는 게 아니라 명시적인 회복률/비파괴/false-positive 검증으로 확인하는 것 |
| **Impact on the evaluation pipeline** | 실제 데이터 검증이 두 라운드 필요했다. 1라운드(라벨 인식만)는 Formal Template의 `vital_sign` 인식률을 0%→100%로 올리고 route/frequency/device 인식도 크게 개선했지만, 두 번째 sanity audit(Formal Template의 `numeric_error`가 전체의 336/338건으로 급증한 데서 촉발)에서 이 중 대부분이 진짜 ASR 오류가 아님을 발견했다: Gold 값은 scaffold 원본 단위를 그대로 유지(`"120 bpm"`)하는 반면 Whisper 쪽 값은 순수 숫자(`"120"`)뿐이라, 전사가 완벽해도 가짜 mismatch가 발생했다 — 파이프라인 최초 버전부터 있던 버그였는데, 1라운드로 Formal Template의 라벨이 대량으로 처음 매칭되기 전까지는 드러나지 않았다. 2라운드(Gold/Whisper 값 canonicalization, BP 구분자 정규화, 위 SpO2 문법)는 사용자가 사전에 지정한 3가지 기준으로 실제 데이터 검증을 거쳤다: (1) 원래 SpO2 삽입구 omission 55건 중 49건(89%)이 회복됐고, 남은 6건은 파서 공백이 아니라 진짜 STT 값 손상임을 확인; (2) 기존에 correct였던 SpO2 매칭 38건 전부 그대로 유지(회귀 0건); (3) 전체 데이터 false-positive 스캔에서 처음엔 2건의 가짜 매칭을 발견(숫자 없는 `%`, 그리고 인식 못한 수식어 표현으로 무관한 유량 숫자를 포착한 경우)했으나 SpO2 값이 `%`로 끝나야 한다는 요구조건 추가로 둘 다 해소했고, 재스캔에서 431건 추출 전체 중 의심 값 0건. 수정된 결과는 이 프로젝트의 핵심 발견을 뒤집었다: CCER(v3→v4)이 Formal Template에서만 유독 크게 하락했고(1.3746→0.8417; Clinical Charting과 Telegraphic ICU도 하락했으나 폭이 훨씬 작음 — 각각 1.2693→1.1682, 1.3682→1.2134 — 이는 이 수정이 균일한 스케일링이 아니라 한 조건에 집중된 편향을 바로잡았다는 근거), Formal Template이 CCER 최악에서 최선으로 뒤집혀 이미 최선이었던 WER·Entity-level F1과 일관되게 됐다. Kendall's W는 0.030→0.391로, Friedman test는 경계적 유의(p=0.049)에서 p=1.09×10⁻¹⁷로 이동했고, Formal Template이 CCER 최선이라는 결론은 `docs/statistical_analysis_plan.md` §3의 사전 등록된 5개 가중치 scheme 전부에서 유지됐다(이번 수정 전엔 5개 중 4개에서만 유지). 명시적 지시에 따라 이 역전은 추가 조정의 근거가 아니라 수정된(올바른) 결과로 받아들여졌다 — 목표는 특정 사전 결론을 지키는 게 아니라 evaluator 편향을 제거하는 것이었다. v1/v2/v3 결과는 비교용으로 그대로 보존되며(`results/pilot_15/`, `results/full_50/`, `results/full_100/`), `results/full_100_v4/`가 최종 해석의 유일한 근거임 |
---

## 8. 탐색적 Hybrid Register: 사후 관찰에서 동기부여된 Entity-Informed 설계

| 항목 | 내용 |
|---|---|
| **Original Design** | Primary 실험은 정확히 3개의 Documentation Register(Formal Template, Clinical Charting, Telegraphic ICU)만 비교했고, 각각을 노트 전체에 균일하게 적용했다 |
| **Issue observed during implementation** | 사후 민감도 분석(Macro-CCER, aggregate 결과를 본 뒤 추가 — `docs/statistical_analysis_plan.md`에 명시적으로 사후 표기)에서 Formal Template의 aggregate CCER 우위가 entity type 전체에 균일하지 않다는 게 드러났다: Formal이 11개 중 8개에서 이겼지만 `device`, `dose`, `route`에서는 오히려 Clinical Charting에 졌다 |
| **Design Decision** | 이를 단순한 서술적 각주로 취급하지 않고, entity-informed register 조합이 여러 register의 강점을 한 노트 안에서 회복할 수 있는지 검증하는 네 번째 탐색적 register("Hybrid")를 설계했다. 결정적으로, block mapping(활력징후/서술 정보는 Formal 방식, 투약 사건+장치/산소공급은 Clinical 방식)을 3개의 사전 등록 방향성 가설(H1-H3), manipulation-check 계획과 함께 Hybrid 데이터를 생성하기 **이전에** `docs/hybrid_followup_spec.md`에 확정했다. v4 수정(§7)이 방금 제거한 것과 같은 종류의 confound를 이 탐색적 설계가 다시 만들지 않도록, 두 가지 설계 선택을 특별히 고정했다: (1) frequency를 Clinical block에 포함시킨 건 frequency 자체의 entity-level 성능 때문이 아니라 — 실제로는 그 반대로 Formal이 더 나았다(0.687 vs. 1.192) — 이미 존재하는, 결과와 무관한 Medication Expression Rule(약물명/용량/투여경로/투여빈도가 이미 하나의 문법적 단위로 렌더링되도록 요구)이 근거였다는 걸 명시적으로 문서화 — 이는 사전에 문서화된 trade-off이지 공짜 선택이 아니다; (2) 모든 Formal-style 사실을 모든 Clinical-style 사실보다 앞에 배치했던 초기 설계안은, 관찰되는 어떤 효과에 대해서든 *register*와 *정보 순서*가 서로 경쟁하는 설명이 되는 confound를 만들 수 있다는 이유로 명시적으로 기각됐다 — 최종 설계는 Content Scaffold의 자연스러운 사실 순서를 유지하고 각 사실이 표현되는 방식만 바꾼다 |
| **Reason** | 이 프로젝트가 반복해서 지켜온 원칙 — 원하는 결과와 독립적으로 수집된 근거로 설계 변경을 평가하고, 숫자가 원하는 대로 나올 때까지 반복 조정하는 게 아니라 실제 데이터로 검증한다 — 는 evaluator 버그를 고치는 것만큼이나 새로운 실험 조건을 구성하는 데도 적용된다. Hybrid mapping이 구조적으로 primary 실험 자체의 결과에서 정보를 얻어 설계됐기 때문에, 이 설계는 통상적인 audit-then-freeze 규율을 넘어 두 가지 추가 안전장치를 적용받았다: 단일(single) mapping으로만 만들고 확정했으며(Hybrid-B/Hybrid-C 변형을 만들어 비교하지 않음 — 더 미묘한 형태의 post-hoc tuning 위험을 피하기 위함), 가설을 pass/fail 성공 기준이 아니라 방향성으로 서술했고, 비유의 검정 결과를 동등성의 증거로 취급하지 말라는 지시를 명시적으로 포함했다 |
| **Impact on the evaluation pipeline** | 결정론적 manipulation check(`closed_vocab_extractor.py` 재사용, 추가 API 호출 없음)로 음성합성 이전에 block mapping이 생성된 텍스트에 실제로 구현됐는지 확인했다: route/frequency/device 344건 중 314건(91.3%)이 영어 약어 형태로, 활력징후 488건 중 488건(100.0%)이 한국어 완전 표기로 렌더링됨을 확인. 이 결과는 있는 그대로 기록했고(생성 프롬프트 재조정에 쓰지 않음), Clinical block의 ~8.7% 비준수는 GPT-4o가 충분히 관행적인 한국어 의료 용어로 판단해 약어로 안 바꾼 3가지 구체적 device 개념으로 추적됐다. 그 결과 Hybrid register(`results/hybrid_followup/`, frozen primary 결과인 `results/full_100_v4/`와 엄격히 분리 보존)는 Formal Template보다 micro-CCER이 21% 낮았고(0.842→0.666), scenario-level 쌍체 Wilcoxon test(W=1070, p=7.07×10⁻⁶)로 확인됐다 — H1과, device/dose/route에 대해서는 H3도 지지됐다. 하지만 `frequency` CCER은 Hybrid 하에서 오히려 **악화**됐다(0.687→1.343) — Clinical Charting 자체의 이미 더 나빴던 frequency 성능(1.192)보다도 나쁘다 — 이는 사전에 문서화한 trade-off가 중요하지 않았던 헤지가 아니라 진짜 비용이었음을 확인해준다. 이 negative finding은 정직하게 사전 지정된 결과라는 이 프로젝트의 기존 원칙에 따라, 긍정적 결과와 동등한 비중으로 보고했다 |
