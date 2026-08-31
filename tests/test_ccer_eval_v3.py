"""
ccer_eval.py v3 변경사항 단위 테스트.

docs/taxonomy_audit.md §5.3, §7.3 대응: medication_identity_error가
최상위 가중치(3)로 등록되고 CCER 점수 계산에 실제로 반영되는지 확인.
"""

from src.evaluation.ccer_eval import compute_ccer, ERROR_WEIGHTS


def _gold_record(entity_type="symptom"):
    return {
        "entity_type": entity_type, "gold_value": "value", "whisper_value": "value",
        "match_status": "matched", "error_type": None
    }


def _medication_identity_error_record():
    return {
        "entity_type": "medication_identity", "gold_value": "Hydralazine", "whisper_value": "Hydroxyzine",
        "match_status": "error", "error_type": "medication_identity_error"
    }


def test_medication_identity_error_weight_registered_at_top_tier():
    assert ERROR_WEIGHTS["medication_identity_error"] == 3
    # 다른 최상위 등급들과 동일한지 확인
    assert ERROR_WEIGHTS["medication_identity_error"] == ERROR_WEIGHTS["numeric_error"]
    assert ERROR_WEIGHTS["medication_identity_error"] == ERROR_WEIGHTS["hallucination"]


def test_medication_identity_error_reflected_in_ccer_score():
    records = [_gold_record() for _ in range(4)] + [_medication_identity_error_record()]
    result = compute_ccer(records)
    # gold_entity_count = 5 (matched 4건 + medication_identity_error 1건, 전부 gold_value 존재)
    assert result["gold_entity_count"] == 5
    assert result["error_type_profile"].get("medication_identity_error") == 1
    expected_score = round(ERROR_WEIGHTS["medication_identity_error"] * 1 / 5, 4)
    assert result["ccer_score"] == expected_score
    assert result["ccer_score"] > 0


def test_medication_identity_error_appears_in_entity_type_profile():
    """Profile 축 확인: medication_identity가 별도 entity_type으로 집계되는지."""
    records = [_gold_record() for _ in range(2)] + [_medication_identity_error_record()]
    result = compute_ccer(records)
    assert "medication_identity" in result["entity_error_profile"]


if __name__ == "__main__":
    test_medication_identity_error_weight_registered_at_top_tier()
    test_medication_identity_error_reflected_in_ccer_score()
    test_medication_identity_error_appears_in_entity_type_profile()
    print("All ccer_eval v3 tests passed.")
