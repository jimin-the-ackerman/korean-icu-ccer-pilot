# Reference Analysis

## 목적

본 문서는 Content Scaffold Schema(§3.3)와 Style Controller(§3.6) 설계에 앞서,
공개적으로 접근 가능한 Reference 자료를 분석하여 다음 세 가지를 확인한 결과를 정리한다.

1. ICU 간호기록에 포함되어야 하는 임상 정보 구조 (Information Structure)
2. Documentation Register 간 표현 방식의 차이 (Language Realization)
3. Rule-based Entity Extraction에 사용할 표준 약어 목록

## 방법론

- 실제 병원 EMR 데이터는 접근 불가하므로, 공개된 교육/임상 자료(웹검색)를 근거로 사용
- 원문을 그대로 복제하지 않고 패턴/구조만 추출하여 재구성
- Claude가 자료 수집·분석을 수행하였으며, 임상 전문가(간호사)의 직접 검증은 거치지 않음 -> Limitation으로 명시 (README Limitations 참고)

---

## 1. Standard Nursing Documentation Forms

### 확인된 사실

공개된 ICU/Critical Care Flow Sheet 양식들은 공통적으로 다음 구조를 가진다:
환자 식별정보, 활력징후(Vital Signs), 검사 데이터, 투약 정보(Medication),
신경학적 평가(Neuro Assessment), 통증 관리, 상처 관리, 섭취-배설량(I/O),
의료기기/라인(Device/Line) 섹션.

일부 양식은 활력징후, I/O, 인공호흡 설정, 라인/배액관, 영양 섭취를 시간 단위로 기록하며,
근무조(shift)별로 투약 및 I/O를 모니터링하는 구조를 갖는다.

### Content Scaffold 필드 후보

| 필드 카테고리 | 실제 양식 근거 | 논문 3.3 표 대응 여부 |
|---|---|---|
| Vital Signs (BP/HR/RR/BT/SpO2) | 모든 출처 공통 | 일치 |
| Medication (name/dose/route/frequency) | Flow Sheet 필수 섹션 | 일치 |
| I/O (Intake/Output) | Flow Sheet 표준 섹션 | 일치 |
| Device/Line (Foley, C-line 등) | ICU 특이적 섹션 | 일치 |
| Neurological/Consciousness Level | ICU Flow Sheet 특이적 | Clinical Status로 대응 |
| Notification/Physician Report | Flow Sheet에는 명시적이지 않음 | SBAR 자료에서 보강 확인 |

결론: 논문 3.3의 필드 설계는 실제 공개 표준 양식과 구조적으로 일치함.

### 출처

- pdfFiller Critical Care Flow Sheet (https://icu-flow-sheet.pdffiller.com/)
- DocHub ICU Flow Sheet (https://www.dochub.com/fillable-form/40568-icu-flow-sheet)
- ICU Flow Sheet Template, Scribd (https://www.scribd.com/document/725449089/ICU-sheet-simplified)
- Developing and validating a patient monitoring flow sheet in ICUs, PMC (https://pmc.ncbi.nlm.nih.gov/articles/PMC4145488/)
- Vital Signs Flow Sheet, pdfFiller/FormsPal

---

## 2. Clinical Charting and Handover Examples (SBAR)

### 확인된 사실

SBAR(Situation-Background-Assessment-Recommendation)는 4단계 구조를 가지며,
각 구간별로 문장 압축도가 다르게 나타난다.

- S/B 구간: 완전한 문장 구조, 배경 설명 위주
- A 구간: 수치와 소견이 나열되는 압축된 형태
- 긴급 상황 SBAR: 주어 생략, 수치와 핵심 소견만 전달하는 최소 압축 형태
- R 구간: 명확한 요청/제안형 문장

실제 교육 자료에서 "72세 남성, 폐렴, 2L 비강캐뉼라 산소 적용"이라는 시나리오가
전형적인 SBAR 예시로 반복적으로 사용되는 것을 확인함.

### Documentation Register 매핑

| SBAR 구간 | 압축 패턴 | Style Controller 대응 |
|---|---|---|
| Situation / Background | 완전한 문장, 서술형 | Formal Template Style |
| Assessment (평시) | 수치+소견 나열, 주어 일부 생략 | Clinical Charting Style |
| Assessment (긴급 상황) | 주어 생략, 수치만 압축 전달 | Telegraphic ICU Style |
| Recommendation | 명확한 요청 문장 | Notification 필드 표현 근거 |

### 출처

- Credenza Health, What Is SBAR (https://credenzahealth.com/career-advice/what-is-sbar-examples-nursing-explainer-and-faq)
- NurseBrain, Free SBAR Nursing Template (https://nursebrain.com/blog/free-sbar-nursing-template/)
- ASQ, SBAR (https://asq.org/quality-resources/sbar)
- Studocu, Nursing Report Handoff Cheat Sheet
- PMC, ICU point-of-care nursing handover checklist based on SBAR (https://pmc.ncbi.nlm.nih.gov/articles/PMC9722762/)

### 한계

이 구간별 압축 패턴 분석은 영어 SBAR 자료를 근거로 하며, 한국 ICU 간호기록의
실제 관행과 정확히 일치한다고 검증되지 않았다. 임상 전문가 검증 없이 AI가
패턴을 재구성한 것으로, 파일럿 연구의 한계로 명시한다.

---

## 3. Clinical Abbreviation Lists

### 카테고리별 확인된 약어

| 카테고리 | 약어 | 의미 |
|---|---|---|
| Route | PO | 경구 |
| Route | IV | 정맥 |
| Route | IM | 근육 |
| Route | SC / SubQ | 피하 |
| Route | SL | 설하 |
| Route | PR | 직장 |
| Frequency | BID | 하루 2회 |
| Frequency | TID | 하루 3회 |
| Frequency | QID | 하루 4회 |
| Frequency | PRN | 필요시 |
| Frequency | STAT | 즉시 |
| Frequency | q4h / q6h / q8h / q12h | 매 N시간마다 |
| Timing | AC | 식전 |
| Timing | PC | 식후 |
| Timing | NPO | 금식 |
| General | VS | 활력징후 |
| General | LOC | 의식수준 |
| General | I&O | 섭취-배설량 |
| General | NKDA | 알려진 약물 알레르기 없음 |
| Symptom Expression | c/o | 호소함 |

### 주의사항

일부 병원 안전 지침에서는 QD, U, cc, ug 등의 약어를 daily, unit, mL, mcg로
풀어쓸 것을 권고한다. 약어 오독으로 인한 투약 오류를 방지하기 위함이다.

### 출처

- St. Ritch School of Medicine, Clinical Abbreviations and Glossary
- George Brown College, Common Medical Abbreviations
- Blueprint Nursing, Nursing Abbreviations Ultimate Guide
- Drugs.com, Top 150 Prescription Abbreviations

---

## 종합 결론

| Reference 카테고리 | Schema 설계에 대한 기여 |
|---|---|
| Standard Forms | Content Scaffold의 필드 구조 확정 근거 |
| Charting/Handover Examples | Style Controller의 압축 규칙 근거 |
| Abbreviation Lists | Rule-based Entity Extraction용 Dictionary 원천 |

다음 단계: 이 분석 결과를 근거로 Content Scaffold Schema(JSON 구조)를 설계한다.

