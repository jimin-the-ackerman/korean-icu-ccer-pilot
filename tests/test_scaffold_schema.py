"""
Content Scaffold Schema 검증 테스트.
GPT-4o가 생성한 JSON이 실제로 이 Schema를 통과하는지 확인하는 용도.
파일럿 단계에서는 예시 값 1개로 수동 테스트, 이후 GPT-4o 실제 출력에도 동일하게 적용됨.
"""

import jsonschema
from src.scaffold.scaffold_schema import get_schema

# GPT-4o가 생성할 법한 예시 (§4.5 논문 예시와 동일한 케이스)
example_valid = {
    "scenario_id": "scenario_001",
    "patient_context": "72-year-old male with pneumonia, respiratory distress",
    "vital_signs": {
        "BP": "130/80",
        "HR": "118",
        "RR": "26",
        "BT": "37.2",
        "SpO2": "88%"
    },
    "symptom": {
        "name": "dyspnea",
        "negation": False,
        "severity": "moderate"
    },
    "medication": {
        "name": "Morphine",
        "dose": "2mg",
        "route": "IV",
        "frequency": None
    },
    "oxygen_support": "O2 2L NC",
    "intervention": None,
    "device": None,
    "io": None,
    "clinical_status": "alert",
    "notification": "Dr notify"
}

# 일부러 스키마를 위반하는 예시 (route에 잘못된 값)
example_invalid = {
    "scenario_id": "scenario_002",
    "patient_context": "test case",
    "vital_signs": {
        "BP": "120/80", "HR": "80", "RR": "18", "BT": "36.5", "SpO2": "98%"
    },
    "symptom": {"name": "pain", "negation": False},
    "medication": {
        "name": "Aspirin",
        "dose": "100mg",
        "route": "INVALID_ROUTE",  # 의도적 오류: enum에 없는 값
        "frequency": "BID"
    },
    "clinical_status": "alert"
}


def test_valid_example():
    schema = get_schema()
    jsonschema.validate(instance=example_valid, schema=schema)
    print("PASS: 유효한 예시가 스키마를 통과함")


def test_invalid_example():
    schema = get_schema()
    try:
        jsonschema.validate(instance=example_invalid, schema=schema)
        print("FAIL: 잘못된 예시가 통과되면 안 되는데 통과됨")
    except jsonschema.exceptions.ValidationError as e:
        print(f"PASS: 잘못된 예시가 정상적으로 거부됨 (사유: {e.message})")


if __name__ == "__main__":
    test_valid_example()
    test_invalid_example()