# Korean ICU Nursing Documentation Style Transfer Pipeline

*[English version here](README.md)*

본 프로젝트는 ICU 간호기록을 다양한 Documentation Register로 생성하고,
음성 합성(TTS) 및 음성 인식(STT)을 거쳐 임상 정보 보존 여부를 평가하기
위한 연구이다.

> ※ 본 프로젝트는 박사후/연구원 지원을 위한 개인 연구 프로젝트입니다.
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

본 연구는 다음을 전체 규모(100개 임상 시나리오 × 3개 Documentation Register
= 300개 샘플)로 구현하고 검증한다:

1. 동일한 임상 정보(Content Scaffold)를 3가지 Documentation Register로
   생성하는 Style-controlled Generation Pipeline
2. 생성된 간호기록을 음성으로 변환(TTS)하고 다시 텍스트로 전사(STT)하는 과정
3. 전사 결과에서 임상 정보 보존 여부를 Word Error Rate(WER), Entity-level
   Precision/Recall/F1, Clinical Critical Error Rate(CCER)로 평가하는 프레임워크
4. 사전 등록된 통계 분석 계획(Friedman/Wilcoxon/mixed-effects, WER-CCER
   상관, within-scenario disagreement, CCER 가중치 민감도 분석)

평가 방법론은 결과와 무관하게 독립적으로 감사·수정된 4번의 문서화된 개정
(`docs/design_decisions.md`, `docs/taxonomy_audit.md`,
`docs/v4_style_invariant_extraction_spec.md`)을 거쳤다. 그중 가장 중요한
발견은 **closed-vocabulary 추출기가 영어 약어만 인식**하도록 설계돼있어,
임상 라벨을 한국어 완전 표기로 자주 렌더링하는 Formal Template이 실제
전사 정확도와 무관하게 구조적으로 불리하게 평가받고 있었다는 점이다.
아래 보고된 모든 결과는 이 편향을 제거한 최종 파이프라인(v4) 기준이다.

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
    -> Statistical Analysis (Friedman/Wilcoxon/Mixed-effects, WER-CCER
       association, within-scenario disagreement, weight sensitivity)
```

### 2.1 Content Scaffold Generation
공개된 표준 간호기록 서식, SBAR 예시, 임상 약어 목록을 분석하여
(`docs/reference_analysis.md`) Content Scaffold의 JSON Schema를 설계하였다
(`src/scaffold/scaffold_schema.py`). GPT-4o가 이 Schema를 따르는 임상
시나리오를 구조화된 JSON으로 생성한다(`src/scaffold/generate_scenarios.py`).
평가의 Gold Standard는 렌더링된 텍스트가 아니라 Content Scaffold 자체를
사용하여, Documentation Register 간 비교가 추출 단계의 차이로 왜곡되지
않도록 한다(`src/entity_extraction/scaffold_as_gold.py`;
`docs/design_decisions.md` §3 참고).

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
전사된 텍스트에서 임상 정보를 두 갈래로 추출하며, 결과와 무관하게 독립
확정된 11개 entity type을 다룬다(`docs/taxonomy_audit.md` §5):

- **Closed-vocabulary Entity** (Route, Frequency, Device, Dose, Vital Sign):
  Reference Analysis에서 확인된 표준 약어 목록을 Dictionary/정규식으로
  규칙 기반 추출한다(`src/entity_extraction/closed_vocab_extractor.py`).
  v4부터 이 추출기는 **style-invariant**하다 — 영어 약어만이 아니라,
  영어 전체 표기·한국어 전체 표기·소수의 관행적 음차 표현까지 `surface
  form → canonical concept/value → 비교` 구조로 인식한다. `medication_dose`
  추출에는 entity ownership hierarchy(후보 탐지 → vital_sign/intake_output
  등 더 구체적인 소유권을 가진 값 배제 → medication-administration 문맥
  확인)를 추가로 적용해, 무관한 숫자를 약물 용량으로 잘못 귀속시키는 것을
  방지한다. 전체 스펙과 감사 과정은
  `docs/v4_style_invariant_extraction_spec.md` 참고.
- **Open-vocabulary Entity** (Symptom, Clinical Status, Medication Identity,
  Intervention, Intake/Output, Notification): 표현이 자유로워 규칙으로
  포착할 수 없으므로, Claude의 Structured Output으로 추출한다
  (`src/entity_extraction/open_vocab_extractor.py`).

### 2.5 Entity Matching & Error Classification
Whisper 전사문에서 추출된 Entity를 Gold Standard(Content Scaffold)와
대조하여 각 임상 정보의 보존 여부를 판정한다.

- Closed-vocabulary: 정규화된 값을 규칙 기반으로 비교한다
  (`src/matching/entity_matcher.py`).
- Open-vocabulary: Claude가 Gold와 Whisper entity 목록을 함께 검토하여
  의미 기반 매칭을 수행하며, medication identity에는 ISMP Confused Drug
  Names 목록에 근거한 더 엄격한 look-alike/sound-alike 안전장치를 적용한다
  (`src/matching/semantic_matcher.py`).

매칭 결과는 Matched / Omission / Numeric Error / Route Error / Frequency
Error / Medication Identity Error / Negation Flip / Severity Shift /
Hallucination 등으로 분류된다.

### 2.6 Evaluation
파이프라인 결과를 세 가지 지표로 평가한다:

- **WER** (`src/evaluation/wer_eval.py`): Gold Transcript와 Whisper
  Transcript 간 전사 정확도. Raw/Normalized(대소문자·구두점 무관) 값을
  모두 보고한다.
- **Entity-level Precision/Recall/F1** (`src/evaluation/entity_eval.py`):
  Content Scaffold 대비 Whisper 결과물의 임상 정보 보존율.
- **Clinical Critical Error Rate (CCER)** (`src/evaluation/ccer_eval.py`):
  각 오류 유형을 잠재적 임상 위험도에 따라 가중치를 부여해 정규화한 점수.
  가중치 체계는 NCC MERP의 환자안전 철학(그리고 medication identity에
  한해 ISMP Confused Drug Names 목록)을 개념적으로 참고해 연구자가 3단계
  (상/중/하)로 설계했으며, 이 가중치 선택 자체를 사전 등록한 5개 대안
  체계로 stress-test했다(아래 §3.5 참고).

### 2.7 Statistical Analysis
사전 등록된 분석 계획(`docs/statistical_analysis_plan.md`, 실행 전
확정)은 다음을 포함한다: Kendall's W를 동반한 Friedman test, Holm 보정
Wilcoxon pairwise 비교, mixed-effects model
(`src/analysis/statistical_tests.py`); scenario-level cluster-bootstrap
WER-CCER Spearman 상관(`src/analysis/sap1_wer_ccer_spearman.py`);
within-scenario 순위 불일치(`src/analysis/sap2_within_scenario_disagreement.py`);
5개 사전 지정 scheme에 대한 CCER 가중치 민감도 분석
(`src/analysis/sap3_weight_sensitivity.py`); entity_type별 오류율
(`src/analysis/sap4_error_profile_final.py`).

---

## 3. 결과 (최종, v4, n=100 시나리오 / 300 샘플)

전체 결과: [`results/full_100_v4/`](results/full_100_v4/).

### 3.1 Word Error Rate (normalized)

| Documentation Register | Mean WER |
|---|---|
| Formal Template | 0.3038 |
| Clinical Charting | 0.4517 |
| Telegraphic ICU | 0.5640 |

### 3.2 Entity-level Evaluation

| Documentation Register | Precision | Recall | F1 |
|---|---|---|---|
| Formal Template | 0.8432 | 0.6728 | 0.7484 |
| Clinical Charting | 0.7665 | 0.5406 | 0.6341 |
| Telegraphic ICU | 0.7995 | 0.4933 | 0.6101 |

### 3.3 Clinical Critical Error Rate

| Documentation Register | CCER (낮을수록 좋음) |
|---|---|
| Formal Template | 0.8417 |
| Clinical Charting | 1.1682 |
| Telegraphic ICU | 1.2134 |

### 3.4 통계적 유의성

Friedman test: χ² = 78.12, Kendall's W = 0.391, p = 1.09 × 10⁻¹⁷.
Holm 보정 Wilcoxon signed-rank: Formal Template은 나머지 두 스타일과
각각 유의하게 다름(p_holm ≈ 1.3 × 10⁻¹¹, 3.3 × 10⁻¹²); Clinical Charting과
Telegraphic ICU는 서로 유의하게 다르지 않음(p_holm = 0.217). Mixed-effects
model(`CCER ~ style + (1|scenario)`)도 두 스타일 계수 모두 p < 0.0001로
유의함을 확인했다. Formal Template이 CCER 최선이라는 결론은 사전 등록한
5개 CCER 가중치 scheme 전부에서 유지되었다(`docs/statistical_analysis_plan.md`
§3).

### 3.5 핵심 발견

WER, Entity-level F1, **그리고** CCER **전부**에서 이제 Formal Template이
**최선**, Telegraphic ICU가 최악으로 나타난다. 이는 이 파이프라인의 이전
(방법론적으로 혼입이 있었던) 버전(v3)의 정반대 결론 — Formal Template이
WER 기준 최선이지만 CCER 기준 *최악*이라는, "완전한 문장형 서술이 원시
전사 정확도는 높이지만 Whisper가 임상 정보를 더 많이 놓치게 만든다"는
결론 — 을 뒤집는 극적인 결과다.

이 이전의 "역전" 발견은 **evaluator 전체 감사를 통과하지 못했다.** 실제
임상 정보 손실과 무관하게 Formal Template의 오류 건수를 부풀린 두 가지
독립적인 구조적 편향이 발견됐다:

1. **스타일 의존적 추출 편향**: closed-vocabulary 추출기가 영어 약어
   (`BP`, `HR`, `IV`, `q4h` 등)만 인식했다. Formal Template은 같은 임상
   사실을 한국어 완전 표기(`혈압`, `심박수`, `정맥으로`, `매 4시간마다`)로
   자주 렌더링하는데, Whisper가 이를 정확히 전사했는지와 무관하게
   추출기가 아예 인식을 못 했다. 이 하나만으로도 Formal Template의
   활력징후 인식률이 수정 후 0%→100%로 바뀌었다.
2. **Gold/Whisper 값 형식 비대칭**: (1)을 고친 후에도, Content Scaffold의
   Gold 값은 원본 단위를 그대로 유지(예: `"120 bpm"`)하는 반면 Whisper
   쪽 추출기는 항상 순수 숫자(`"120"`)만 포착했다. 이 때문에 Whisper가
   숫자를 완벽하게 전사했어도 가짜 "numeric error"가 발생했다 — 파이프라인
   최초 버전부터 있던 버그였는데, (1)을 고쳐 Formal Template의 라벨이
   처음으로 대량 매칭되기 전까지는 드러나지 않았다.

둘 다 원하는 결과에 맞춰 땜질한 게 아니라 실제 데이터 검증(회복률, 비파괴
확인, false-positive 스캔)을 거쳐 감사·수정했다. 전체 스펙과 근거,
감사 과정은 `docs/v4_style_invariant_extraction_spec.md`에 있다. 편향을
제거한 올바른 결론은, 이 파일럿에서 WER·Entity-level F1·CCER이 대체로
일관된다는 것이다 — 더 문법적이고 완전하게 풀어쓴 기록은 Whisper가
정확하게 전사하기도 쉽고, 임상 정보 보존에도 더 낫다. 영어 전용
evaluator가 내렸을 결론과는 정반대다.

따라서 이 프로젝트의 방법론적 기여는 세 스타일의 구체적인 순위 자체보다,
**임상적으로 설계된 평가 지표(CCER)를 만드는 것만으로는 evaluator 편향에서
자유롭다는 보장이 되지 않으며, 그 지표를 뒷받침하는 entity extraction
계층도 지표 자체와 동일한 엄밀함으로 감사돼야 한다**는 것을 보여주는
데 있다.

---

## 4. Repository Structure

```
korean-icu-ccer-pilot/
├── configs/
│   └── config.yaml              # 실험 설정 (n_scenarios, results_dir 등)
├── docs/
│   ├── reference_analysis.md    # Reference 자료 분석
│   ├── design_decisions.md      # 구현 중 설계 변경 기록
│   ├── limitations.md           # 연구의 한계
│   ├── taxonomy_audit.md        # v3: 독립적 CCER taxonomy 감사 및 확정
│   ├── v4_style_invariant_extraction_spec.md  # v4: 스타일 편향 감사·스펙·확정
│   ├── statistical_analysis_plan.md           # 사전 등록 SAP (확정본)
│   └── full_run_execution_order.md            # 확장 실행 순서 고정 문서
├── data/
│   ├── scenarios/                # Content Scaffold (GPT-4o 생성)
│   ├── generated_text/           # 스타일별 Gold Transcript
│   ├── audio/                    # TTS 음성 파일 (git 추적 안 함)
│   ├── stt_transcripts/          # Whisper 전사 결과
│   └── entities/                 # Entity 추출/매칭 결과
├── src/
│   ├── pipeline_utils.py          # Skip-by-default 안전장치 (RunLog, --overwrite)
│   ├── scaffold/                  # Content Scaffold schema 및 생성
│   ├── style_controller/          # Documentation Register 규칙
│   ├── generation/                # GPT-4o 문서 생성
│   ├── tts/                       # 음성 합성
│   ├── stt/                       # 음성 인식
│   ├── entity_extraction/         # Closed/open-vocabulary 추출
│   ├── matching/                  # Entity 매칭, semantic matching
│   ├── evaluation/                # WER, entity evaluation, CCER
│   └── analysis/                  # Error profile, power analysis, 통계 검정, SAP 1-4
├── results/
│   ├── pilot_15/                  # v1/v2/v3 체크포인트(15샘플 파일럿, 보존)
│   ├── full_50/                   # 50-scenario 체크포인트(보존)
│   ├── full_100/                  # v3(v4 수정 전) 100-scenario 체크포인트(보존)
│   └── full_100_v4/               # 최종 결과 (100 시나리오, 편향 보정)
└── tests/                          # 유닛 테스트
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

모든 생성/추출/매칭 스크립트는 기본적으로 idempotent하다 — 이미 결과가
있는 샘플은 자동으로 건너뛰고, 없는 것만 처리한다(`src/pipeline_utils.py`).
강제로 다시 만들려면 `--overwrite`를 붙이면 된다. 덕분에 규모 확장(5→50→100
시나리오)을 이미 계산된 결과를 훼손할 위험 없이 안전하게 진행할 수 있다 —
이 프로젝트가 실제로 확장할 때 쓴 전체 체크리스트는
`docs/full_run_execution_order.md` 참고.

```bash
# 1. Content Scaffold 생성 (GPT-4o)
python3 -m src.scaffold.generate_scenarios

# 2. 스타일별 문서 생성 (GPT-4o)
python3 -m src.generation.generate_notes

# 3. 음성 합성 (OpenAI TTS)
python3 -m src.tts.synthesize_speech

# 4. 음성 인식 (OpenAI Whisper)
python3 -m src.stt.transcribe

# 5. Entity 추출 (closed-vocab은 정규식이라 API 불필요, open-vocab은 Claude 호출)
python3 -m src.entity_extraction.run_closed_vocab_extraction
python3 -m src.entity_extraction.run_open_vocab_extraction

# 6. Entity 매칭 (closed-vocab은 규칙 기반, API 불필요; open-vocab은 Claude)
python3 -m src.matching.run_closed_vocab_matching
python3 -m src.matching.run_semantic_matching

# 7. 평가 (WER, Entity-level P/R/F1, CCER, Error Profile) - API 불필요
python3 -m src.evaluation.wer_eval
python3 -m src.evaluation.entity_eval
python3 -m src.evaluation.ccer_eval
python3 -m src.analysis.error_profile --output-dir results/full_100_v4

# 8. 통계 분석 (docs/statistical_analysis_plan.md 기준) - API 불필요
python3 -m src.analysis.statistical_tests --results-dir results/full_100_v4
python3 -m src.analysis.sap1_wer_ccer_spearman --results-dir results/full_100_v4
python3 -m src.analysis.sap2_within_scenario_disagreement --results-dir results/full_100_v4
python3 -m src.analysis.sap3_weight_sensitivity --output-dir results/full_100_v4
python3 -m src.analysis.sap4_error_profile_final --output-dir results/full_100_v4
```

### 5.3 규모 확장

`configs/config.yaml`의 `experiment.n_scenarios`를 바꾸고(결과를 별도
폴더에 보존하고 싶으면 `paths.results_dir`도 함께), 위와 동일한 순서로
재실행하면 된다. 모든 단계가 기본적으로 이미 있는 결과를 건너뛰므로,
기존에 계산된 시나리오(예: 처음 100개)는 전혀 손대지 않고 새로 추가된
것만 처리된다 — 별도 코드 수정이 필요 없다. 이 프로젝트가 실제로
5→50→100 시나리오로 확장할 때 쓴 정확한 체크리스트(사전 점검, 무결성
확인, 하지 않을 것 목록 포함)는 `docs/full_run_execution_order.md` 참고.

### 5.4 테스트

```bash
pytest tests/ -q
```

---

## 6. 관련 문서

- [`docs/reference_analysis.md`](docs/reference_analysis.md): Content
  Scaffold Schema 및 Style Controller 규칙의 근거가 된 Reference 자료 분석
- [`docs/design_decisions.md`](docs/design_decisions.md): 원안 대비 구현
  중 변경된 설계 결정 기록
- [`docs/limitations.md`](docs/limitations.md): 연구의 한계, 의도적으로
  남겨둔 잔여(스타일 편향과 무관한) 파싱 공백 포함
- [`docs/taxonomy_audit.md`](docs/taxonomy_audit.md): v3 — 11개 CCER
  entity taxonomy에 대한 독립적·결과-무관 감사 및 확정
- [`docs/v4_style_invariant_extraction_spec.md`](docs/v4_style_invariant_extraction_spec.md):
  v4 — 위 §3.5에서 설명한 style-invariant closed-vocabulary 추출 수정의
  감사·스펙·확정 문서
- [`docs/statistical_analysis_plan.md`](docs/statistical_analysis_plan.md):
  사전 등록된 통계 분석 계획(실행 전 확정)
- [`docs/full_run_execution_order.md`](docs/full_run_execution_order.md):
  5→100 시나리오 확장 시 이미 계산된 결과를 훼손하지 않도록 고정한 실행
  체크리스트

---

## 7. Author

Jimin (jimin-the-ackerman)
