# Korean ICU Nursing Documentation Style Transfer Pipeline

본 프로젝트는 ICU 간호기록을 다양한 Documentation Register로 생성하고,
음성 합성(TTS) 및 음성 인식(STT)을 거쳐
임상 정보 보존 여부를 평가하기 위한 파일럿 연구이다.

> ※ 본 프로젝트는 석사 후 연구원 지원을 위한 개인 연구 프로젝트(Pilot Study)입니다.
> 실제 병원 EMR을 사용하지 않고 공개 Reference를 기반으로 Content Scaffold를 설계하였으며,
> 생성형 AI를 활용하여 ICU 간호기록 생성–음성 합성–음성 인식–Entity Evaluation–CCER까지의
> 전체 파이프라인을 구현하였습니다.

---

## 1. 연구 개요

한국 ICU 간호기록은 일반적인 한국어 문장과 다른 고유한 기록 체계
(Documentation Register)를 가진다. 동일한 임상 정보라도 완전한 문장형
서술(Formal Template), 한영 혼용 압축 기록(Clinical Charting), 극도로
압축된 실시간 기록(Telegraphic ICU) 등 서로 다른 방식으로 표현될 수 있으며,
이 표현 방식의 차이는 음성 인식(STT) 성능과 임상 정보 보존율에 서로 다른
영향을 미칠 수 있다.

본 연구는 다음을 파일럿 규모(5개 임상 시나리오 × 3개 Documentation Register
= 15개 샘플)로 구현하고 검증한다:

1. 동일한 임상 정보(Content Scaffold)를 3가지 Documentation Register로
   생성하는 Style-controlled Generation Pipeline
2. 생성된 간호기록을 음성으로 변환(TTS)하고 다시 텍스트로 전사(STT)하는 과정
3. 전사 결과에서 임상 정보 보존 여부를 Word Error Rate(WER), Entity-level
   Precision/Recall/F1, Clinical Critical Error Rate(CCER)로 평가하는 프레임워크

파일럿의 목적은 대규모 성능 비교가 아니라, 위 파이프라인 전체가
end-to-end로 정상 작동함을 검증하는 것이다. 검증된 코드는 파라미터
조정만으로 50개 시나리오(150개 샘플) 규모로 확장 가능하도록 설계되었다.

---

## 2. 전체 파이프라인

```
Reference Analysis
    -> Content Scaffold Schema
    -> GPT-4o: Structured Clinical Scenario Generation
    -> Style Controller
    -> GPT-4o: Style-controlled Documentation Generation
    -> OpenAI TTS: Speech Synthesis
    -> OpenAI Whisper: Speech Recognition
    -> Entity Extraction (Closed-vocabulary / Open-vocabulary)
    -> Entity Matching & Error Type Classification
    -> Evaluation (WER / Entity-level P,R,F1 / CCER)
```

### 2.1 Content Scaffold Generation
공개된 표준 간호기록 서식, SBAR 예시, 임상 약어 목록을 분석하여
(`docs/reference_analysis.md`) Content Scaffold의 JSON Schema를 설계하였다
(`src/scaffold/scaffold_schema.py`). GPT-4o가 이 Schema를 따르는 임상
시나리오를 구조화된 JSON으로 생성한다(`src/scaffold/generate_scenarios.py`).

### 2.2 Style-controlled Documentation Generation
동일한 Content Scaffold를 Formal Template / Clinical Charting /
Telegraphic ICU 세 가지 스타일로 표현하도록 GPT-4o에 지시한다. 각 스타일의
규칙(문장 압축도, 한영 코드스위칭, 차팅형 서술어 등)은 Reference Analysis에
근거하여 설계되었다(`src/style_controller/style_controller.py`,
`src/generation/generate_notes.py`).

### 2.3 Speech Synthesis & Recognition
생성된 간호기록 텍스트를 OpenAI TTS로 음성화하고(`src/tts/synthesize_speech.py`),
OpenAI Whisper API로 다시 텍스트로 전사한다(`src/stt/transcribe.py`).
화자(voice)는 모든 샘플에 대해 단일하게 고정하여 통제변수로 유지한다.

### 2.4 Entity Extraction
전사된 텍스트에서 임상 정보를 두 갈래로 추출한다:

- **Closed-vocabulary Entity** (Route, Frequency, Device, Dose, Vital Sign):
  Reference Analysis에서 확인된 표준 약어 목록을 Dictionary/정규식으로
  규칙 기반 추출한다(`src/entity_extraction/closed_vocab_extractor.py`).
- **Open-vocabulary Entity** (Symptom, Clinical Status, Intervention,
  Notification): 표현이 자유로워 규칙으로 포착할 수 없으므로, Claude의
  Structured Output 기능으로 추출한다(`src/entity_extraction/open_vocab_extractor.py`).

### 2.5 Entity Matching & Error Classification
Gold Standard(Content Scaffold)와 Whisper 전사 결과에서 추출된 Entity를
비교하여 보존 여부를 판정한다.

- Closed-vocabulary: 정규화된 값의 일치 여부를 규칙 기반으로 비교한다
  (`src/matching/entity_matcher.py`).
- Open-vocabulary: Claude가 Gold/Whisper Entity 목록을 함께 검토하여
  의미 기반(semantic) 매칭을 수행한다(`src/matching/semantic_matcher.py`).

매칭 결과는 Matched / Omission / Numeric Error / Route Error /
Frequency Error / Negation Flip / Severity Shift 등으로 분류된다.

### 2.6 Evaluation
세 가지 지표로 파이프라인 결과를 평가한다:

- **WER** (`src/evaluation/wer_eval.py`): Gold Transcript와 Whisper
  Transcript 간 전사 정확도. 대소문자/구두점 정규화 전후 값을 모두 산출한다.
- **Entity-level Precision/Recall/F1** (`src/evaluation/entity_eval.py`):
  Content Scaffold 대비 Whisper 결과의 임상 정보 보존율.
- **Clinical Critical Error Rate(CCER)** (`src/evaluation/ccer_eval.py`):
  Error Type별 임상적 위험도 가중치를 반영한 정규화 점수. 가중치는
  NCC MERP의 환자안전 중심 철학을 개념적으로 참고하여 연구자가 직접
  설계하였다(3단계: 매우 높음/중간/낮음).

---

## 3. 결과 요약 (Pilot, n=15)

### 3.1 Word Error Rate (정규화 기준)

| Documentation Register | Mean WER |
|---|---|
| Formal Template | 0.3439 |
| Clinical Charting | 0.4299 |
| Telegraphic ICU | 0.4735 |

### 3.2 Entity-level Evaluation

| Documentation Register | Precision | Recall | F1 |
|---|---|---|---|
| Formal Template | 0.5946 | 0.3385 | 0.4314 |
| Clinical Charting | 0.5893 | 0.5077 | 0.5455 |
| Telegraphic ICU | 0.6481 | 0.5385 | 0.5882 |

### 3.3 Clinical Critical Error Rate

| Documentation Register | CCER (낮을수록 우수) |
|---|---|
| Telegraphic ICU | 1.0154 |
| Clinical Charting | 1.1385 |
| Formal Template | 1.3538 |

### 3.4 핵심 발견

WER 기준으로는 Formal Template이 가장 우수하고 Telegraphic ICU가 가장
저조하지만, Entity-level F1과 CCER 기준으로는 **정반대로 Telegraphic ICU가
가장 우수하고 Formal Template이 가장 저조**하다.

이는 Formal Template의 완전한 문장형 서술이 Whisper의 전사 정확도(WER) 자체는
높이지만, 정보가 서술형 문장 속에 녹아 있어 핵심 임상 정보가 통째로
누락되는 경향(Omission)이 크다는 것을 시사한다. 반대로 Telegraphic ICU는
문장 구조가 깨지는 비율(WER)은 높지만, 정보가 압축·명시적으로 나열되어
있어 핵심 수치/개체 자체는 상대적으로 더 잘 보존된다.

이 결과는 전사 정확도(WER)만으로 의료 음성인식 시스템을 평가할 경우
임상적으로 왜곡된 결론에 도달할 수 있다는 것을 파일럿 규모에서 실증적으로
보여준다.

---

## 4. 프로젝트 구조

```
korean-icu-ccer-pilot/
├── configs/
│   └── config.yaml              # 실험 설정 (시나리오 수, 스타일, 모델 등)
├── docs/
│   ├── reference_analysis.md    # Reference 자료 분석 결과
│   ├── design_decisions.md      # 설계 변경 이력
│   └── limitations.md           # 연구 한계
├── data/
│   ├── scenarios/                # Content Scaffold (GPT-4o 생성)
│   ├── generated_text/           # Style-controlled Gold Transcript
│   ├── audio/                    # TTS 음성 파일
│   ├── stt_transcripts/          # Whisper 전사 결과
│   └── entities/                 # Entity 추출/매칭 결과
├── src/
│   ├── scaffold/                 # Content Scaffold Schema, 생성 로직
│   ├── style_controller/         # Documentation Register 규칙 정의
│   ├── generation/                # GPT-4o 문서 생성
│   ├── tts/                       # 음성 합성
│   ├── stt/                       # 음성 인식
│   ├── entity_extraction/         # Closed/Open-vocabulary 추출
│   ├── matching/                  # Entity Matching, Semantic Matching
│   └── evaluation/                # WER, Entity Eval, CCER
├── results/
│   └── pilot_15/                  # 최종 평가 결과 (CSV/JSON)
└── tests/                          # 단위 테스트
```

---

## 5. 재현 방법

### 5.1 환경 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # OPENAI_API_KEY, ANTHROPIC_API_KEY 입력
```

### 5.2 전체 파이프라인 실행 순서

```bash
# 1. Content Scaffold 생성 (GPT-4o)
python3 -m src.scaffold.generate_scenarios

# 2. Style-controlled Documentation 생성 (GPT-4o)
python3 -m src.generation.generate_notes

# 3. 음성 합성 (OpenAI TTS)
python3 -m src.tts.synthesize_speech

# 4. 음성 인식 (OpenAI Whisper)
python3 -m src.stt.transcribe

# 5. WER 평가
python3 -m src.evaluation.wer_eval

# 6. Entity 추출
python3 -m src.entity_extraction.run_closed_vocab_extraction
python3 -m src.entity_extraction.run_open_vocab_extraction

# 7. Entity Matching
python3 -m src.matching.run_closed_vocab_matching
python3 -m src.matching.run_semantic_matching

# 8. 최종 평가 (Entity-level P/R/F1, CCER)
python3 -m src.evaluation.entity_eval
python3 -m src.evaluation.ccer_eval
```

### 5.3 규모 확장 (5 → 50 시나리오)

`configs/config.yaml`의 `experiment.n_scenarios` 값을 변경하고,
`src/scaffold/generate_scenarios.py`의 `SCENARIOS` 목록을 필요한 만큼
확장한 뒤 위 순서를 동일하게 재실행하면 된다. 나머지 코드는 시나리오
개수와 무관하게 동작하도록 설계되었다.

---

## 6. 관련 문서

- [`docs/reference_analysis.md`](docs/reference_analysis.md): Content
  Scaffold Schema와 Style Controller 규칙의 근거가 된 Reference 자료 분석
- [`docs/design_decisions.md`](docs/design_decisions.md): 제안서 대비
  구현 과정에서 변경된 설계와 그 사유
- [`docs/limitations.md`](docs/limitations.md): 현재 파일럿 연구의 한계




