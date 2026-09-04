# Hybrid Style Follow-up: Exploratory Design Specification

**상태: FREEZE.** 이 문서는 실제 API 실행(GPT-4o 렌더링) 전에 확정한
설계다. 결과를 본 뒤 이 문서(block mapping, hypotheses, 통계 계획)를
수정하지 않는다.

**성격 명시**: 이 실험은 confirmatory가 아니라 **exploratory
follow-up**이다. Hybrid의 block mapping 자체가 v4 최종 100-scenario
결과(특히 entity-type별 macro-CCER 패턴, `results/full_100_v4/sap5_*.csv`)를
관찰한 뒤 설계되었기 때문이다. 논문에서는 이를 "Main experiment → 문제
발견 → design implication → exploratory follow-up"이라는 흐름으로
명시적으로 서술한다.

---

## 1. 연구 질문

> Can an entity-informed hybrid register improve clinical information
> preservation beyond the best-performing original register (Formal
> Template)?

## 2. Block Mapping (확정)

| Block | 대상 | 표현 규칙 출처 |
|---|---|---|
| **Formal 표현** | vital signs, symptom, clinical status, intervention, notification, intake/output | `STYLE_DEFINITIONS["formal_template"]`의 규칙 문구를 그대로 재사용(신규 규칙 문구 없음) |
| **Clinical Charting 표현** | medication event(medication name + dose + route + frequency, 하나의 단위) + device + oxygen support | `STYLE_DEFINITIONS["clinical_charting"]`의 규칙 문구를 그대로 재사용 |

**정보 순서**: 원본 Content Scaffold가 암시하는 자연스러운 사실 순서
(예: patient context → vital signs → symptom → medication event →
intervention → device/oxygen support → clinical status → notification)를
그대로 유지한다. **사실을 표현 규칙에 따라 재배치하지 않는다** — Formal
표현 사실을 앞에, Clinical 표현 사실을 뒤에 모으는 식의 블록 재배치는
"표현 방식"이 아니라 "정보 순서"라는 별도의 confound를 만들기 때문에
명시적으로 금지한다. 오직 각 사실이 표현되는 **방식**만 바뀐다.

**Frequency를 medication event에 포함한 이유(명시)**: macro-CCER
분석(`results/full_100_v4/sap5_entity_type_ccer_table.csv`)에서 frequency
단독으로는 Formal Template이 더 낮은 오류율을 보였다(0.6869 vs 1.1919).
그럼에도 frequency를 Clinical Charting 표현에 포함시킨 것은 결과 때문이
아니라, 이미 존재하는(결과와 무관하게 v1부터 있던) `MEDICATION_EXPRESSION_RULE`
— "medication name, dose, route and frequency should appear as one
coherent medication event whenever present" — 이 네 요소를 하나의
문법적 단위로 취급하도록 이미 규정하고 있기 때문이다. Frequency만 따로
떼어 Formal 문장으로 표현하면 이 기존 규칙과 정면으로 충돌한다.

**Device/oxygen support를 Clinical 표현에 포함한 이유**: (1) macro-CCER
관찰상 Clinical Charting이 더 나았고, (2) 이와 별개로 ICU 현장에서
장치/산소 지원 상태는 짧고 구조화된 지지적 서술(short structured support
statement)로 표현되는 것이 문서화 관행상 자연스럽다 — 이 두 번째 근거는
결과와 무관하게 성립한다.

## 3. 사전 등록 가설 (Exploratory, 방향성 — 성공 기준 아님)

```
H1: Hybrid의 aggregate micro-CCER는 Formal Template보다 낮다.

H2 (exploratory, 방향성): Hybrid의 vital-sign error rate는 Formal
    Template 대비 실질적으로 증가하지 않는 방향을 보일 것으로 예상한다.

H3 (exploratory, 방향성): Hybrid의 device/dose/route error rate는
    Formal Template보다 낮아지고, Clinical Charting의 관찰값 방향으로
    이동할 것으로 예상한다.
```

**H2/H3 보고 원칙**: `p > .05`를 "동등하다"는 근거로 쓰지 않는다(비유의는
동등성의 증거가 아님). Equivalence/non-inferiority test는 이번 exploratory
스코프에 추가하지 않는다. 대신 entity_type별 오류율의 **실제 차이(effect
size, 관찰된 방향과 크기)**만 기술적으로 보고한다. 결과가 가설과 반대로
나와도(예: H2가 기각되어 vital_sign이 악화됨) 그대로 보고하며, 이는 실패가
아니라 "entity-specific advantages observed descriptively do not
necessarily compose into a superior mixed-register note"라는 동등하게
유효한 결과로 취급한다.

## 4. 통계 계획 — Descriptive vs Inferential 구분

- **Primary descriptive outcome**: aggregate micro-CCER (기존 3-스타일과
  동일한 공식, Hybrid 100개 전체 집계) — Formal/Clinical/Telegraphic 옆에
  나란히 보고
- **Primary inferential comparison**: **scenario-level(샘플 단위) CCER**,
  같은 100개 scaffold에서 나온 Hybrid vs Formal **쌍체 비교(Wilcoxon
  signed-rank, n=100)**. Aggregate micro-CCER 값 자체를 검정한 것으로
  오해되지 않도록, 보고 시 이 둘을 명확히 분리해 서술한다.
- **Secondary**: macro-CCER(robustness), Entity-level P/R/F1, normalized
  WER, entity_type별 오류율(H2/H3 검정용 — effect size로 보고)

## 5. Manipulation Check

**용어**: 이 검사 대상은 Content Scaffold(Gold entity의 근거)가 아니라
**GPT-4o가 생성한, TTS 이전의 렌더링 결과물**이다. Gold라는 용어와 혼동을
피하기 위해 이를 **"generated reference note"**로 지칭한다(Gold entity와
구분).

**시점**: 100개 generated reference note 생성 직후, TTS 이전에 실행한다.
검사 결과를 보고 prompt나 block mapping을 재조정하지 않는다 — 위반율
자체를 결과로 기록한다.

**결정론적 체크** (기존 `closed_vocab_extractor.py`를 그대로 재사용, 신규
API 호출 없음):
1. Route/Frequency/Device(Clinical 표현 대상)로 추출된 항목 중, 실제
   raw 텍스트가 영어 약어 형태인 비율(한글 미포함 여부로 판별)
2. Vital sign(Formal 표현 대상)로 추출된 항목 중, 실제 raw 텍스트가
   한국어 전체 표기 형태인 비율(한글 포함 여부로 판별)

**사람 검토(무작위 부분표본)**: 고정 시드로 10~15개를 무작위 추출하여
(a) 정보 순서가 원본 scaffold의 자연스러운 순서와 일치하는지, (b) 전체적
으로 자연스러운 노트로 읽히는지 정성적으로 확인한다.

---

## 6. 실행 순서

```bash
# 1. config.yaml: experiment.styles에 "hybrid" 추가
# 2. Generated reference note 생성 (기존 300개는 skip, 신규 100개만 생성)
python -m src.generation.generate_notes

# 3. Manipulation check (TTS 이전, 신규 API 호출 없음)
python -m src.analysis.hybrid_manipulation_check

# 4. (3의 결과를 보고 mapping을 수정하지 않고) TTS/STT
python -m src.tts.synthesize_speech
python -m src.stt.transcribe

# 5. Entity 추출/매칭 (기존 300개는 skip, 신규 100개만)
python -m src.entity_extraction.run_closed_vocab_extraction
python -m src.entity_extraction.run_open_vocab_extraction
python -m src.matching.run_closed_vocab_matching
python -m src.matching.run_semantic_matching

# 6. 비교 분석 (results/hybrid_followup/에 저장, results/full_100_v4/는 불변)
python -m src.analysis.hybrid_followup
```

기존 Formal/Clinical/Telegraphic 300개는 어떤 단계에서도 재생성되지
않는다(skip-by-default 안전장치).
