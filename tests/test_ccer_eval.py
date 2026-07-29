"""
ccer_eval.py 단위 테스트.

limitations.md #6 대응: whisper_only(hallucination) 삽입이 CCER 점수에
실제로 반영되는지 검증한다.
"""

from src.evaluation.ccer_eval import compute_ccer, ERROR_WEIGHTS


def _gold_record(entity_type="symptom", error_type=None, match_status="matched"):
    return {
        "entity_type": entity_type,
        "gold_value": "value",
        "whisper_value": "value" if match_status == "matched" else None,
        "match_status": match_status,
        "error_type": error_type,
    }


def _hallucination_record(entity_type="symptom"):
    return {
        "entity_type": entity_type,
        "gold_value": None,
        "whisper_value": "fabricated",
        "match_status": "whisper_only",
        "error_type": "hallucination",
    }


def test_hallucination_weight_is_registered():
    assert "hallucination" in ERROR_WEIGHTS
    assert ERROR_WEIGHTS["hallucination"] > 0


def test_hallucination_only_sample_has_nonzero_ccer():
    """Gold 3개가 전부 정상 매칭이고, 추가로 whisper_only 삽입이 1개 있는 경우.
    수정 전에는 이 삽입이 CCER 점수에 전혀 반영되지 않았다(0으로 계산됨)."""
    records = [_gold_record() for _ in range(3)] + [_hallucination_record()]
    result = compute_ccer(records)

    assert result["gold_entity_count"] == 3
    assert result["error_type_profile"].get("hallucination") == 1
    expected_score = round(ERROR_WEIGHTS["hallucination"] * 1 / 3, 4)
    assert result["ccer_score"] == expected_score
    assert result["ccer_score"] > 0  # 수정 전이라면 0.0이었을 케이스


def test_no_hallucination_baseline_unaffected():
    """hallucination이 없는 기존 케이스는 결과가 그대로여야 한다 (회귀 방지)."""
    records = [_gold_record() for _ in range(2)] + [
        _gold_record(error_type="omission", match_status="omission")
    ]
    result = compute_ccer(records)
    # gold_entity_count = 3 (matched 2건 + omission 1건, 전부 gold_value가 존재)
    assert result["gold_entity_count"] == 3
    assert result["ccer_score"] == round(ERROR_WEIGHTS["omission"] * 1 / 3, 4)
    assert "hallucination" not in result["error_type_profile"]


def test_multiple_hallucinations_scale_linearly():
    records = [_gold_record() for _ in range(5)] + [_hallucination_record() for _ in range(2)]
    result = compute_ccer(records)
    expected_score = round(ERROR_WEIGHTS["hallucination"] * 2 / 5, 4)
    assert result["ccer_score"] == expected_score


if __name__ == "__main__":
    test_hallucination_weight_is_registered()
    test_hallucination_only_sample_has_nonzero_ccer()
    test_no_hallucination_baseline_unaffected()
    test_multiple_hallucinations_scale_linearly()
    print("All ccer_eval tests passed.")
