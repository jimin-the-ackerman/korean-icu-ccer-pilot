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