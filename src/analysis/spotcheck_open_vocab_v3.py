"""
v3 open_vocab_extractor.py 로컬 spot-check (실제 Claude API 호출 필요)

목적: docs/taxonomy_audit.md §5/§8에서 확정한 taxonomy가 실제 Claude 추출에서
의도대로 동작하는지, 15샘플 전체 재실행 전에 대표 transcript 3개로 먼저 확인.

확인 항목:
1. medication_identity가 정확히 추출되는가 (약물명만, dose/route 없이)
2. intake_output이 정확히 추출되는가
3. device/oxygen_support(ventilator, nasal cannula, Foley 등)가 interventions에
   중복으로 들어가지 않는가 (§3.3에서 확인된 duplicated concept 문제가 실제로
   해소됐는지)
4. 기존 intervention(예: fluid resuscitation)은 여전히 정상적으로 잡히는가

대상 샘플 (data/stt_transcripts/*.json, 이미 레포에 존재하는 실제 Whisper 전사):
- scenario_001_clinical_charting: 심하게 뭉개진 STT, device(ventilator+nc) 포함, io 없음
- scenario_004_clinical_charting: 중간 정도 잡음, medication+intervention+device+io 전부 포함
- scenario_002_formal_template: 깨끗한 한국어 완전문장, 한국어 약물명("인슐린")·
  한국어 io 서술("소변량은 저하된 상태였다") 테스트

사용법 (로컬, .env에 ANTHROPIC_API_KEY 필요):
    python -m src.analysis.spotcheck_open_vocab_v3
"""

import json
import os

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from src.entity_extraction.open_vocab_extractor import extract_open_vocab_entities

load_dotenv()

SAMPLES = [
    "scenario_001_clinical_charting",
    "scenario_004_clinical_charting",
    "scenario_002_formal_template",
]

# 각 샘플에서 사람이 직접 확인한 기대값 (Gold 텍스트/scaffold 기반)
EXPECTATIONS = {
    "scenario_001_clinical_charting": {
        "medication_identity_should_mention": "ceftriaxone",
        "intake_output_should_be_null": True,
        "interventions_should_not_contain": ["ventilator", "nasal cannula", "산소"],
    },
    "scenario_004_clinical_charting": {
        "medication_identity_should_mention": "morphine",
        "intake_output_should_be_null": False,
        "interventions_should_not_contain": ["foley"],
        "interventions_should_contain": ["fluid resuscitation"],
    },
    "scenario_002_formal_template": {
        "medication_identity_should_mention": "인슐린",  # or "insulin"
        "intake_output_should_be_null": False,
        "interventions_should_contain": ["fluid resuscitation"],
    },
}


def check_sample(client, model, sample_id):
    path = f"data/stt_transcripts/{sample_id}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    text = data["whisper_transcript"]

    print(f"\n{'=' * 70}\n{sample_id}\n{'=' * 70}")
    print(f"원문: {text}\n")

    result = extract_open_vocab_entities(client, model, text)
    print("추출 결과:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    exp = EXPECTATIONS[sample_id]
    print("\n--- 자동 체크 ---")

    med = (result.get("medication_identity") or "").lower()
    expected_med = exp["medication_identity_should_mention"].lower()
    med_ok = expected_med in med
    print(f"[{'OK' if med_ok else 'FAIL'}] medication_identity에 '{expected_med}' 포함: "
          f"실제값={result.get('medication_identity')!r}")

    io_val = result.get("intake_output")
    if exp["intake_output_should_be_null"]:
        io_ok = io_val is None
        print(f"[{'OK' if io_ok else 'FAIL'}] intake_output이 null이어야 함: 실제값={io_val!r}")
    else:
        io_ok = io_val is not None
        print(f"[{'OK' if io_ok else 'FAIL'}] intake_output이 null이 아니어야 함: 실제값={io_val!r}")

    interventions_lower = [i.lower() for i in result.get("interventions", [])]
    dup_ok = True
    for forbidden in exp.get("interventions_should_not_contain", []):
        if any(forbidden.lower() in i for i in interventions_lower):
            dup_ok = False
            print(f"[FAIL] interventions에 '{forbidden}'이(가) 들어있으면 안 됨: {result.get('interventions')}")
    if dup_ok and exp.get("interventions_should_not_contain"):
        print(f"[OK] interventions에 device/oxygen_support 관련 중복 없음: {result.get('interventions')}")

    contain_ok = True
    for required in exp.get("interventions_should_contain", []):
        if not any(required.lower() in i for i in interventions_lower):
            contain_ok = False
            print(f"[FAIL] interventions에 '{required}'이(가) 있어야 하는데 없음: {result.get('interventions')}")
    if contain_ok and exp.get("interventions_should_contain"):
        print(f"[OK] 기대한 intervention이 정상적으로 포함됨: {result.get('interventions')}")

    return med_ok and io_ok and dup_ok and contain_ok


def main():
    with open("configs/config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    model = config["entity_extraction"]["claude_model"]  # 파이프라인과 동일 모델 사용

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    results = {}
    for sample_id in SAMPLES:
        results[sample_id] = check_sample(client, model, sample_id)

    print(f"\n{'=' * 70}\n요약\n{'=' * 70}")
    for sample_id, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}: {sample_id}")

    if all(results.values()):
        print("\n모든 spot-check 통과. semantic_matcher.py 단계로 진행 가능.")
    else:
        print("\n일부 실패. 프롬프트 조정이 필요할 수 있음 - 실패한 샘플의 "
              "추출 결과 전체를 다시 확인할 것.")


if __name__ == "__main__":
    main()
