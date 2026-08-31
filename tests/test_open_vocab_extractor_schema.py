"""
open_vocab_extractor.py 스키마/프롬프트 검증 테스트 (v3 taxonomy 반영, API 미호출).

docs/taxonomy_audit.md §5, §8 대응:
- EXTRACTION_TOOL에 medication_identity, intake_output 필드가 추가되었는지
- interventions의 description에서 device/oxygen_support/io/medication이
  명시적으로 제외되어 있는지
- SYSTEM_PROMPT에 경계 규칙과 실제 반례(ventilator, nasal cannula, io 등)가
  포함되어 있는지

실제 Claude 호출 결과의 정확성은 이 테스트로 검증할 수 없다 — 로컬 환경에서
API로 별도 확인이 필요하다 (다음 단계).
"""

from src.entity_extraction.open_vocab_extractor import EXTRACTION_TOOL, SYSTEM_PROMPT

SCHEMA = EXTRACTION_TOOL["input_schema"]
PROPS = SCHEMA["properties"]


def test_required_fields_include_new_categories():
    assert set(SCHEMA["required"]) == {
        "symptoms", "clinical_status", "medication_identity",
        "interventions", "intake_output", "notification"
    }


def test_medication_identity_field_exists_as_single_nullable_string():
    field = PROPS["medication_identity"]
    assert field["type"] == ["string", "null"]


def test_intake_output_field_exists_as_single_nullable_string():
    field = PROPS["intake_output"]
    assert field["type"] == ["string", "null"]


def test_interventions_description_excludes_device_and_oxygen_support():
    desc = PROPS["interventions"]["description"].lower()
    assert "device" in desc
    assert "ventilator" in desc or "nasal cannula" in desc
    assert "medication" in desc
    assert "intake" in desc or "fluid" in desc


def test_symptoms_and_clinical_status_and_notification_unchanged():
    """회귀 방지: 기존 필드 타입/구조가 그대로 유지되는지."""
    assert PROPS["symptoms"]["type"] == "array"
    assert PROPS["clinical_status"]["type"] == ["string", "null"]
    assert PROPS["notification"]["type"] == ["string", "null"]


def test_system_prompt_has_category_boundary_checklist():
    assert "Category boundaries" in SYSTEM_PROMPT
    assert "medication_identity" in SYSTEM_PROMPT
    assert "intake_output" in SYSTEM_PROMPT


def test_system_prompt_has_real_pilot_data_examples():
    """taxonomy_audit.md에서 실제로 문제가 됐던 표현들이 반례로 들어있는지."""
    assert "Ventilator" in SYSTEM_PROMPT
    assert "nasal cannula" in SYSTEM_PROMPT
    assert "Ceftriaxone" in SYSTEM_PROMPT
    assert "Urine output" in SYSTEM_PROMPT or "urine output" in SYSTEM_PROMPT


def test_system_prompt_still_has_verbatim_extraction_rule():
    """회귀 방지: 기존 hallucination 방지 규칙(축어적 추출)이 유지되는지."""
    assert "Verbatim extraction only" in SYSTEM_PROMPT
    assert "garbled" in SYSTEM_PROMPT


if __name__ == "__main__":
    test_required_fields_include_new_categories()
    test_medication_identity_field_exists_as_single_nullable_string()
    test_intake_output_field_exists_as_single_nullable_string()
    test_interventions_description_excludes_device_and_oxygen_support()
    test_symptoms_and_clinical_status_and_notification_unchanged()
    test_system_prompt_has_category_boundary_checklist()
    test_system_prompt_has_real_pilot_data_examples()
    test_system_prompt_still_has_verbatim_extraction_rule()
    print("All open_vocab_extractor schema tests passed.")
