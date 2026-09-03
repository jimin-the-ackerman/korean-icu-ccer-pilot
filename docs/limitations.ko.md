# Limitations

*[English version here](limitations.md)*

본 문서는 현재 파일럿 연구(5 scenario × 3 style = 15 sample)의 방법론적
한계를 정리한다. 이는 파일럿 규모와 리소스 제약 하에서 내려진 의도적
설계 판단의 결과이며, 후속 연구에서 보완이 필요한 지점을 명시하기 위함이다.

---

## 1. 파일럿 규모

5개 임상 시나리오, 15개 샘플로 진행되었다. 이는 파이프라인의 end-to-end
작동을 검증하기 위한 규모이며, 통계적으로 유의미한 결론을 도출하기에는
표본 크기가 작다. 본 연구에서 보고하는 수치(WER, F1, CCER)는 경향성
확인 수준으로 해석되어야 한다.

## 2. TTS/STT 도구 대체

제안서는 Google Cloud TTS와 로컬 Whisper 모델을 전제했으나, 파일럿에서는
OpenAI TTS와 OpenAI Whisper API로 대체하였다(상세 사유는
`docs/design_decisions.md` 참고). 도구 대체 자체가 연구 결론에 미치는
영향은 제한적으로 판단하나, 서로 다른 TTS/STT 엔진 간 성능 차이가
존재할 가능성은 배제할 수 없다.

## 3. 언어 설정 비교 실험 미실시

제안서는 Whisper의 Auto Detect와 한국어 고정 설정을 사전 비교하도록
설계하였으나, 파일럿에서는 한국어 고정(`language="ko"`)으로 바로 진행
하였다. 두 설정 간 차이에 대한 정량적 근거는 확보되지 않았다.

## 4. Claude 기반 Entity Extraction의 환각(Hallucination) 위험

Open-vocabulary Entity Extraction 과정에서, Claude가 음성 인식 오류로
깨진 텍스트를 임상적으로 그럴듯하게 보정하여 원문에 없는 Entity를
생성하는 사례가 실제로 관찰되었다(예: 활력징후 수치만으로 "저산소증"
증상을 추론하여 추가). 프롬프트에 verbatim 추출 원칙과 반례를 명시하여
완화하였으나, 이는 근본적 해결이 아니라 완화 조치이며, 유사한 패턴이
관측되지 않은 다른 샘플에서도 발생하지 않았다고 보장할 수 없다.

## 5. Semantic Matching의 음성적 유사성 오판

> **상태: v2에서 완화됨** (`docs/design_decisions.md` §4 참고). 아래
> 원문은 파일럿에서 최초 관찰된 형태로 그대로 보존한다.

Open-vocabulary Entity Matching의 Semantic Match 단계는 Claude가
Gold Entity와 Whisper Entity 간 임상적 의미 동일성을 판단하도록
설계되었다. 그러나 검증 과정에서, Whisper가 STT 오류로 발음만 유사하게
재현한 문자열(예: "chest pain" → "체스파인")을 Claude가 의미가 보존된
것으로 오판하는 사례가 관찰되었다. 해당 표기는 임상적으로 의미를 갖지
않는 음차 오류임에도 semantic match로 분류되어, 실질적인 정보 손실이
"보존됨"으로 과대평가될 위험이 있다. 본 파일럿에서는 이 문제를 별도의
Error Type 신설이나 평가 로직 변경 없이 방법론적 한계로 기술한다.

v2에서는 `semantic`과 구분되는 별도의 `phonetic_artifact` 매칭 카테고리를
도입하고, 명시적인 판정 규칙과 반례를 프롬프트에 추가했으며, 평가 시에는
`omission`과 동일하게 처리한다. 이는 프롬프트 레벨의 완화 조치이며
구조적 해결은 아니다(Claude의 판단과 독립적인 음성적 유사도 탐지기를
추가한 것은 아님). 따라서 경계 사례(부분적으로만 인식 가능한 외래어 등)
에서는 여전히 오판이 발생할 수 있다. 이번 계획의 2주차에서 기존 15샘플을
v2로 재실행하여, 이 재분류가 실제로 몇 건에 영향을 미치는지 정량화할
예정이다.

## 6. CCER의 whisper_only(환각성 삽입) 미반영

> **상태: v2에서 해결됨** (`docs/design_decisions.md` §5 참고). 아래
> 원문은 파일럿에서 최초 관찰된 형태로 그대로 보존한다.

Whisper Transcript에만 존재하고 Gold Entity에 대응하는 항목이 없는
경우(`whisper_only`)는 현재 CCER 계산에서 가중치 0으로 처리되어
집계에서 제외된다. 즉 Whisper가 실제로 존재하지 않는 정보를 삽입하는
경우(환각)에 대한 페널티가 현재 공식에 반영되어 있지 않다.

v2에서는 이 항목들에 `error_type="hallucination"`을 부여하고, CCER
공식에서 numeric_error/negation_flip/severity_shift와 동일한 등급인
weight=3을 적용한다. 가중치 선정 근거는 `src/evaluation/ccer_eval.py`
참고.

## 7. Substitution 판정 로직의 단순성

Closed-vocabulary Entity Matching에서, 동일 Entity Type 내에
Omission 1건과 Whisper 전용 항목 1건이 동시에 존재하는 경우 이를
Substitution(치환)으로 재해석하는 휴리스틱을 사용한다. 이는 파일럿
규모(문장당 Entity 개수가 적음)에서는 유효하나, 50개 이상으로 확장 시
한 문장에 동일 Type의 Entity가 여러 개 존재하는 경우 오판 가능성이
있으며, 더 정교한 정렬(alignment) 알고리즘이 필요할 수 있다.

## 8. 임상 전문가 검증 부재

Reference Analysis(공개 자료 기반 근거 조사)와 CCER 가중치 설계
(NCC MERP 철학을 개념적으로 참고하여 연구자가 직접 설계) 모두 실무
간호사 또는 임상 전문가의 직접 검증을 거치지 않았다. 생성된 Content
Scaffold와 Documentation Register 표현이 실제 한국 ICU 임상 환경의
관행과 정확히 일치하는지는 검증되지 않았다.

## 9. 실제 병원 데이터 미사용

본 연구는 개인정보 보호와 데이터 접근성 문제로 실제 병원 EMR 데이터를
사용하지 않고, 전 과정을 합성 데이터(GPT-4o 생성)로 진행하였다. 합성
데이터 기반 결과가 실제 임상 환경에 그대로 일반화된다고 주장하지 않는다.

---

## 10. Closed-vocab 정규식의 카테고리 간 오염 (Dose vs. Vital Sign / Intake-Output)

**[v4에서 해결됨]** 이 한계는 v4 style-invariant extraction 작업의 일부로
수정되었다. 전체 entity ownership hierarchy 수정 내용은
`docs/v4_style_invariant_extraction_spec.md` §3.5, 설계 근거는
`docs/design_decisions.ko.md` §7 참고. 아래 서술은 원래 문제의 기록으로
그대로 보존한다.

v3 파이프라인 sanity audit(`docs/taxonomy_audit.md`) 과정에서 발견됨. v3
이전(v1/v2)에도 동일 건수로 존재했던 사전 문제로, v3 taxonomy 변경이
새로 만든 문제가 아니다. `closed_vocab_extractor.py`의 `dose` 정규식은
문맥과 무관하게 "숫자+단위" 패턴(예: `\d+\s*(mg|mL|cc|g|mcg|L/min)`)이면
전부 매칭한다. 이로 인해 두 가지 오탐이 파일럿에서 관찰됐다: ① 혈압
수치가 STT로 뭉개지면서 "숫자+mg" 패턴이 된 경우(예: "90/60 mmHg"가
"90-60mg"로 전사됨)가 약물 용량으로 오분류됨. ② 섭취/배설량 수치(예:
"urine output 200 mL")도 마찬가지로 약물 용량으로 오분류됨. 둘 다 투약과
무관한 값이 dose 카테고리의 hallucination 건수를 부풀린다.

## 11. 하나의 노트 안에서 같은 장치가 두 번 언급되는 경우

역시 v3 sanity audit에서 발견됨, 역시 사전 문제(v1/v2와 건수 동일). LLM이
생성한 노트 텍스트가 같은 실제 장치 사실을 한 노트 안에서 서로 다른
표현으로 두 번 언급하는 경우가 있다(예: "SpO2 95% on 2L NC."에 이어
나중에 "NC 사용 중."). Gold의 closed-vocab device 목록은 Content
Scaffold에서 나오므로(물리적 사실 1개 = entity 1개, 생성된 텍스트가 몇 번
반복 서술하든 무관), 반면 정규식 기반 추출기는 텍스트에 실제로 등장하는
횟수를 그대로 센다. 그 결과 한 노트에서 같은 장치가 두 번 언급되면
Whisper 쪽엔 device entity가 2개, Gold 쪽엔 1개만 생겨 나머지 1개가
hallucination으로 잘못 집계된다. 실제로는 아무 정보도 지어내지 않았는데도
그렇다. 수정하려면 매칭 전에 동일 텍스트 내 중복 값을 제거하거나, 노트
생성 단계에서 각 장치 사실을 한 번만 서술하도록 제약해야 한다. Future
Work로 남기며, 파일럿에서 15개 중 1개 샘플에만 영향을 준 소수 사례다.

## 12. Symptom 카테고리 경계 누수 (patient_context, clinical_status)

역시 v3 sanity audit에서 발견됨. 서로 관련된 두 가지 하위 문제이며, 둘 다
사전에 존재하던 현상이다(v2에서는 동일 현상이 6건이었는데 v3 프롬프트
개선 이후 3건으로 줄었음 — v3의 SYSTEM_PROMPT 수정이 부분적으로는
완화했지만 완전히 해소하지는 못했다는 뜻):
- Content Scaffold의 `patient_context` 필드(`docs/taxonomy_audit.md`
  §5.5에 따라 CCER 범위에서 명시적으로 제외됨)가 노트 생성 단계에서
  증상처럼 읽히는 문장으로 서술되는 경우가 있다(예: patient_context
  "...presenting with respiratory distress..."가 노트 문장 "...respiratory
  distress 호소함..."이 됨). 이 내용은 Gold symptom entity에 전혀 반영되지
  않으므로(Gold의 symptom entity는 Scaffold의 별도 단일 `symptom` 필드에서만
  나옴), Whisper가 이걸 정확히 전사해도 환각성 symptom으로 오분류된다.
- clinical_status류 서술(예: "약간의 기면 상태를 보이고 있다")이 Whisper
  쪽 추출에서 `clinical_status`뿐 아니라 `symptom`("lethargy")으로도 중복
  추출되는 경우가 있다. device/oxygen_support vs intervention에서 이미
  고친 것과 같은 종류의 카테고리 중복 패턴이지만(`docs/taxonomy_audit.md`
  §3.3), 그 수정 범위에 포함되지 않았던 카테고리 쌍에서 발생한다.

둘 다 이번 v3 taxonomy 범위를 사후적으로 넓히지 않고("결과에 맞춰 taxonomy를
계속 확장하지 않는다"는 원칙, `docs/taxonomy_audit.md` §6.4), 다음 taxonomy
개정(잠재적 "v4") 대상 Future Work로 남긴다.

**50개 확장 최종 sanity audit에서 관찰된 변종 사례**: 같은 patient_context
누수 메커니즘이 symptom이 아니라 intervention 쪽에서도 나타남을 확인했다
(`scenario_029`: patient_context "...requiring close respiratory
monitoring..."이 노트에 "호흡 상태 밀착 모니터링 필요."로 서술되고,
Whisper는 이를 정확히 전사하지만 대응하는 Gold intervention entity가
없어 hallucination으로 오분류됨). 이는 한계 12가 symptom 카테고리에만
국한된 문제가 아니라, patient_context 누수가 우연히 어떤 entity type과
비슷하게 읽히느냐에 따라 그 카테고리의 가짜 hallucination으로 나타날 수
있다는 걸 보여준다.

---

## 13. `intervention` 카테고리로의 잔여 의미 경계 누수

50개 확장 본실험의 최종 pipeline sanity audit(`data/entities/`,
`results/full_50/`)에서 발견됨. 50샘플 결과에서 관찰된 14건의
`intervention` 카테고리 hallucination 중 13건이 동일한 근본 패턴으로
귀결된다: `intervention` open-vocab 카테고리의 Whisper 측 추출
(`open_vocab_extractor.py`)이, v3에서 intervention 범위를 축소할 때
명시적으로 제외되지 않은 인접 카테고리의 행위적/활동적 표현을 흡수하고
있다(`docs/taxonomy_audit.md` §5.2, #8; §8.2에서는 투약·device/
oxygen_support·intake/output **값**을 제외했음 — 아래 두 하위 격차 참고).
14건 중 13건 모두 Whisper가 없는 정보를 지어낸 게 아니라, 실제 Gold
정보가 카테고리 경계 문제로 중복 집계된 경우다.

**하위 사례 A — `notification`(전문의 컨설트 요청) vs `intervention`**
(14건 중 5건): 전문의 컨설트 요청을 서술하는 텍스트(예: Gold notification
"Consult gastroenterology for ongoing management of pancreatitis." /
"orthopedic consultation requested")가 `intervention`으로도 독립적으로
재추출됨(예: "Gastroenterology Consult 요청함", "ORTHOPEDIC CONSULT").
v3의 intervention 제외 목록은 투약·device/oxygen-support·intake/output은
명시적으로 다루지만 **notification은 포함하지 않았음** — 이 카테고리 쌍은
당시 수정 범위에서 단순히 빠졌던 것이다.

**하위 사례 B — `intake_output`의 "모니터링 행위" 표현 vs `intervention`**
(14건 중 6건): v3 제외 규칙과 예시는 io의 **값**(예: "urine output 200
mL")은 다루지만, io를 **모니터링하는 행위** 자체를 서술하는 표현(예: Gold
io "strict monitoring of intake and output", "strict fluid balance
monitoring")은 여전히 `intervention`으로 독립 재추출됨(예: "스트릭트
모니터링 of intake and output", "strict fluid balance monitoring"). 제외
규칙의 문구가 값 중심으로 작성되어, 같은 사실을 행위 중심으로 서술한
경우를 예상하지 못했다.

**하위 사례 C — Scaffold `io` 필드 자체가 intervention성 문구로 채워짐**
(14건 중 2건): 일부 시나리오(예: `scenario_027`)에서는 Content Scaffold의
`io` 필드 자체가 scaffold 생성 단계에서 체액균형 관측치가 아니라
intervention처럼 읽히는 문구("IV fluids initiated")로 채워짐. 이
문구에 대한 Whisper의 intervention 추출은 표현 자체만 보면 부자연스럽지
않음 — 모호함의 근원이 Gold/Whisper taxonomy 정합성이 아니라 더 상류인
scaffold 생성 단계의 문구 선택에 있다.

결과에 맞춰 taxonomy를 사후적으로 재조정하지 않는다는 원칙
(`docs/taxonomy_audit.md` §6.4)에 따라, 이는 v3에 편입하지 않고 잔여
한계로 기록한다. 향후 수정(잠재적 "v4")에서는 intervention 제외 목록을
notification/컨설트 표현과 intake-output **모니터링 행위** 표현(값뿐
아니라)까지 명시적으로 확장하고, `io` 필드 내용이 행위가 아닌 관측치로만
채워지도록 scaffold 생성 단계에 제약이나 사후 검증 단계를 추가하는 방향이
될 것이다.

---

## 14. v4(Style-Invariant Extraction)에서 의도적으로 남겨둔 잔여 공백

v4 style-invariant extraction audit(`docs/v4_style_invariant_extraction_spec.md`)
및 실제 데이터 검증 과정에서 발견·기록됨. 놓친 게 아니라 의도적으로 정한
범위 경계다 — 각각 실제 100개 시나리오 데이터로 검증한 결과, 일반화
가능한 문법으로 해결 불가능하거나(진짜 정보 손실), v4가 원래 고치려던
스타일 편향과 무관한 잔여 STT 노이즈 효과였다.

- **"정맥"(route) 단독형**: 접미사가 붙은 형태(정맥으로/정맥주사/정맥
  내/정맥 수액)만 `iv` route로 인정한다 — 실증 스캔 결과 단독 "정맥" 언급의
  29%가 다른 개념(device 또는 symptom)이었다는 발견에 근거함. 100개
  시나리오 데이터에서 단독형 사례 자체가 관찰되지 않아, 이는 "확인된
  누락"이 아니라 "아직 검증 안 됨" 상태다 — 향후 데이터에서 실제 단독형
  route 용례가 나오면 재검토.
- **SpO2 label-value 문법의 잔여 사례**: v4 문법 수정 후에도 원래 55건의
  SpO2 삽입구 omission 중 6건은 여전히 안 잡힘 — 전부 값 자체가 STT로
  심하게 뭉개진 경우(예: "SpO2 간지 5%", "산소포화도는 상실기 공기에서
  95%로")로, 일반화 가능한 구조적 패턴이 아니라 진짜 정보 손실임을
  확인했다. 추가로 1건("...이 O2를 비강케귤라로 공급받으면서...")은
  조사와 산소 맥락 수식어 사이에 추가 어절이 끼어있어 닫힌 문법이
  커버하지 못함 — 단 1건뿐인 관찰 사례를 위해 특수 처리하지 않고 그대로
  둠.
- **Formal Template의 잔여 device/dose/route 오류율**: v4 수정 후에도
  Formal Template의 `device`(77%), `dose`(86%), `route`(73%) 오류율은
  이제 최선이 된 `vital_sign` 오류율(4.6%)보다 여전히 훨씬 높다. 이는
  잔여 추출 편향이 아니라, 짧은 영어 약어와 달리 여러 음절로 이루어진
  한국어 임상 표현이 겪는 일반적인 STT 전사 노이즈로 추정된다 —
  Architecture A(`docs/v4_style_invariant_extraction_spec.md` §6.2)는
  라벨 인식 편향 제거만을 목표로 명시적으로 범위를 좁혔지, 스타일 간
  균일한 STT 강건성을 보장하려던 게 아니었다. 이 귀인을(잔존하는 미발견
  추출 공백이 아니라 진짜 STT 노이즈라는 것을) 확실히 확인하는 것은
  Future Work로 남긴다.

---

## Future Work

- [v2에서 완료, 프롬프트 레벨] 표준 의료 용어 온톨로지(SNOMED CT, UMLS)
  또는 한국어 의료 개체명 인식(NER) 모델을 활용한 Entity Normalization은
  `phonetic_artifact` 프롬프트 수정보다 더 구조적인 대안으로 여전히 열려
  있음 (한계 5 대응)
- [v2에서 완료] CCER 공식에 whisper_only(환각성 삽입) 페널티 반영 (한계 6 대응)
- 50개 이상 규모 확장 시 Entity Matching 정렬 알고리즘 고도화 (한계 7 대응)
- 임상 전문가(간호사) 대상 Content Scaffold 및 CCER 가중치 검증 (한계 8 대응)
- 실제 병원 데이터 확보 시 합성 데이터 기반 결과와의 비교 검증 (한계 9 대응)
- Whisper Auto Detect vs 한국어 고정 설정 비교 실험 (한계 3 대응)
- [v4에서 완료] Dose 정규식에 문맥 인식 로직(entity ownership hierarchy)
  추가하여 활력징후/섭취배설량 수치 오분류 방지 (한계 10 대응)
- 매칭 전 동일 텍스트 내 중복 closed-vocab 값 제거 로직 추가 (한계 11 대응)
- device/oxygen_support-intervention에 적용한 카테고리 경계 제외 규칙을
  symptom-clinical_status 쌍까지 확장, patient_context 서술이 필요로 하는
  좁은 예외 조항 재검토 (한계 12 대응)
- intervention 제외 목록을 notification/컨설트 요청 표현, intake-output
  **모니터링 행위** 표현(값뿐 아니라)까지 명시적으로 확장; `io` 필드
  내용이 행위가 아닌 관측치로만 채워지도록 scaffold 생성 단계에 제약이나
  사후 검증 단계 추가 (한계 13 대응)