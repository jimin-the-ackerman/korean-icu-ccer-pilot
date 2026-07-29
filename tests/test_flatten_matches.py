"""
flatten_matches.py 단위 테스트.

limitations.md #6 (whisper_only 페널티 부재)과 #5 (음차 전사 오판)를
고치는 과정에서 생긴 로직 변경을 검증한다. 실제 API 호출 없이,
entity_matcher.py / semantic_matcher.py가 반환할 법한 형태의 합성 데이터로
flatten_matches.py의 동작만 독립적으로 확인한다.
"""

from src.evaluation.flatten_matches import (
    flatten_closed_vocab,
    flatten_open_vocab,
    flatten_all_matches,
    OMISSION_EQUIVALENT_BASES,
)


def test_closed_vocab_whisper_only_gets_hallucination_error_type():
    """entity_matcher.py가 만드는 whisper_only(error_type=None) 레코드가
    flatten_closed_vocab을 거치면 error_type="hallucination"으로 바뀌어야 한다."""
    closed_matches = [
        {
            "entity_type": "device", "gold_value": None, "whisper_value": "ventilator",
            "match_status": "whisper_only", "error_type": None
        },
        {
            "entity_type": "route", "gold_value": "IV", "whisper_value": "IV",
            "match_status": "matched", "error_type": None
        },
    ]
    result = flatten_closed_vocab(closed_matches)

    whisper_only_records = [r for r in result if r["match_status"] == "whisper_only"]
    assert len(whisper_only_records) == 1
    assert whisper_only_records[0]["error_type"] == "hallucination"

    matched_records = [r for r in result if r["match_status"] == "matched"]
    assert matched_records[0]["error_type"] is None  # 정상 매칭은 영향받지 않아야 함


def test_closed_vocab_does_not_mutate_input():
    """flatten_closed_vocab이 원본 dict를 in-place로 변경하지 않는지 확인
    (동일 matched_data가 entity_eval.py 등 다른 소비자에서도 재사용되므로 중요)."""
    original = [{
        "entity_type": "device", "gold_value": None, "whisper_value": "ventilator",
        "match_status": "whisper_only", "error_type": None
    }]
    flatten_closed_vocab(original)
    assert original[0]["error_type"] is None


def test_open_vocab_whisper_only_symptom_gets_hallucination():
    open_matches = {
        "symptom_matches": [],
        "whisper_only_symptoms": ["환각으로 삽입된 증상"],
        "clinical_status_match": None,
        "intervention_matches": [],
        "whisper_only_interventions": [],
        "notification_match": None,
    }
    result = flatten_open_vocab(open_matches)
    assert len(result) == 1
    assert result[0]["match_status"] == "whisper_only"
    assert result[0]["error_type"] == "hallucination"


def test_phonetic_artifact_treated_as_omission():
    """semantic_matcher.py가 match_basis="phonetic_artifact"로 판정한 항목은
    CCER/entity-eval 관점에서 omission과 동일하게 집계되어야 한다."""
    open_matches = {
        "symptom_matches": [
            {
                "gold_value": "chest pain", "whisper_value": "체스파인",
                "match_basis": "phonetic_artifact",
                "negation_match": None, "severity_match": None,
            }
        ],
        "whisper_only_symptoms": [],
        "clinical_status_match": None,
        "intervention_matches": [],
        "whisper_only_interventions": [],
        "notification_match": None,
    }
    result = flatten_open_vocab(open_matches)
    assert len(result) == 1
    assert result[0]["match_status"] == "omission"
    assert result[0]["error_type"] == "omission"
    assert result[0]["whisper_value"] is None  # 음차 잔재는 "보존된 정보"로 집계하지 않음


def test_genuine_semantic_match_still_counted_as_matched():
    """회귀 방지: 진짜 semantic match(예: dyspnea/호흡곤란)는 여전히 matched로 남아야 한다."""
    open_matches = {
        "symptom_matches": [
            {
                "gold_value": "dyspnea", "whisper_value": "호흡곤란",
                "match_basis": "semantic",
                "negation_match": True, "severity_match": True,
            }
        ],
        "whisper_only_symptoms": [],
        "clinical_status_match": None,
        "intervention_matches": [],
        "whisper_only_interventions": [],
        "notification_match": None,
    }
    result = flatten_open_vocab(open_matches)
    assert result[0]["match_status"] == "matched"
    assert result[0]["error_type"] is None


def test_clinical_status_phonetic_artifact_treated_as_omission():
    open_matches = {
        "symptom_matches": [],
        "whisper_only_symptoms": [],
        "clinical_status_match": {
            "gold_value": "drowsy", "whisper_value": "드로위",
            "match_basis": "phonetic_artifact",
        },
        "intervention_matches": [],
        "whisper_only_interventions": [],
        "notification_match": None,
    }
    result = flatten_open_vocab(open_matches)
    assert len(result) == 1
    assert result[0]["match_status"] == "omission"


def test_omission_equivalent_bases_contains_expected_values():
    assert set(OMISSION_EQUIVALENT_BASES) == {"omission", "phonetic_artifact"}


def test_flatten_all_matches_combines_closed_and_open():
    matched_data = {
        "closed_vocab_matches": [
            {"entity_type": "device", "gold_value": None, "whisper_value": "vent",
             "match_status": "whisper_only", "error_type": None},
        ],
        "open_vocab_matches": {
            "symptom_matches": [], "whisper_only_symptoms": ["fake symptom"],
            "clinical_status_match": None,
            "intervention_matches": [], "whisper_only_interventions": [],
            "notification_match": None,
        },
    }
    records = flatten_all_matches(matched_data)
    assert len(records) == 2
    assert all(r["error_type"] == "hallucination" for r in records)


if __name__ == "__main__":
    test_closed_vocab_whisper_only_gets_hallucination_error_type()
    test_closed_vocab_does_not_mutate_input()
    test_open_vocab_whisper_only_symptom_gets_hallucination()
    test_phonetic_artifact_treated_as_omission()
    test_genuine_semantic_match_still_counted_as_matched()
    test_clinical_status_phonetic_artifact_treated_as_omission()
    test_omission_equivalent_bases_contains_expected_values()
    test_flatten_all_matches_combines_closed_and_open()
    print("All flatten_matches tests passed.")
