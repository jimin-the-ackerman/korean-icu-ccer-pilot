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