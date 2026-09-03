# v4: Style-Invariant Clinical Concept Canonicalization — Audit & Specification

**상태: FREEZE.** 이 문서는 최종 확정본이다(§9 참고). 이후 결과를 보고
방법론이나 기준을 재조정하지 않는다.

**작성 원칙**: 이 문서는 100개 Formal Template 결과에서 실패한 문자열을 보고
역산해서 만든 목록이 **아니다**. Content Scaffold의 canonical concept,
`style_controller.py`의 스타일 설계 의도, `docs/reference_analysis.md`의 약어
출처, 표준 한국어 임상 용어를 근거로 독립적으로 확정한다.

**핵심 설계 원칙(사용자 확정)**: surface form이 아니라 clinical concept를
비교한다. `surface form → canonical concept/value → comparison` 3단계로
분리하며, 번역 모델/LLM을 중간에 넣지 않는다(결정론적 규칙만 사용 — CCER이
STT 정보 보존이 아니라 번역 정확도까지 측정하게 되는 것을 방지).

---

## 1. Entity Type 목록 + 현재 Extraction/Normalization 방식

`closed_vocab_extractor.py`(추출)와 `entity_matcher.py`(매칭)를 함께 재확인한
결과, **매칭 로직은 이미 canonical key + value 비교 구조로 설계되어 있다**는
중요한 사실을 확인했다:

- `match_vital_signs()`: `label`(canonical key, 예: `bp`)로 먼저 매칭하고
  `value`는 별도로 비교 — 값이 다르면 `numeric_error`
- `match_value_list()`(route/frequency/device 공용): `normalized`(canonical
  value)로 비교 — omission 1건+whisper_only 1건이면 substitution 휴리스틱이
  `ENTITY_TYPE_ERROR_MAP`(`route_error`/`frequency_error`/`device_error`)으로
  전환

즉 **`entity_matcher.py`는 surface form을 전혀 모른 채로 이미 canonical
representation만 놓고 비교하고 있다.** 이번 문제의 근원은 순수하게
`closed_vocab_extractor.py`가 canonical 값 공간(`iv`, `bp`, `q4h`, `foley` 등)
으로 정규화하기 **전** 단계, 즉 surface form 인식 범위가 영어로 국한돼있다는
것뿐이다. (§7, §8에서 이 결론의 함의를 다룬다.)

| # | Entity Type | 현재 추출 방식 | 현재 정규화 방식 |
|---|---|---|---|
| 1 | `route` | `ROUTE_DICT` 정확 일치(영어만) | 사전 값 그대로(`IV`→`iv`), `SC`/`SUBQ`→`sc`로 동의어 통합 이미 존재 |
| 2 | `frequency` | `FREQUENCY_DICT` + `FREQUENCY_QH_PATTERN`(영어만) | `BID`→`bid` 등 그대로, `q{N}h`는 정규식으로 값(N) 추출 후 `q{N}h` 문자열로 정규화 |
| 3 | `device` | `DEVICE_PATTERNS` 정규식(영어만) | 여러 surface form(`nasal cannula`/`NC`/`high-flow nasal cannula`)이 이미 `nc` 하나로 통합되는 동의어 정규화가 존재 |
| 4 | `vital_sign` | `VITAL_SIGN_PATTERN` 정규식(영어만) | `label`(예: `spo2`/`spo₂`/`sat`→`spo2`)과 `value`를 분리 저장 — canonical key/value 구조가 이미 부분적으로 구현됨 |
| 5 | `dose` | `DOSE_PATTERN` 정규식(단위는 영어 표준 단위로 스타일 공통 규정) | 단위 소문자화만; **문맥 무관하게 숫자+단위만 잡아 다른 entity 값을 오인하는 기존 문제(한계 #10) 있음** — 이번 §6에서 재사용할 반면교사 |

**결론**: 현재도 "동의어를 canonical 값으로 통합"하는 정규화 패턴 자체는
이미 코드에 존재한다(예: SC/SUBQ→sc, 여러 nasal cannula 표현→nc). 이번
작업은 이 기존 패턴을 **영어 동의어뿐 아니라 한국어/영어 전체 표기까지
포함하도록 확장**하는 것이며, 새로운 아키텍처를 도입하는 게 아니라 기존
아키텍처를 완성하는 것에 가깝다.

---

## 2. Surface Form 지원 현황 + 누락 + 스타일 편향 점검

100개 Whisper 전사문 전수 스캔 결과(이전 조사에서 확인):

| Entity Type | 영어 약어/단어가 Formal Template 전사문에 아예 없는 비율 |
|---|---|
| `vital_sign` | 100% (500/500) |
| `route` | 87% (87/100) |
| `frequency` | 92% (91/99) |
| `device` | 88% (71/81) |

**구조적 편향 확인**: `style_controller.py`의 `CODE_SWITCHING_RULE`은 "clinical
entity label은 모든 스타일에서 영어/표준 약어를 선호하라"고 명시하지만,
Formal Template 고유 규칙("완전한 임상 용어 선호")과 상충되어 GPT-4o가
스타일별로 일관되지 않게 처리했다. Clinical Charting/Telegraphic ICU는
스타일 규칙 자체가 "표준 약어 사용"을 명시적으로 요구해 이 충돌이 없다 —
**즉 Formal Template만 구조적으로 불리한 상태였다.**

---

## 3. Canonical Representation 설계

### 3.1 `vital_sign`

| Canonical Key | Canonical Value 형태 | 한국어 표기 | 영어 전체 표기 | 약어 |
|---|---|---|---|---|
| `bp` | `"수축기/이완기"` 문자열(예: `"120/80"`) | 혈압 | blood pressure | BP |
| `hr` | 정수 문자열 | 심박수, 맥박 | heart rate, pulse | HR |
| `rr` | 정수 문자열 | 호흡수, 호흡 | respiratory rate, respiration | RR |
| `bt` | 소수 문자열(°C 단위 고정) | 체온 | body temperature, temperature | BT |
| `spo2` | 정수+`%` 문자열 | 산소포화도 | oxygen saturation | SpO2, SpO₂, SAT |

- **정규화 규칙**: (라벨 사전 lookup, 대소문자/공백 무시) → canonical key.
  값은 key별로 다른 하위 패턴 사용 — `bp`만 `\d+/\d+` 형태, 나머지는
  `\d+(\.\d+)?%?` 형태. 라벨 사전에는 한국어 항목(`혈압`, `심박수`, `맥박`,
  `호흡수`, `호흡`, `체온`, `산소포화도`)과 영어 전체 표기를 모두 등록한다.
- **비교 규칙**: `entity_matcher.match_vital_signs()`을 그대로 사용(변경 없음)
  — canonical key로 매칭, value 문자열이 다르면 `numeric_error`.

### 3.2 `route`

| Canonical Value | 한국어 표기 | 영어 전체 표기 | 약어 | 음차(§3.6 기준 적용) |
|---|---|---|---|---|
| `iv` | 정맥으로, 정맥주사(로), 정맥 주사로, 정맥 내, 정맥 수액 | intravenous | IV | 아이비 |
| `po` | 경구, 경구로 | oral, per os | PO | — |
| `im` | 근육, 근육주사, 근육으로 | intramuscular | IM | — |
| `sc` | 피하, 피하주사, 피하로 | subcutaneous | SC, SUBQ | — |
| `sl` | 설하, 설하로 | sublingual | SL | — |
| `pr` | 직장, 직장으로 | rectal, per rectum | PR | — |

**"정맥" 단독형 처리 방침 (100개 데이터 실증 스캔 완료)**: 100개 시나리오
전체 Gold+Whisper 텍스트에서 "정맥"을 포함하는 어절을 전수 스캔한 결과
42건 중 30건(71%)이 route 의미, 12건(29%)이 **route가 아닌 다른 개념**
(`정맥관` 7건 = device/C-line, `정맥류` 4건 = symptom/식도정맥류출혈,
`정맥관(C-line)` 1건 = device)이었다. route로 쓰인 30건은 전부 `정맥으로`,
`정맥 주사로`, `정맥 내`, `정맥주사로`처럼 특정 접미사가 뒤따르는
형태였고, `정맥` 뒤에 `관`이나 `류`가 바로 붙으면 예외 없이 다른 개념이
되었다.

**확정 규칙**: `정맥`은 뒤따르는 접미사가 `으로`/`주사`/`내`/`수액` 중
하나일 때만 route로 인정한다. 뒤에 `관` 또는 `류`가 바로 이어지면
**명시적으로 제외**한다(negative lookahead). 단독 `정맥`(접미사 없이 그
자체로 끝나는 경우)은 이번 100개 데이터에는 없었으므로 인정하지 않는다
— 향후 확장 데이터에서 재검토 가능.

- **정규화 규칙**: 순수 dictionary lookup(값 개념 없음, 카테고리 자체가
  정보). 정규식/value parsing 불필요.
- **비교 규칙**: `entity_matcher.match_value_list()` 그대로 사용(변경 없음).

### 3.3 `frequency`

| Canonical Value | 한국어 표기 | 영어 전체 표기 | 약어 | 음차(§3.6 기준 적용) |
|---|---|---|---|---|
| `bid` | 하루 2회, 하루에 2번 | twice daily | BID | — |
| `tid` | 하루 3회, 하루에 3번 | three times daily | TID | — |
| `qid` | 하루 4회, 하루에 4번 | four times daily | QID | — |
| `prn` | 필요시, 필요할 때 | as needed | PRN | — |
| `stat` | 즉시 | immediately | STAT | 스탯 |
| `q{N}h` | 매 {N}시간마다, {N}시간마다 | every {N} hours | q{N}h | — |

- **정규화 규칙**: `bid`/`tid`/`qid`/`prn`/`stat`는 순수 dictionary.
  `q{N}h`만 **값 파싱이 필요**(N을 추출해 `q{N}h` 문자열로 정규화) — 한국어
  패턴(`매\s*(\d+)\s*시간마다`, `(\d+)\s*시간마다`)에서 N을 추출해 기존
  `FREQUENCY_QH_PATTERN`과 동일한 정규화 문자열을 생성한다.
- **비교 규칙**: `match_value_list()` 그대로 사용. gold `q4h` vs whisper
  `q6h`처럼 N이 다르면 문자열이 달라지므로 자동으로 omission+whisper_only
  1건씩 잡히고, 기존 substitution 휴리스틱이 `frequency_error`로 전환 —
  **이미 "값이 다르면 error로 잡히는" 요구사항을 충족하는 구조**임을 확인.

### 3.4 `device`

| Canonical Value | 한국어 표기 | 영어 표기 |
|---|---|---|
| `foley` | 폴리 카테터, 유치도뇨관 | Foley, Foley catheter |
| `c-line` | 중심정맥관 | C-line, central line |
| `ventilator` | 인공호흡기 | ventilator |
| `ng tube` | 비위관 | NG tube, nasogastric tube |
| `nc` | 비강 캐뉼라 | nasal cannula, NC, high-flow nasal cannula |

- **정규화 규칙**: 순수 dictionary(카테고리 자체가 정보, 값 없음).
- **비교 규칙**: `match_value_list()` 그대로 사용(변경 없음).

### 3.5 `dose` — 이번 v4 범위에 포함 (Entity Ownership 기반 재설계, 최종)

기존 `DOSE_PATTERN`은 문맥 무관하게 "숫자+단위"만 잡아 vital_sign(BP가
STT로 뭉개진 경우, 예: "90-60mg")이나 intake_output(예: "200mL") 값을
dose로 오인하는 문제가 있었다(한계 #10). 100개 데이터 기준 dose
hallucination이 **92건** 발생, 상당수가 이 오염 문제로 확인됨.

**Ownership 정의(고정)**:

> `medication_dose` = **특정 약물(named medication)의 투여량**. 생리학적
> 측정값(vital_sign), 섭취/배설량(intake_output), 범용 수액 투여량(fluid
> administration volume — 현재 v3 taxonomy상 `intervention` 소관)은
> 제외한다.

이 정의가 ownership의 **본질**이다. 아래 3~4단계에서 쓰는 route/frequency/
투약 동사 신호는 **이 정의 자체가 아니라, "이 숫자+단위가 실제로 특정
약물 투여 문맥에 속하는가"를 텍스트 규칙만으로(LLM 없이) 판별하기 위한
deterministic proxy**일 뿐이다. 이상적으로는 "이 숫자 근처에 약물명이
있는가"를 직접 봐야 하지만, 약물명은 open-vocab(`medication_identity`,
Claude 기반)이라 closed-vocab 추출기가 직접 참조할 수 없다(§6 Architecture
A 채택 이유). 그래서 route/frequency/투약 동사라는, 텍스트 규칙만으로
확인 가능한 **간접 신호**로 이 문맥을 추정한다.

**Deterministic Extraction Hierarchy**:

```
1단계: 숫자+단위 후보 탐지 (기존 DOSE_PATTERN과 동일)

2단계: 더 구체적인 소유권을 가진 entity_type부터 배제 (순서 중요, 거리 무관)
   2a. 이 숫자가 vital_sign 패턴(BP/HR/RR/BT/SpO2 라벨 뒤 숫자)에 의해
       이미 캡처된 값이면 → dose 후보에서 제외
   2b. 단위가 부피 단위(mL/L/cc)이고, 직전 문맥이 io 어휘(urine/output/
       소변량/섭취량/배설량/drain/배액량) 또는 범용 수액 명칭 denylist
       (IV fluids/NS/normal saline/D5W/LR/수액, §3.5.1)와 일치하면 →
       dose 후보에서 제외

3단계: 2단계를 통과한 후보만 medication-administration context(proxy
   신호) 확인
   - 같은 절(또는 관련 텍스트 단위) 안에 route/frequency 매칭 존재, 또는
   - 투여/주입/복용/처방/administer/given류 투약 동사 존재
   둘 다 없으면 최종 배제

4단계: 구두점/거리는 3단계에서 "같은 절"을 판별하는 **보조 파싱 수단**으로만
   사용(판정 기준 자체가 아님)
```

**2단계가 이전 설계와 다른 점**: 이전엔 BP 오염 사례를 3단계(문맥 신호
탐색) 안에서 거리 비교로 처리하려 했는데, 그러면 Formal Template처럼 한
절 안에 여러 임상 사실이 있는 경우 오탐이 발생했다(실측 확인: 진짜 dose
유지 82%, 가짜 dose 거부 66%). 2단계에서 **더 구체적인 소유권(vital_sign/
io)을 가진 값을 먼저 제외**하면, 그 사례들은 애초에 3단계(절 내 신호
탐색)까지 갈 필요가 없어져 절 길이 문제의 영향을 받지 않는다.

**요청하신 3개 사례의 처리 결과**:

| 입력 | 판정 | 근거 |
|---|---|---|
| `Morphine 2 mg IV` | **medication_dose** | 2단계 통과(vital_sign/io 소유 아님) + 3단계 route(`IV`) proxy 신호 존재 |
| `urine output 200 mL` | **medication_dose 아님** (intake_output 영역) | 2b단계에서 io 어휘로 제외 |
| `BP 90-60mg`(STT로 깨진 vital_sign) | **medication_dose 아님** (vital_sign artifact) | 2a단계에서 vital_sign 라벨 소유로 제외 — 3단계(절 내 신호 탐색) 도달 전에 배제됨 |

### 3.5.1 수액(Fluid Volume) 포함 여부 — 명시적 제외로 확정

`IV fluids 500mL`, `NS 500mL infusion`처럼 특정 약물이 아니라 수액 자체의
투여량을 나타내는 표현은 **`medication_dose`에서 명시적으로 제외**한다
(위 ownership 정의 및 2b단계에 이미 반영됨).

**근거**: v3 taxonomy(`docs/taxonomy_audit.md` §5, freeze됨)에서 수액
투여(예: "fluid resuscitation")는 이미 `intervention`(open-vocab) 카테고리가
다루고 있다(예: scenario_002의 scaffold `intervention: "fluid
resuscitation"`). `medication_dose`는 "특정 약물의 투여량"을 의미하는
카테고리이므로, 일반 수액(생리식염수/NS, IV fluids, D5W, 링거액/LR 등
특정 약물명이 아닌 범용 수액 명칭)의 volume은 애초에 이 카테고리의 대상이
아니다. 이는 경계 사례를 남겨두는 게 아니라, **기존에 이미 확정된
taxonomy 경계를 그대로 따르는 것**이다.

**구현 방향**: 범용 수액 명칭 denylist(`IV fluids`, `NS`, `normal saline`,
`D5W`, `LR`, `수액` 등)를 두어, dose 후보 직전 문맥이 이 denylist와
일치하면 route/frequency가 근접해 있어도 medication_dose로 인정하지
않는다. 이 volume 언급 자체는 이미 `intervention`(open-vocab, Claude
기반)이 "fluid resuscitation" 등으로 독립적으로 포착하고 있으므로 정보
손실은 없다.

---

### 3.6 Phonetic Surface-Form 포함 기준 — `phonetic_artifact` 원칙과의 정합성

`semantic_matcher.py`의 기존 원칙(open-vocab): "Gold 텍스트 없이 그 표현만
보고 한국어 화자가 이해할 수 있는가?"가 `semantic`(인정) vs
`phonetic_artifact`(기각)를 가르는 기준이다. Closed-vocab lexicon에 음차
표현을 포함할지도 이와 정합적인 기준이 필요하다.

**포함 기준(신중하게 표현)**: 단순히 100개 데이터에 등장했다는 이유가
아니라, **해당 clinical domain에서 약어/용어의 established spoken
realization으로 볼 수 있는 경우에만** canonical lexicon에 포함한다. 이는
"표준(standard)"이라고 단정하는 것이 아니라 — 외부 근거(예: 실제 임상
현장에서의 사용 빈도 조사)를 확인하기 전까지는 "표준"이라는 표현 자체를
쓰지 않는다.

| 표현 | 분류 | 이유 |
|---|---|---|
| `IV → 아이비` | conventional abbreviation pronunciation | 영어 약어를 알파벳으로 그대로 읽는 관행(CT/MRI/ICU와 같은 패턴)의 결과로 볼 수 있음 |
| `STAT → 스탯` | conventional clinical spoken form | 외래어를 한국어 음운으로 옮기는 관행적 표기로 볼 수 있음 |
| `chest pain → 체스파인` | idiosyncratic ASR artifact | 이렇게 읽거나 표기하는 관행 자체가 없음, 순수 STT 오류 결과물이며 원문 없이는 이해 불가 |

**포함하지 않는 것**: 특정 STT 결과에서만 우연히 관찰된, 관행적 근거가
없는 음차는 lexicon에 포함하지 않고 기존 `phonetic_artifact` 판정 원칙에
맡긴다(closed-vocab은 애초에 해당 사항 없음 — closed-vocab에 없는
표현은 그냥 omission으로 처리되며, 이는 open-vocab의 phonetic_artifact와
달리 오분류 위험이 없음). 이번 v4에서 closed-vocab lexicon에 추가하는
음차는 `아이비`, `스탯` 두 건으로 제한하며, 향후 추가 음차 표현이
필요하다고 판단되면 이 기준(conventional spoken realization 여부)을
동일하게 적용해 개별 검토한다.

---

## 4. vital_sign / route / frequency / device 심화 — 단순 사전 vs 정규식+값 파싱

| Entity Type | 필요 방식 | 이유 |
|---|---|---|
| `route` | **순수 dictionary normalization** | 값 개념이 없는 순수 카테고리 |
| `device` | **순수 dictionary normalization** | 값 개념이 없는 순수 카테고리 |
| `frequency` (bid/tid/qid/prn/stat) | **순수 dictionary normalization** | 값 개념 없음 |
| `frequency` (q{N}h) | **정규식 + 값 파싱 필요** | N이라는 실제 수치값이 존재, 값 비교 대상 |
| `vital_sign` | **정규식 + 값 파싱 필요** (라벨은 dictionary, 값은 패턴별로 다름) | BP는 복합값(수축기/이완기), 나머지는 단일 수치 — 값 비교가 핵심 |

---

## 5. Entity Ownership / Context Constraint 설계

한계 #10(dose 정규식이 vital_sign/io 숫자를 오염시킨 사례)을 반면교사로,
새 패턴 추가 시 지킬 원칙을 먼저 정한다.

### 5.1 한국어 정규식 특유의 위험 — 단어 경계 문제

영어는 `\b`(word boundary)가 신뢰할 만하지만, 한국어는 조사가 어절에
결합되는 교착어 특성상 `\b`가 기대대로 작동하지 않을 수 있다. 예:
- `정맥`(intravenous route)이라는 패턴을 넣으면, `정맥류`(varicose vein,
  증상 관련 무관한 단어) 안에서도 부분 매칭될 위험이 있다.
- `호흡`(respiration)이 패턴에 들어가면, `호흡곤란`(dyspnea, symptom)
  안에서도 매칭될 수 있다 — `호흡수`(RR)와 `호흡곤란`(symptom)을 구분해야
  하는데 단순 부분 문자열 매칭으로는 안 됨.

**원칙**: 한국어 패턴은 반드시 (a) 완전한 명사형 어절 단위로 매칭하거나
(b) 뒤따르는 특정 접미사/문맥(예: 활력징후 라벨 뒤에는 반드시 숫자가
바로 이어짐, frequency는 반드시 "마다"/"회" 등으로 끝남)을 요구해 대상을
좁힌다. 순수 substring 매칭은 쓰지 않는다.

### 5.2 카테고리 간 충돌 위험 사전 점검

| 위험 패턴 | 충돌 가능 대상 | 방지 설계 |
|---|---|---|
| `호흡` (RR 라벨) | `호흡곤란`(symptom), `호흡 상태 모니터링`(intervention, 한계 #13 사례) | 라벨 뒤에 숫자가 바로 이어지는 경우만 vital_sign으로 인정(기존 영어 패턴도 `[label][:\s]*[숫자]` 구조를 따르므로 동일 원칙 적용) |
| `{N}시간마다` (frequency) | io 관련 서술("4시간 동안 200mL", 한계 #10과 유사) | "마다"로 끝나는 형태만 frequency로 인정, "동안"/"over" 형태는 제외 |
| `정맥` (route) | `정맥류`(symptom), `정맥관`(device) — **100개 데이터 실증 스캔으로 확인**(§3.2) | `으로`/`주사`/`내`/`수액` 접미사 필수, `관`/`류` 바로 뒤따르면 명시적 제외 |
| `비강 캐뉼라`/`인공호흡기` 등 device 한국어 표기 | 낮음(복합 고유 명사라 다른 문맥과 충돌 가능성 낮음) | 그대로 진행 가능 |
| `dose`(숫자+단위) | vital_sign(BP STT 오염), intake_output — **100개 데이터로 원인 확인**(§3.5) | Primary: 같은 절(마침표/줄바꿈 경계) 안에 route/frequency/투약 동사 신호 존재 필수 + vital_sign 라벨과의 상호 배타. 거리 조건은 절 경계를 못 찾을 때만 쓰는 보조 fallback |

### 5.3 검증 방법(코드 작성 후 §10 테스트 계획에서 실행)

새 패턴을 100개 시나리오의 전체 Gold/Whisper 텍스트에 대해 실행해, **의도한
entity_type이 아닌 곳에서 우연히 매칭되는 사례가 있는지** 전수 스캔한다
(현재 dose 문제를 발견했던 방식과 동일한 사후 검증을 새 패턴에도 선제적으로
적용).

---

## 6. v3 taxonomy를 바꾸는가, 별도 layer만 바꾸는가 + Architecture A vs B

### 6.1 taxonomy 변경 여부

**판단: taxonomy는 바뀌지 않는다. 별도 layer(extraction/normalization)만
수정한다.** 근거:
- `docs/taxonomy_audit.md` §5에서 확정한 11개 entity_type 카테고리(어떤
  정보를 다루는가)는 전혀 바뀌지 않음 — `vital_sign`/`route`/`frequency`/
  `device` 카테고리 자체는 그대로 존재
- 바뀌는 것은 "카테고리 안에서 surface form을 canonical 값으로 정규화하는
  방법"뿐 — §1에서 확인했듯 매칭 로직(`entity_matcher.py`)조차 이미
  canonical 값을 전제로 설계돼 있어 바뀌지 않음
- 사용자 판단대로 별도 버전(`v4`)으로 분리하는 것이 맞음 — taxonomy
  freeze(v3)는 그대로 유지하고, 이번 수정은 "evaluator의 style bias
  제거"라는 다른 층위의 methodological correction

### 6.2 Architecture A vs B — dose ownership 구현 방식 비교

**A. 현재 아키텍처 유지 + deterministic ownership hierarchy만 추가(§3.5 채택안)**

| 항목 | 내용 |
|---|---|
| 변경 범위 | `closed_vocab_extractor.py` 하나만 |
| 핵심 한계 | `medication_identity`(open-vocab, Claude 추출)를 positive evidence로 직접 참조하지 못함 — route/frequency/투약동사라는 간접 proxy로만 medication context를 추정 |
| 장점 | open/closed vocab 분리 원칙(`docs/taxonomy_audit.md`) 유지, 구현·검증 범위 작음 |
| 리스크 | route/frequency/투약동사가 전부 생략된 극단적 사례는 여전히 놓칠 수 있음(§10.2b에서 회귀 테스트로 확인) |

**B. `medication_identity + dose + route + frequency`를 하나의 structured
medication tuple로 통합 (v5 후보, 이번 범위 아님)**

| 항목 | 내용 |
|---|---|
| 변경 범위 | `open_vocab_extractor.py`(medication event span 식별), `closed_vocab_extractor.py`(span 내부 전용 재설계), `entity_matcher.py`(span 인식 매칭), `flatten_matches.py`(medication 그룹 재구조화) — open/closed vocab 경계를 가로지름 |
| 핵심 장점 | ownership 문제가 구조적으로 해소 — Claude가 "이 구간은 이 약물에 대한 서술"이라고 확정하면 그 구간 내 숫자+단위는 자동으로 그 약물의 dose로 귀속, proxy 신호 불필요 |
| 리스크 | v3 taxonomy freeze 이후 다시 카테고리 경계(open/closed 분리)를 건드리는 것과 다름없음 — "결과에 맞춰 taxonomy를 재조정하지 않는다"는 기존 원칙과 긴장 관계. `entity_matcher.py`까지 변경 필요(지금까지 "안 건드려도 된다"고 확인했던 파일) |
| 성격 | v4 범위를 넘어서는 별도의 methodological redesign |

**결론(확정)**: **A 채택.** §3.5의 2단계(구체적 소유권 우선 배제)가 B의
핵심 장점(ownership 모호성 제거) 중 상당 부분을 open/closed vocab 경계를
건드리지 않고도 달성하므로, 이번 v4는 A로 진행하고 B는 v5 후보로 남긴다.

---

## 7. 변경 필요 파일 vs 변경 금지 파일

| 파일 | 변경 여부 | 이유 |
|---|---|---|
| `src/entity_extraction/closed_vocab_extractor.py` | 변경 | 이번 수정의 핵심 대상 |
| `tests/test_closed_vocab_extractor.py` (또는 신규 파일) | 추가/변경 | style-invariance 테스트 |
| `src/matching/entity_matcher.py` | 변경 안 함 | §1에서 확인했듯 이미 canonical key/value 비교 구조라 그대로 재사용 가능 |
| `src/entity_extraction/scaffold_as_gold.py` | 변경 안 함 | Gold closed-vocab은 Scaffold 구조화 값에서 나오며(텍스트 정규식 아님), 이번 문제와 무관 |
| `src/entity_extraction/open_vocab_extractor.py` | 변경 안 함 | open-vocab은 Claude 기반이라 언어 무관, 이번 문제 대상 아님 |
| `src/matching/semantic_matcher.py` | 변경 안 함 | 상동 |
| `src/evaluation/flatten_matches.py` | 변경 안 함 | error_type 어휘 자체는 안 바뀜(`route_error`/`frequency_error`/`device_error`/`numeric_error`/`omission` 등 기존 항목 그대로 사용) |
| `src/evaluation/ccer_eval.py` | 변경 안 함 | 상동 |
| `docs/taxonomy_audit.md` | 변경 안 함 | v3 freeze 유지 |
| `docs/limitations.md`/`.ko.md` | 추가 예정(코드 수정 후) | v1부터 있던 이 버그를 별도 항목으로 기록 |

---

## 8. 영향 범위 — 어떤 SAP 분석이 재계산 필요한가

```
closed_vocab_extractor.py 수정
  -> run_closed_vocab_extraction.py --overwrite (*_closed.json 재생성)
  -> run_closed_vocab_matching.py --overwrite (closed_vocab_matches 재생성)
      -> CCER 변경 (ccer_eval.py)                          [재계산 필요]
      -> Entity-level P/R/F1 변경 (entity_eval.py)          [재계산 필요]
      -> Error Profile 변경 (SAP #4)                        [재계산 필요]
      -> Friedman/Wilcoxon/Mixed-effects (CCER 기반)        [재계산 필요]
      -> WER-CCER association, SAP #1 (CCER 쪽만 변경)      [재계산 필요]
      -> Within-scenario disagreement, SAP #2 (CCER 쪽만)   [재계산 필요]
      -> Weight sensitivity, SAP #3 (CCER 기반 전체)        [재계산 필요]
      -> Power analysis (효과 크기 변경 가능성)              [재계산 권장]
```

**영향 없음(재계산 불필요)**:
- `WER`/`wer_results.csv` — WER은 entity 추출과 무관하게 Gold/Whisper
  텍스트를 직접 jiwer로 비교하므로 완전히 영향 없음
- `open_vocab_matches`(medication_identity, intake_output, symptom,
  clinical_status, notification, intervention 관련 모든 결과) — Claude
  기반이라 이번 수정과 무관
- `data/scenarios`, `data/generated_text`, `data/audio`,
  `data/stt_transcripts` — 원본 데이터는 전혀 재생성 불필요
- v1/v2/v3 결과(`results/pilot_15/*`) — 그대로 보존

---

## 9. 확정된 결정 사항 (최종)

1. **route "정맥" 단독형 처리 — 실증 스캔 기반으로 확정.** §3.2에서 100개
   데이터 전수 스캔 결과 29%가 route가 아닌 다른 개념(device/symptom)
   이었음을 확인 — `으로`/`주사`/`내`/`수액` 접미사 필수, `관`/`류` 후행 시
   명시적 제외로 확정.
2. **medication_dose의 ownership — "특정 약물의 투여량"이라는 정의(§3.5)와
   그 문맥을 추정하는 4단계 deterministic hierarchy(§3.5 hierarchy)로
   확정.** route/frequency/투약 동사는 ownership의 정의 자체가 아니라
   medication-administration context를 확인하는 **proxy**임을 명시.
   vital_sign/intake_output/fluid volume처럼 더 구체적인 소유권을 가진
   값은 2단계에서 먼저 배제(거리 비교가 아니라 구조적 우선순위로 처리) —
   이는 100개 데이터 분포에 맞춘 튜닝이 아니라, 더 구체적인 카테고리가
   이미 그 값을 설명한다는 논리적 우선순위다. 절/구두점/거리는 3~4단계의
   보조 파싱 수단으로만 사용.
3. **Fluid volume(수액 투여량) — medication_dose에서 명시적으로 제외
   확정.** v3 taxonomy에서 이미 `intervention`이 수액 투여를 다루고
   있으므로(§3.5.1), `IV fluids 500mL`/`NS 500mL` 같은 범용 수액 표현은
   denylist로 medication_dose 후보에서 제외한다.
4. **Architecture A(현재 구조 + ownership hierarchy) 채택, B(structured
   medication tuple)는 v5 후보로 분리 확정(§6.2).**
5. **Phonetic surface-form 포함 기준 확정(§3.6).** "표준"이라는 표현 대신
   "해당 clinical domain에서 conventional abbreviation/term의 established
   spoken realization으로 볼 수 있는가"를 기준으로, `아이비`(IV)/`스탯`
   (STAT) 두 건만 이번 v4 lexicon에 포함. 관행적 근거가 없는 음차는 포함
   하지 않고 기존 `phonetic_artifact` 원칙(open-vocab 한정)에 맡긴다.

**이 문서는 이제 최종 확정본(freeze)이다.** 다음 단계는 코드 구현
(`closed_vocab_extractor.py`) → 유닛 테스트(§10) → 100개 데이터 재실행
(`run_closed_vocab_extraction.py --overwrite`, `run_closed_vocab_matching.py
--overwrite`, API 호출 없음) → v3 결과 보존한 채 v4로 별도 저장 → 100개
전체를 동일한 SAP(`docs/statistical_analysis_plan.md`)로 재평가.

---

## 10. 테스트 계획 (구현 후 실행할 것)

### 10.1 Style-invariance 핵심 테스트
동일 concept의 Formal(한국어 전체)/Clinical/Telegraphic(영어 약어) 표현이
전부 같은 canonical entity로 귀결되는지:
- `BP 120/80`, `혈압 120/80`, `blood pressure 120/80` → 전부 `{label: bp, value: "120/80"}`
- `IV`, `정맥으로`, `정맥주사`, `intravenous` → 전부 `iv`
- `q4h`, `매 4시간마다`, `4시간마다`, `every 4 hours` → 전부 `q4h`
- `NC`, `nasal cannula`, `비강 캐뉼라` → 전부 `nc`

### 10.2 Value mismatch 테스트
- Gold `BP 120/80` vs Whisper `혈압 120/60` → label은 `bp`로 동일 매칭,
  value가 다르므로 `numeric_error` (omission 아님)
- Gold `q4h` vs Whisper `매 6시간마다` → `frequency_error` (omission 아님)

### 10.2b Dose Ownership 테스트 (§3.5 4단계 hierarchy 대응)
- `Aspirin 325 mg PO STAT` → 2단계 통과(vital_sign/io/fluid 소유 아님) +
  3단계 route "PO" 존재 → dose 인정
- `Urine output 200 mL over 4 hours` → 2b단계에서 io 어휘로 제외 → dose
  인정 안 함
- `BP 90-60mg`(STT 오염) → 2a단계에서 vital_sign 라벨 소유로 제외 → dose
  인정 안 함 (3단계 도달 전 배제)
- `IV fluids 500mL 투여함` → 2b단계에서 fluid volume denylist로 제외
  (§3.5.1) → dose 인정 안 함
- `Morphine 4mg 투여함`(route/frequency 없이 투약 동사만 있는 경우) → 2단계
  통과 + 3단계 투약 동사 신호로 dose 인정(scaffold의 frequency가 null인
  시나리오 대응)
- 구두점이 전혀 없는 run-on Whisper 전사문에서 절 경계를 못 찾는 경우 →
  4단계 보조 파싱 fallback이 정상 동작하는지 확인
- route/frequency/투약동사가 전부 없는 극단적 사례(Architecture A의 알려진
  한계, §6.2) → 의도적으로 omission 처리됨을 확인(결함이 아니라 A의
  설계상 트레이드오프임을 테스트로 명시)

### 10.3 회귀 테스트
- 기존 `tests/test_closed_vocab_extractor.py`의 영어 전용 테스트 케이스가
  전부 그대로 통과하는지(영어 인식 능력 저하 없음)

### 10.4 False positive(교차 오염) 방지 테스트 — §5 대응
- `호흡곤란을 호소함`(symptom) 텍스트가 `RR`로 오매칭되지 않는지
- `정맥류가 관찰됨`(가상의 증상 서술) 텍스트가 `IV` route로 오매칭되지 않는지
- `4시간 동안 200mL 확인됨`(io 서술) 텍스트가 frequency로 오매칭되지 않는지

### 10.5 실데이터 전수 스캔 (§5.3)
- 100개 시나리오의 실제 Gold/Whisper 텍스트 전체에 새 정규식을 실행해,
  의도치 않은 entity_type에서 매칭이 발생하지 않는지 확인
- 기존에 omission으로 잡혔던 Formal Template의 vital_sign/route/frequency/
  device 레코드 중 몇 건이 이제 정상 매칭되는지 정량 확인
