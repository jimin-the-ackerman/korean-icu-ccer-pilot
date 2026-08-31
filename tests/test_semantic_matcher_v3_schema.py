"""
semantic_matcher.py v3 스키마/프롬프트 검증 테스트 (API 미호출).

docs/taxonomy_audit.md §5, §8 대응:
- medication_identity_match, intake_output_match 신설 확인
- value_substitution match_basis가 4개 단일값 필드에 공통 추가됐는지
- medication_identity에 대한 엄격한 LASA 안전 규칙과 긍정/부정 사례가
  프롬프트에 포함됐는지

실제 Claude 판정의 정확성(Ceftriaxone/Cephtriaxone을 실제로 semantic으로,
Hydralazine/Hydroxyzine을 실제로 value_substitution으로 판정하는지)은 이
테스트로 검증할 수 없다 — 로컬 환경에서 실제 API로 별도 확인이 필요하다.
"""

from src.matching.semantic_matcher import MATCH_TOOL, SYSTEM_PROMPT, is_valid_match_result

PROPS = MATCH_TOOL["input_schema"]["properties"]
REQUIRED = MATCH_TOOL["input_schema"]["required"]


def test_medication_identity_match_field_exists():
    assert "medication_identity_match" in PROPS
    assert "medication_identity_match" in REQUIRED
    field = PROPS["medication_identity_match"]
    assert field["type"] == "object"
    assert set(field["required"]) == {"gold_value", "whisper_value", "match_basis"}


def test_intake_output_match_field_exists():
    assert "intake_output_match" in PROPS
    assert "intake_output_match" in REQUIRED
    field = PROPS["intake_output_match"]
    assert field["type"] == "object"


def test_value_substitution_added_to_all_four_single_value_fields():
    for field_name in ["clinical_status_match", "medication_identity_match",
                        "intake_output_match", "notification_match"]:
        enum = PROPS[field_name]["properties"]["match_basis"]["enum"]
        assert "value_substitution" in enum, f"{field_name}에 value_substitution 누락"
        # 기존 카테고리도 보존됐는지
        assert "semantic" in enum
        assert "phonetic_artifact" in enum
        assert "whisper_only" in enum
        assert "both_null" in enum


def test_symptom_and_intervention_matches_unaffected():
    """회귀 방지: 리스트형 필드(symptom/intervention)는 value_substitution 대상이 아님."""
    symptom_enum = PROPS["symptom_matches"]["items"]["properties"]["match_basis"]["enum"]
    assert "value_substitution" not in symptom_enum
    intervention_enum = PROPS["intervention_matches"]["items"]["properties"]["match_basis"]["enum"]
    assert "value_substitution" not in intervention_enum


def test_prompt_has_value_substitution_general_rule():
    assert "value_substitution" in SYSTEM_PROMPT
    assert "alert" in SYSTEM_PROMPT and "drowsy" in SYSTEM_PROMPT  # 기존 예시 활용 확인


def test_prompt_has_medication_identity_strict_rule():
    assert "medication_identity" in SYSTEM_PROMPT
    assert "LASA" in SYSTEM_PROMPT or "look-alike" in SYSTEM_PROMPT.lower()
    assert "ISMP" in SYSTEM_PROMPT


def test_prompt_has_medication_positive_and_negative_examples():
    """긍정 사례(같은 약물의 STT 오타)와 부정 사례(실제 LASA 쌍)가 둘 다 있는지."""
    assert "Ceftriaxone" in SYSTEM_PROMPT and "Cephtriaxone" in SYSTEM_PROMPT
    assert "Hydralazine" in SYSTEM_PROMPT and "Hydroxyzine" in SYSTEM_PROMPT


def test_prompt_instructs_conservative_default_for_medication():
    """모호할 때 semantic보다 value_substitution 쪽으로 기울여야 한다는 지침이 있는지."""
    assert "prefer" in SYSTEM_PROMPT.lower() or "when in doubt" in SYSTEM_PROMPT.lower()


def test_is_valid_match_result_requires_new_fields():
    base = {
        "symptom_matches": [], "whisper_only_symptoms": [],
        "clinical_status_match": {"gold_value": None, "whisper_value": None, "match_basis": "both_null"},
        "intervention_matches": [], "whisper_only_interventions": [],
        "notification_match": {"gold_value": None, "whisper_value": None, "match_basis": "both_null"},
    }
    # medication_identity_match, intake_output_match 없이 -> invalid
    assert is_valid_match_result(dict(base)) is False

    full = dict(base)
    full["medication_identity_match"] = {"gold_value": None, "whisper_value": None, "match_basis": "both_null"}
    full["intake_output_match"] = {"gold_value": None, "whisper_value": None, "match_basis": "both_null"}
    assert is_valid_match_result(full) is True


if __name__ == "__main__":
    test_medication_identity_match_field_exists()
    test_intake_output_match_field_exists()
    test_value_substitution_added_to_all_four_single_value_fields()
    test_symptom_and_intervention_matches_unaffected()
    test_prompt_has_value_substitution_general_rule()
    test_prompt_has_medication_identity_strict_rule()
    test_prompt_has_medication_positive_and_negative_examples()
    test_prompt_instructs_conservative_default_for_medication()
    test_is_valid_match_result_requires_new_fields()
    print("All semantic_matcher v3 schema tests passed.")
