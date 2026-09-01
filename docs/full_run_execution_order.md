# 50-Scenario Full Run — Execution Order (Locked)

**작성 시점**: v3 taxonomy freeze 완료 직후, 15샘플(scenario_001~005) 결과
확정 이후. **이 문서에 명시된 순서와 안전장치를 지켜야만 기존 v1/v2/v3
결과가 안전하게 보존된다.**

**핵심 전제**: 이 실행에서 다루는 데이터 경로(`data/scenarios`,
`data/generated_text`, `data/audio`, `data/stt_transcripts`,
`data/entities`)는 pilot/full 단계 구분 없이 고정 경로를 공유한다. 즉
50개 확장은 "새로 15개를 만들고 따로 보관"이 아니라 **"기존 5개 위에
45개를 이어붙이는"** 방식이다. 1주차부터 만들어온 `src/pipeline_utils.py`의
skip-by-default 안전장치(§0)가 반드시 켜져 있어야 하며, 어떤 단계에서도
`--overwrite`를 실수로 붙이지 않는다.

---

## 0. 사전 점검 (실행 전 필수 확인)

```bash
# 1. 현재 브랜치가 최신이고 깨끗한지
git status
git log --oneline -3   # "Add idempotent skip-by-default..." 커밋이 보여야 함

# 2. 안전장치 테스트 전체 통과 확인
pytest tests/ -q       # 74개 전부 통과해야 함

# 3. 기존 scenario_001~005 데이터가 스킵되는지 dry-run 격으로 확인
#    (closed-vocab matching은 API 호출이 없으므로 이 자체가 안전한 실사용 확인)
python -m src.matching.run_closed_vocab_matching
#    -> "15 skipped / 0 processed" 로 나와야 함 (지금 상태 기준)
git status --short data/entities/   # matched.json 30개가 diff에 안 잡혀야 함(로그 파일만 새로 생김)
git checkout -- data/entities/*_matching_log.json 2>/dev/null || rm -f data/entities/*_matching_log.json
```

이 세 가지가 전부 확인된 뒤에만 1단계로 진행한다.

---

## 1. config.yaml 변경 (딱 두 줄)

```yaml
project:
  stage: "full"          # pilot -> full
experiment:
  n_scenarios: 50        # 5 -> 50
```

`paths` 섹션은 건드리지 않는다(고정 경로 유지 — 위 핵심 전제 참고).
`results_dir`만 마지막 CCER 계산 단계(§9)에서 별도로 지정한다(v1/v2/v3
폴더와 절대 겹치지 않게).

---

## 2. 실행 순서 (8단계, 전부 `--overwrite` 없이 기본값으로 실행)

| # | 명령어 | 산출물 | API | 예상 처리량 |
|---|---|---|---|---|
| 1 | `python -m src.scaffold.generate_scenarios` | `data/scenarios/scenario_006~050.json` | OpenAI(GPT-4o) | 45건 |
| 2 | `python -m src.generation.generate_notes` | `data/generated_text/scenario_006~050_{3스타일}.json` | OpenAI(GPT-4o) | 135건 |
| 3 | `python -m src.tts.synthesize_speech` | `data/audio/*.mp3` | OpenAI(TTS) | 135건 |
| 4 | `python -m src.stt.transcribe` | `data/stt_transcripts/*.json` | OpenAI(Whisper) | 135건 |
| 5 | `python -m src.entity_extraction.run_closed_vocab_extraction` | `data/entities/*_closed.json` | 없음(정규식) | 270건(Gold+Whisper) |
| 6 | `python -m src.entity_extraction.run_open_vocab_extraction` | `data/entities/*_open.json` | Claude | 270건(Gold+Whisper) |
| 7 | `python -m src.matching.run_closed_vocab_matching` | `data/entities/*_matched.json`(closed_vocab_matches) | 없음(규칙) | 135건 |
| 8 | `python -m src.matching.run_semantic_matching` | `data/entities/*_matched.json`(open_vocab_matches) | Claude | 135건 |

**각 단계는 반드시 순서대로**(이전 단계 산출물이 다음 단계 입력이므로) 실행한다.
1~4단계는 시나리오 자체와 스타일별 텍스트/음성/전사를 만드는 단계이고,
5~8단계는 지금까지 v1/v2/v3에서 계속 다뤄온 entity 추출·매칭 단계다.

**각 단계 실행 후 콘솔에 뜨는 요약을 반드시 확인**한다:
```
=== 실행 요약: processed=45, skipped=15, failed=0 ===
```
`skipped=15`(scenario_001~005 × 3스타일, 또는 시나리오 자체 단계는 5)가 항상
나와야 하고, `failed`가 0이 아니면 그 단계를 실패한 sample_id만 다시
실행하면 된다(스킵 로직 덕분에 재실행 자체가 "이어서 실행하기"가 됨).

---

## 3. 중단 시 재개 방법

어느 단계에서든 중단되면(API 오류, 네트워크 등), **똑같은 명령어를 다시
실행**하면 된다. 이미 끝난 sample_id는 자동으로 skip되고, 안 끝난 것만
이어서 처리된다. 별도의 재개 로직을 신경 쓸 필요 없음.

---

## 4. 완료 후 무결성 확인 (§0에서 만든 실행 로그 활용)

```bash
python3 -c "
import json, glob
for log_path in sorted(glob.glob('data/*/generation_log.json')) + \
                sorted(glob.glob('data/entities/*_log.json')):
    d = json.load(open(log_path, encoding='utf-8'))
    s = d['summary']
    print(f'{log_path:55s} processed={len(s[\"processed\"]):3d} skipped={len(s[\"skipped\"]):3d} failed={len(s[\"failed\"]):3d}')
    if s['failed']:
        print('   실패 목록:', s['failed'])
"
```

각 단계의 `processed + skipped`가 전체 샘플 수(시나리오 단계는 50, 스타일별
단계는 150)와 정확히 일치하는지, `failed`가 0인지 확인한다. 하나라도
빠지면 그 단계를 다시 실행(스킵 로직이 알아서 빠진 것만 처리).

---

## 5. scenario_001~005 무결성 최종 확인 (필수, 스킵하지 말 것)

```bash
git diff --stat data/scenarios/scenario_001.json data/scenarios/scenario_002.json \
                data/scenarios/scenario_003.json data/scenarios/scenario_004.json \
                data/scenarios/scenario_005.json
git diff --stat data/entities/scenario_00{1,2,3,4,5}_*_matched.json
```

**아무 출력도 없어야 정상**(=v3 freeze 시점과 완전히 동일). 뭔가 바뀐 게
보이면 즉시 중단하고 원인을 확인한다(안전장치를 우회한 `--overwrite`가
실수로 들어갔을 가능성 등).

---

## 6. WER / Entity-level P·R·F1 / CCER 계산 (50개 전체 기준)

```bash
python -m src.evaluation.wer_eval
python -m src.evaluation.entity_eval
python -m src.evaluation.ccer_eval
```

이 세 스크립트는 `config.yaml`의 `results_dir`을 그대로 쓰는데, **1단계에서
`results_dir`을 아직 안 바꿨다면 지금 바꾼다**:

```yaml
paths:
  results_dir: "results/full_50"   # v1/v2/v3(results/pilot_15/*) 와 절대 안 겹치게
```

---

## 7. v3 taxonomy 기준 Error Profile 분석 (50개 전체)

```bash
python -m src.analysis.error_profile --output-dir results/full_50
```

---

## 8. 통계 검정 · 가중치 민감도 분석 (2주차부터 예정돼 있던 것)

50개 규모에서 실제로 처음 진행하는 단계:
- Repeated-measures 검정 (Friedman test / mixed-effects model)
- 가중치 민감도 분석 (`ERROR_WEIGHTS`를 여러 조합으로 바꿔가며 핵심 결론 유지 확인)

(이 두 스크립트는 아직 미작성 — 50개 데이터가 나온 뒤 별도로 설계)

---

## 9. 사후 검정력 확인 (선택, 참고용)

```bash
python -m src.analysis.power_analysis --input results/full_50/ccer_results.csv
```

v3 15샘플 기준 필요 시나리오 수는 10개였고 50개는 이미 5배 여유가 있으므로,
이 단계는 "실제로 검정력이 충분했는지"를 사후 확인하는 참고 목적이며 표본
수 재조정을 위한 것이 아니다.

---

## 하지 않을 것 (원칙 재확인)

- taxonomy(§5, `docs/taxonomy_audit.md`)를 50개 결과에 맞춰 재수정하지 않는다
- `scenario_001~005` 및 그 하위 산출물을 어떤 이유로도 재생성하지 않는다
  (재생성이 꼭 필요하면 별도로 상의 후 명시적 `--overwrite`로, v1/v2/v3
  전체 재검증을 동반해서 진행)
- `results/pilot_15/`(v1/v2/v3) 폴더를 `results/full_50/` 작업 중 덮어쓰지 않는다
