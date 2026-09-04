"""
hybrid_manipulation_check.py 핵심 판별 로직 검증.
실제 hybrid 데이터 생성 전에, 검사 로직 자체가 올바른지 합성 텍스트로 확인.
"""

from src.analysis.hybrid_manipulation_check import check_sample, is_korean_form


def test_is_korean_form_detects_hangul():
    assert is_korean_form("정맥으로") is True
    assert is_korean_form("IV") is False
    assert is_korean_form("IV로") is True  # 혼합이어도 한글 있으면 True


def test_well_formed_hybrid_sample_passes():
    """block mapping을 잘 따른 hybrid 텍스트 - 위반 0건이어야 함."""
    text = (
        "72세 여성 환자가 급성 심근경색으로 입원하였다. "
        "혈압은 145/90 mmHg이며 심박수는 110 bpm으로 확인되었다.\n"
        "Aspirin 325mg PO STAT 투여함.\n"
        "환자는 심한 흉통을 호소하였다.\n"
        "NC 유지함."
    )
    r = check_sample(text)
    # vital_sign(혈압/심박수)이 한국어 라벨로 나옴 -> Formal 표현 준수
    assert r["formal_block_total"] >= 2
    assert r["formal_block_korean_form"] == r["formal_block_total"]
    # route(PO)가 영어 약어로 나옴 -> Clinical 표현 준수
    assert r["clinical_block_total"] >= 1
    assert r["clinical_block_english_form"] == r["clinical_block_total"]


def test_medication_leaked_into_formal_style_detected():
    """route가 한국어로 새어나온 경우 -> Clinical 표현 위반으로 잡혀야 함."""
    text = "Aspirin 325mg을 경구로 즉시 투여하였다."
    r = check_sample(text)
    assert r["clinical_block_total"] >= 1
    assert r["clinical_block_english_form"] < r["clinical_block_total"]


def test_vital_sign_leaked_into_clinical_style_detected():
    """vital_sign이 영어 약어로 새어나온 경우 -> Formal 표현 위반으로 잡혀야 함."""
    text = "BP 90/60, HR 120 확인함."
    r = check_sample(text)
    assert r["formal_block_total"] >= 2
    assert r["formal_block_korean_form"] < r["formal_block_total"]


if __name__ == "__main__":
    test_is_korean_form_detects_hangul()
    test_well_formed_hybrid_sample_passes()
    test_medication_leaked_into_formal_style_detected()
    test_vital_sign_leaked_into_clinical_style_detected()
    print("All hybrid manipulation check tests passed.")
