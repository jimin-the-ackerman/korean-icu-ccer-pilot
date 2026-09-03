# Statistical Analysis Plan (SAP) — 논문 초안 전 최종 확정본

**Freeze 시점**: 100-scenario full run (300 samples) 데이터 기준.
**전제**: Friedman/Wilcoxon/Mixed-effects 결과(`src/analysis/statistical_tests.py`,
`results/full_100/`)는 이미 완료되어 보존되며 재실행하지 않는다. 아래 4개
분석이 논문 초안 전 마지막 confirmatory/exploratory analysis set이다.
**원칙**: 이 문서 확정 이후에는 결과를 보고 분석 방법이나 weighting scheme을
추가/삭제하지 않는다. 100개 시나리오를 최종 데이터셋으로 freeze한다.

**[사후 기록 - v4 재실행 관련]** 이 SAP를 확정한 이후, closed-vocab
entity 추출기의 style-dependent bias(`docs/v4_style_invariant_extraction_spec.md`)
가 발견되어 별도의 methodological correction(v4)을 거쳤다. 아래 4개
분석의 **방법론 자체는 전혀 수정하지 않았고**, v4로 재계산된 최종
`results/full_100_v4/` 데이터에 대해 동일한 절차를 그대로 재실행했다.
이는 결과를 보고 분석 방법을 바꾼 것이 아니라, 입력 데이터(evaluator의
구조적 편향 제거)가 바뀐 것이므로 이 문서의 freeze 원칙에 위배되지 않는다.

---

## 1. WER–CCER Association (Spearman)

**연구 질문**: 300개 샘플(100 시나리오 × 3 스타일) 전체에서 WER과 CCER이
sample level에서 얼마나 함께 움직이는가? 이 관계가 style 간 평균 차이에서
비롯된 것인지, style 내부에서도 성립하는 관계인지?

**계산할 통계량**:
- Pooled Spearman ρ (normalized WER ↔ CCER, n=300)
- Style별 Spearman ρ 3개 (각 n=100)
- 전부 95% CI를 **scenario-level cluster bootstrap**으로 계산 (p-value 중심
  해석이 아니라 ρ와 CI 중심으로 해석)

**Bootstrap 방법**:
- Pooled: 100개 scenario_id를 복원추출(resampling with replacement)하고,
  뽑힌 각 scenario의 **3개 스타일 행을 전부 함께** bootstrap sample에
  포함시켜 repeated-measures 구조(같은 scenario 내 3개 관측치 간 상관)를
  보존한다. 이렇게 만든 bootstrap sample(n=300, 단 중복 포함)에서 Spearman
  ρ를 계산한다.
- Style별: 각 style은 이미 scenario당 1개 관측치이므로, 100개 scenario_id를
  복원추출하고 해당 style의 값만 뽑아 ρ를 계산한다(pooled와 동일한
  scenario-단위 resampling 원칙을 일관되게 적용).
- **Replicates**: 5,000회
- **CI**: Percentile method (2.5th ~ 97.5th percentile)

**해석 범위**:
- 할 수 있는 것: WER-CCER 관계의 방향·강도, style 평균 차이의 부산물인지
  여부(pooled ρ가 style별 ρ보다 훨씬 강하면 between-style 효과가 크다는 뜻)
- 할 수 없는 것: 어느 metric이 "맞다"는 판단, 인과관계, 순위 차이의 통계적
  유의성(이는 이미 완료된 Friedman/Wilcoxon의 몫)

---

## 2. Within-Scenario Metric Disagreement

**연구 질문**: 같은 시나리오 안에서 WER과 CCER이 3개 스타일에 대해 서로
다른 순위/최선 스타일을 고르는 정도는? "Formal Template = WER 최선, CCER
최악"이 시나리오 단위에서도 일관되게 나타나는가?

**Tie 정의**: WER(normalized), CCER 값 모두 **저장된 정밀도(4자리 반올림)
기준으로 완전히 동일**한 경우를 tie로 정의한다. (CCER은 이미
`ccer_eval.py`에서 4자리로 반올림되어 저장됨; WER도 동일 정밀도로 맞춰
비교)

**Primary 결과** (반드시 보고):
1. **Complete ranking agreement**: 시나리오별 WER 기준 3-스타일 순위와
   CCER 기준 순위가 (tie 구조를 포함해) 완전히 일치하는 시나리오 비율.
   두 metric 중 하나라도 해당 시나리오에서 tie가 있으면, 다른 metric도
   동일한 tie 구조를 가질 때만 "일치"로 인정한다.
2. **Best-style agreement**: WER 기준 최선 스타일과 CCER 기준 최선 스타일이
   일치하는 시나리오 비율. 어느 한쪽이라도 최선이 tie이면 별도 카테고리
   ("최선 tie")로 보고한다.
3. **Pairwise concordance/discordance/tie** (3개 style pair 각각:
   Formal-Clinical, Formal-Telegraphic, Clinical-Telegraphic): 해당
   시나리오에서 두 스타일 중 어느 쪽이 더 나은지(낮은 값)를 WER과 CCER이
   각각 판단했을 때,
   - **Concordant**: 두 metric이 같은 스타일을 "더 낫다"고 판단
   - **Discordant**: 두 metric이 반대 스타일을 "더 낫다"고 판단
   - **Tie**: WER 또는 CCER 중 하나 이상이 그 pair에서 tie
   세 범주의 비율을 pair별로 전부 보고한다.

**Secondary/descriptive 결과**:
- 시나리오별 **Kendall's tau-b**(WER 순위 vs CCER 순위)의 분포(평균, 분포).
  **채택 이유**: 시나리오 하나에 스타일이 3개뿐이라 가능한 순위 조합이
  제한적이므로 tau-b를 1차 검정 통계량으로 쓰기엔 정보량이 작다. 대신
  "두 순위가 pairwise 비교 단위에서 얼마나 동의하는가"를 압축해서 보여주는
  요약 지표로만 부차적으로 보고한다(τ=+1 완전 일치 ~ τ=-1 완전 역전).
  Kendall's W(앞서 Friedman에서 쓴 것)와는 목적이 다르다 — W는 "여러 반복
  측정이 서로 얼마나 일관된 순서를 갖는가"(다자간 합치도)를 재고, tau-b는
  "두 개의 특정 순위(WER-순위, CCER-순위)가 서로 얼마나 같은가"(두 순위
  간 합치도)를 잰다.

**해석 범위**:
- 할 수 있는 것: 역전 현상이 몇 %의 시나리오에서 나타나는지, 어느 style
  pair에서 특히 심한지, Formal의 WER-CCER 불일치가 시나리오 단위 패턴인지
- 할 수 없는 것: 어느 metric이 옳은지, 100개 시나리오/3스타일 조합 밖으로의
  일반화

---

## 3. CCER Weight Sensitivity Analysis

**연구 질문**: 현재 결론(스타일 순위, Formal Template의 WER-CCER 불일치)이
`ERROR_WEIGHTS`의 구체적 숫자(3/2/1) 선택에 의존하는가, 다른 합리적
가중치 체계에서도 유지되는가?

**사전 고정 weighting schemes** (5개, 결과 확인 전 확정):

| Scheme | 설명 | tier3 | tier2 | tier1 |
|---|---|---|---|---|
| **Primary(현행)** | 기준선 | 3 | 2 | 1 |
| **A. Equal** | 가중치 구분 제거 | 1 | 1 | 1 |
| **B. Wide** | tier 간 격차 확대 | 5 | 2 | 1 |
| **C. Narrow** | tier 간 격차 축소 | 1.5 | 1.2 | 1 |
| **D. Hallucination-downweighted** | `hallucination`(v2에서 신설된 항목)만 tier3→tier2로 하향; `medication_identity_error`는 hallucination과 다른 오류 유형이므로 tier3 그대로 유지 | 나머지 tier3 항목 그대로 3 / hallucination=2 | 2 | 1 |

tier 소속은 현재 `ERROR_WEIGHTS`의 실제 분류를 따른다:
tier3={numeric_error, negation_flip, severity_shift, hallucination,
medication_identity_error}, tier2={omission, substitution, route_error,
frequency_error, unit_error, device_error}, tier1={formatting_error}.
(scheme D는 tier3 중 hallucination만 개별적으로 2로 낮춤, 나머지 tier3
항목은 그대로 유지)

**NCC MERP 관련**: 5개 scheme 전부 연구자가 설계한 것이며, primary·대안
모두 NCC MERP가 숫자를 직접 제공한 게 아니라 "심각도를 단계로 나눈다"는
철학만 참고한 것이라는 입장을 결과 서술에서 일관되게 유지한다
(`docs/taxonomy_audit.md` §7.3과 동일).

**각 scheme마다 계산할 것**: style별 mean CCER, style 순위, Formal의
WER-CCER 불일치 유지 여부, Kendall's W, Friedman p-value.

**Primary robustness criterion** (결과 해석의 기준, 결과 확인 전 고정):
> Formal Template이 WER 기준 최선임에도, 사전 정의된 5개 weighting
> scheme 전반에서 CCER 기준 최선이 되지 않는가?

**Secondary robustness criterion**:
- Exact style ranking이 5개 scheme에서 유지되는가
- Mean CCER 차이의 방향(부호)이 유지되는가
- Kendall's W가 scheme 간 어떻게 달라지는가
- Friedman p-value가 scheme 간 어떻게 달라지는가

**명시적 목적 제한**: 이 sensitivity analysis의 목적은 p-value를 유의하게
만드는 것이 **아니다**. weight 선택에 대한 결론의 방향성 강건성(directional
robustness)만 확인하는 것이 목적이며, 이 분석 결과로 primary weighting을
사후 변경하지 않는다.

---

## 4. 100-Scenario 최종 Error Profile

**연구 질문**: Formal Template의 omission 지배적 패턴이 구체적으로 어떤
entity_type에서 나오는가? Clinical/Telegraphic의 numeric_error 등 다른
구성과 entity_type 단위로 비교하면 어떤가?

**계산할 것**:
- Style × Error Type × Entity Type 3중 교차표 (건수) — 기존
  `error_profile.py`의 `entity_type_x_error_type_by_style()` 재사용
- **추가**: entity_type별 **error rate** = 해당 (style, entity_type)의
  오류 건수 / 해당 (style, entity_type)의 **Gold entity 총 개수**. 건수만
  비교하면 entity_type별 빈도 차이(예: vital_sign은 원래 개수가 많고
  medication_identity는 적음) 때문에 잘못된 해석을 할 위험이 있어, 분모를
  맞춘 비율로 같이 제시한다.

**해석 범위**:
- 할 수 있는 것: 어떤 entity_type이 어떤 error_type과 강하게 결부되는지
  서술적 특징화(Signature 축 뒷받침)
- 할 수 없는 것: 인과관계 주장, 이 교차표 자체의 통계적 유의성(검정하지
  않음, 순수 기술통계)

---

## 실행 순서

문서 확정 후 1 → 2 → 3 → 4 순서로 실행하고, 결과를 그대로 보고한다.
실행 후 이 문서(분석 방법·weighting scheme)를 결과에 맞춰 수정하지 않는다.
