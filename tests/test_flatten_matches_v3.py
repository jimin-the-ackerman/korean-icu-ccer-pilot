"""
flatten_matches.py v3 변경사항 단위 테스트.

docs/taxonomy_audit.md §5.3, §8 대응:
- medication_identity_match, intake_output_match이 올바른 entity_type으로
  flatten되는지
- value_substitution이 entity_type별로 다른 error_type으로 매핑되는지
  (medication_identity -> medication_identity_error, 나머지 -> substitution)
"""

from src.evaluation.flatten_matches import flatten_open_vocab, VALUE_SUBSTITUTION_ERROR_TYPE


def _base_open_matches(**overrides):
    base = {
        "symptom_matches": [], "whisper_only_symptoms": [],
        "clinical_status_match": None,
        "medication_identity_match": None,
        "intervention_matches": [], "whisper_only_interventions": [],
        "intake_output_match": None,
        "notification_match": None,
    }
    base.update(overrides)
    return base


def test_medication_identity_value_substitution_gets_dedicated_error_type():
    open_matches = _base_open_matches(
        medication_identity_match={
            "gold_value": "Hydralazine", "whisper_value": "Hydroxyzine",
            "match_basis": "value_substitution"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert len(records) == 1
    r = records[0]
    assert r["entity_type"] == "medication_identity"
    assert r["match_status"] == "error"
    assert r["error_type"] == "medication_identity_error"


def test_clinical_status_value_substitution_gets_generic_substitution():
    """회귀 방지: medication_identity가 아닌 필드는 기존 substitution 유지."""
    open_matches = _base_open_matches(
        clinical_status_match={
            "gold_value": "alert", "whisper_value": "drowsy",
            "match_basis": "value_substitution"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["error_type"] == "substitution"
    assert records[0]["entity_type"] == "clinical_status"


def test_notification_value_substitution_gets_generic_substitution():
    open_matches = _base_open_matches(
        notification_match={
            "gold_value": "RT notified", "whisper_value": "MD notified",
            "match_basis": "value_substitution"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["error_type"] == "substitution"


def test_intake_output_value_substitution_gets_generic_substitution():
    open_matches = _base_open_matches(
        intake_output_match={
            "gold_value": "urine output 200 mL", "whisper_value": "urine output 50 mL",
            "match_basis": "value_substitution"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["entity_type"] == "intake_output"
    assert records[0]["error_type"] == "substitution"


def test_medication_identity_semantic_match_is_matched_no_error():
    """회귀 방지: 진짜 semantic match(Ceftriaxone/Cephtriaxone)는 matched로 남아야 함."""
    open_matches = _base_open_matches(
        medication_identity_match={
            "gold_value": "Ceftriaxone", "whisper_value": "Cephtriaxone",
            "match_basis": "semantic"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["match_status"] == "matched"
    assert records[0]["error_type"] is None


def test_medication_identity_omission():
    open_matches = _base_open_matches(
        medication_identity_match={
            "gold_value": "Ceftriaxone", "whisper_value": None,
            "match_basis": "omission"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["match_status"] == "omission"
    assert records[0]["error_type"] == "omission"


def test_medication_identity_whisper_only_gets_hallucination():
    open_matches = _base_open_matches(
        medication_identity_match={
            "gold_value": None, "whisper_value": "Insulin",
            "match_basis": "whisper_only"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["match_status"] == "whisper_only"
    assert records[0]["error_type"] == "hallucination"


def test_medication_identity_phonetic_artifact_treated_as_omission():
    open_matches = _base_open_matches(
        medication_identity_match={
            "gold_value": "Ceftriaxone", "whisper_value": "체프트리악손",
            "match_basis": "phonetic_artifact"
        }
    )
    records = flatten_open_vocab(open_matches)
    assert records[0]["match_status"] == "omission"
    assert records[0]["error_type"] == "omission"


def test_medication_identity_and_intake_output_both_null_excluded():
    open_matches = _base_open_matches(
        medication_identity_match={"gold_value": None, "whisper_value": None, "match_basis": "both_null"},
        intake_output_match={"gold_value": None, "whisper_value": None, "match_basis": "both_null"},
    )
    records = flatten_open_vocab(open_matches)
    assert records == []


def test_value_substitution_error_type_mapping_table():
    assert VALUE_SUBSTITUTION_ERROR_TYPE["medication_identity"] == "medication_identity_error"
    assert "clinical_status" not in VALUE_SUBSTITUTION_ERROR_TYPE  # 기본값(substitution) 사용


def test_all_four_single_value_fields_processed_together():
    """네 필드가 동시에 존재해도 각각 독립적으로 올바르게 처리되는지."""
    open_matches = _base_open_matches(
        clinical_status_match={"gold_value": "alert", "whisper_value": "alert", "match_basis": "exact"},
        medication_identity_match={"gold_value": "Morphine", "whisper_value": "Insulin", "match_basis": "value_substitution"},
        intake_output_match={"gold_value": "urine output low", "whisper_value": None, "match_basis": "omission"},
        notification_match={"gold_value": None, "whisper_value": "RT notified", "match_basis": "whisper_only"},
    )
    records = flatten_open_vocab(open_matches)
    by_type = {r["entity_type"]: r for r in records}
    assert by_type["clinical_status"]["match_status"] == "matched"
    assert by_type["medication_identity"]["error_type"] == "medication_identity_error"
    assert by_type["intake_output"]["error_type"] == "omission"
    assert by_type["notification"]["error_type"] == "hallucination"


if __name__ == "__main__":
    test_medication_identity_value_substitution_gets_dedicated_error_type()
    test_clinical_status_value_substitution_gets_generic_substitution()
    test_notification_value_substitution_gets_generic_substitution()
    test_intake_output_value_substitution_gets_generic_substitution()
    test_medication_identity_semantic_match_is_matched_no_error()
    test_medication_identity_omission()
    test_medication_identity_whisper_only_gets_hallucination()
    test_medication_identity_phonetic_artifact_treated_as_omission()
    test_medication_identity_and_intake_output_both_null_excluded()
    test_value_substitution_error_type_mapping_table()
    test_all_four_single_value_fields_processed_together()
    print("All flatten_matches v3 tests passed.")
