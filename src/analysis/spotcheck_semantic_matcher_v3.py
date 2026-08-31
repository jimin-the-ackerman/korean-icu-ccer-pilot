"""
v3 semantic_matcher.py 로컬 spot-check (실제 Claude API 호출 필요)

목적: medication_identity_match의 핵심 안전장치 -- "철자/발음이 비슷해도
실제로 다른 약물이면 반드시 value_substitution으로 가야 한다" -- 가 실제
Claude 판정에서 지켜지는지, 15샘플 전체 재실행 전에 합성 케이스로 먼저 확인.

확인 항목 (전부 medication_identity_match 대상):
1. Gold "Ceftriaxone" vs Whisper "Cephtriaxone" (2단계 spot-check에서 실제로
   나온 STT 철자 오류) -> "semantic"이어야 함 (같은 약물)
2. Gold "Hydralazine" vs Whisper "Hydroxyzine" (ISMP 공식 LASA 쌍) ->
   "value_substitution"이어야 함 (다른 약물)
3. Gold "Morphine" vs Whisper "Morphine" -> "exact"
4. Gold "Ceftriaxone" vs Whisper 없음(null) -> "omission"
5. Gold 없음(null) vs Whisper "Insulin" -> "whisper_only"
6. 대조군: clinical_status에서도 value_substitution이 정상 작동하는지
   (Gold "alert" vs Whisper "drowsy")

이 스크립트는 scaffold/whisper 원본 텍스트가 아니라, entity 리스트를 직접
구성한 합성 케이스를 쓴다 -- medication_identity_match 판정 로직 자체를
좁게 타겟하기 위함이며, 실제 15샘플 재실행 시에는 전체 파이프라인(추출->매칭)
이 자연스럽게 이 케이스들을 포함하게 된다.

사용법 (로컬, .env에 ANTHROPIC_API_KEY 필요):
    python -m src.analysis.spotcheck_semantic_matcher_v3
"""

import json
import os

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from src.matching.semantic_matcher import match_open_vocab

load_dotenv()

CASES = [
    {
        "label": "medication_identity: STT 철자 오류 (같은 약물) -> semantic 기대",
        "gold": {"symptoms": [], "clinical_status": None, "medication_identity": "Ceftriaxone",
                  "interventions": [], "intake_output": None, "notification": None},
        "whisper": {"symptoms": [], "clinical_status": None, "medication_identity": "Cephtriaxone",
                    "interventions": [], "intake_output": None, "notification": None},
        "check_field": "medication_identity_match",
        "expected_basis": {"semantic", "exact", "normalized"},
    },
    {
        "label": "medication_identity: ISMP 공식 LASA 쌍 (다른 약물) -> value_substitution 기대",
        "gold": {"symptoms": [], "clinical_status": None, "medication_identity": "Hydralazine",
                  "interventions": [], "intake_output": None, "notification": None},
        "whisper": {"symptoms": [], "clinical_status": None, "medication_identity": "Hydroxyzine",
                    "interventions": [], "intake_output": None, "notification": None},
        "check_field": "medication_identity_match",
        "expected_basis": {"value_substitution"},
    },
    {
        "label": "medication_identity: 완전 동일 -> exact 기대",
        "gold": {"symptoms": [], "clinical_status": None, "medication_identity": "Morphine",
                  "interventions": [], "intake_output": None, "notification": None},
        "whisper": {"symptoms": [], "clinical_status": None, "medication_identity": "Morphine",
                    "interventions": [], "intake_output": None, "notification": None},
        "check_field": "medication_identity_match",
        "expected_basis": {"exact"},
    },
    {
        "label": "medication_identity: Whisper 누락 -> omission 기대",
        "gold": {"symptoms": [], "clinical_status": None, "medication_identity": "Ceftriaxone",
                  "interventions": [], "intake_output": None, "notification": None},
        "whisper": {"symptoms": [], "clinical_status": None, "medication_identity": None,
                    "interventions": [], "intake_output": None, "notification": None},
        "check_field": "medication_identity_match",
        "expected_basis": {"omission"},
    },
    {
        "label": "medication_identity: Gold에 없는데 Whisper가 삽입 -> whisper_only 기대",
        "gold": {"symptoms": [], "clinical_status": None, "medication_identity": None,
                  "interventions": [], "intake_output": None, "notification": None},
        "whisper": {"symptoms": [], "clinical_status": None, "medication_identity": "Insulin",
                    "interventions": [], "intake_output": None, "notification": None},
        "check_field": "medication_identity_match",
        "expected_basis": {"whisper_only"},
    },
    {
        "label": "대조군 - clinical_status value_substitution (alert vs drowsy) -> value_substitution 기대",
        "gold": {"symptoms": [], "clinical_status": "alert", "medication_identity": None,
                  "interventions": [], "intake_output": None, "notification": None},
        "whisper": {"symptoms": [], "clinical_status": "drowsy", "medication_identity": None,
                    "interventions": [], "intake_output": None, "notification": None},
        "check_field": "clinical_status_match",
        "expected_basis": {"value_substitution"},
    },
]


def main():
    with open("configs/config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    model = config["entity_extraction"]["claude_model"]
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    all_pass = True
    for case in CASES:
        print(f"\n{'=' * 70}\n{case['label']}\n{'=' * 70}")
        result = match_open_vocab(client, model, case["gold"], case["whisper"])
        match = result.get(case["check_field"])
        print(f"결과: {json.dumps(match, ensure_ascii=False, indent=2)}")

        basis = match.get("match_basis") if match else None
        ok = basis in case["expected_basis"]
        all_pass = all_pass and ok
        print(f"[{'OK' if ok else 'FAIL'}] match_basis={basis!r}, 기대={case['expected_basis']}")

    print(f"\n{'=' * 70}\n요약: {'모든 케이스 통과' if all_pass else '일부 실패 - 위 FAIL 항목의 프롬프트 조정 필요'}\n{'=' * 70}")


if __name__ == "__main__":
    main()
