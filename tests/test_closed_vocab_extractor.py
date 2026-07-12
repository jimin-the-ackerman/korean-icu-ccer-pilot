"""
Closed-vocabulary Entity Extractor 단위 테스트.
실제 파일럿 샘플(scenario_001_telegraphic_icu)의 Gold/Whisper 텍스트로 검증.
"""

from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities

gold_sample = """65세 남성, 호흡곤란, 폐렴.
BP 100/65.
HR 110.
RR 28.
BT 38.1.
SpO2 88%.
Cough moderate.
Ceftriaxone 1g IV q12h.
High-flow nasal cannula 사용.
Ventilator 사용.
임상상태 drowsy.
RT notify."""

whisper_sample = "육신함성 후 곤란 폐렴 BP 165 HR 28 BT 38.1 SPO2 88% COUGH MODERATE 세프트 리액션 1g IV Q12H HIGH FLOW NASAL CANNULA 사용 VENTILATOR 사용 임상상태 DROWSY RT NOTIFY"


def test_gold_extraction():
    result = extract_closed_vocab_entities(gold_sample)
    print("=== Gold 추출 결과 ===")
    for entity_type, items in result.items():
        print(f"{entity_type}: {items}")


def test_whisper_extraction():
    result = extract_closed_vocab_entities(whisper_sample)
    print("\n=== Whisper 추출 결과 ===")
    for entity_type, items in result.items():
        print(f"{entity_type}: {items}")


if __name__ == "__main__":
    test_gold_extraction()
    test_whisper_extraction()