"""
v4 style-invariant closed-vocab extraction 유닛 테스트.
docs/v4_style_invariant_extraction_spec.md §10 테스트 계획을 그대로 구현.
"""

from src.entity_extraction.closed_vocab_extractor import (
    extract_closed_vocab_entities,
    extract_route,
    extract_frequency,
    extract_device,
    extract_vital_sign,
    extract_dose,
)


# ============================================================
# 10.1 Style-invariance 핵심 테스트
# ============================================================

def test_bp_style_invariance():
    for text in ["BP 120/80", "혈압 120/80", "blood pressure 120/80"]:
        result = extract_vital_sign(text)
        assert len(result) == 1, f"실패: {text!r}"
        assert result[0]["label"] == "bp"
        assert result[0]["value"] == "120/80"


def test_iv_style_invariance():
    for text in ["Aspirin 325mg IV 투여함", "Aspirin 325mg 정맥으로 투여함",
                 "Aspirin 325mg 정맥주사로 투여함", "Aspirin 325mg intravenous 투여함",
                 "Aspirin 325mg 아이비로 투여함"]:
        result = extract_route(text)
        assert any(r["normalized"] == "iv" for r in result), f"실패: {text!r}"


def test_q4h_style_invariance():
    for text in ["Aspirin 325mg q4h 투여함", "Aspirin 325mg 매 4시간마다 투여함",
                 "Aspirin 325mg 4시간마다 투여함", "Aspirin 325mg every 4 hours 투여함"]:
        result = extract_frequency(text)
        assert any(r["normalized"] == "q4h" for r in result), f"실패: {text!r}"


def test_nc_style_invariance():
    for text in ["NC 사용 중", "nasal cannula 사용 중", "비강 캐뉼라 사용 중"]:
        result = extract_device(text)
        assert any(r["normalized"] == "nc" for r in result), f"실패: {text!r}"


# ============================================================
# 10.2 Value mismatch 테스트
# ============================================================

def test_bp_value_mismatch_detected():
    gold = extract_vital_sign("혈압 120/80")
    whisper = extract_vital_sign("혈압 120/60")
    assert gold[0]["label"] == whisper[0]["label"] == "bp"
    assert gold[0]["value"] != whisper[0]["value"]


def test_q4h_vs_q6h_different_normalized_value():
    gold = extract_frequency("q4h")
    whisper = extract_frequency("매 6시간마다")
    assert gold[0]["normalized"] == "q4h"
    assert whisper[0]["normalized"] == "q6h"
    assert gold[0]["normalized"] != whisper[0]["normalized"]


# ============================================================
# 10.2b Dose Ownership 테스트 (§3.5 4단계 hierarchy)
# ============================================================

def _dose_for(text):
    vs = extract_vital_sign(text)
    route = extract_route(text)
    freq = extract_frequency(text)
    return extract_dose(text, vs, route, freq)


def test_morphine_with_route_is_dose():
    result = _dose_for("Morphine 2 mg IV 투여함.")
    assert len(result) == 1
    assert result[0]["value"] == "2"


def test_urine_output_not_dose():
    result = _dose_for("Urine output 200 mL over 4 hours 확인됨.")
    assert result == []


def test_bp_stt_artifact_not_dose():
    result = _dose_for("BP 90-60mg, HR 98 bpm.")
    assert result == [], f"vital_sign 소유 숫자가 dose로 잘못 인정됨: {result}"


def test_fluid_volume_not_dose():
    result = _dose_for("IV fluids 500mL 투여함.")
    assert result == [], f"수액 volume이 dose로 잘못 인정됨(§3.5.1 위반): {result}"


def test_ns_fluid_not_dose():
    result = _dose_for("NS 500mL infusion 시행함.")
    assert result == []


def test_dose_with_only_admin_verb_no_route_frequency():
    """route/frequency가 없어도 투약 동사만으로 dose 인정 (scaffold frequency null 대응)."""
    result = _dose_for("Morphine 4mg 투여함.")
    assert len(result) == 1
    assert result[0]["value"] == "4"


def test_aspirin_po_stat_full_example():
    result = _dose_for("Aspirin 325 mg PO STAT.")
    assert len(result) == 1
    assert result[0]["value"] == "325"


def test_genuine_dose_pattern_regression_from_original_pilot():
    """지난주 실제 데이터 재현: Ceftriaxone 1g IV q12h 형태."""
    result = _dose_for("Ceftriaxone 1g IV q12h 적용함.")
    assert len(result) == 1


def test_decimal_dose_not_split_by_clause_boundary():
    """0.3mg처럼 소수점이 있는 dose가 절 경계 오분류로 신호를 놓치지 않는지."""
    result = _dose_for("Epinephrine 0.3mg IM 투여함.")
    assert len(result) == 1
    assert result[0]["value"] == "0.3"


def test_runon_text_fallback():
    """구두점이 전혀 없는 run-on 텍스트에서 fallback 경로가 정상 동작하는지."""
    text = ("65세 남성 환자 Pneumonia로 인한 Respiratory Distress 호소함 "
            "BP 165 HR 110 RR 88 BT 32 SpO2 88 Moderate cough 확인됨 "
            "Ceftriaxone 1g IV Q12H 적용함 High flow nasal cannula 산소지원 유지함")
    result = _dose_for(text)
    assert any(r["value"] == "1" for r in result), "run-on 텍스트에서 fallback으로도 못 잡음"


def test_route_frequency_admin_verb_all_absent_correctly_omitted():
    """Architecture A의 알려진 한계(§6.2): 세 신호가 전부 없으면 의도적으로 omission."""
    result = _dose_for("Morphine 4mg.")
    assert result == [], "신호가 전혀 없는 경우는 A의 설계상 인정하지 않아야 함"


# ============================================================
# 10.3 회귀 테스트 (기존 영어 전용 케이스)
# ============================================================

def test_existing_pilot_sample_still_works():
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
    result = extract_closed_vocab_entities(gold_sample)
    assert any(v["label"] == "bp" and v["value"] == "100/65" for v in result["vital_sign"])
    assert any(v["label"] == "hr" and v["value"] == "110" for v in result["vital_sign"])
    assert any(r["normalized"] == "iv" for r in result["route"])
    assert any(f["normalized"] == "q12h" for f in result["frequency"])
    assert any(d["normalized"] == "nc" for d in result["device"])
    assert any(d["normalized"] == "ventilator" for d in result["device"])
    assert len(result["dose"]) == 1


# ============================================================
# 10.4 False positive(교차 오염) 방지 테스트 — §5 대응
# ============================================================

def test_dyspnea_symptom_not_matched_as_rr():
    result = extract_vital_sign("환자는 호흡곤란을 호소함")
    assert result == [], f"호흡곤란(symptom)이 RR로 오매칭됨: {result}"


def test_respiratory_monitoring_not_matched_as_rr():
    """한계 #13 사례: '호흡 상태 모니터링'이 RR로 오매칭되지 않는지."""
    result = extract_vital_sign("호흡 상태 밀착 모니터링 필요")
    assert result == [], f"호흡 상태(intervention)가 RR로 오매칭됨: {result}"


def test_varicose_vein_not_matched_as_iv_route():
    result = extract_route("식도 정맥류로 인한 위장관 출혈")
    assert not any(r["normalized"] == "iv" for r in result), \
        f"정맥류(symptom)가 IV route로 오매칭됨: {result}"


def test_central_line_device_not_matched_as_iv_route():
    result = extract_route("중심정맥관이 삽입되어 있다")
    assert not any(r["normalized"] == "iv" for r in result), \
        f"정맥관(device)이 IV route로 오매칭됨: {result}"


def test_io_monitoring_not_matched_as_frequency():
    result = extract_frequency("4시간 동안 200mL 확인됨")
    assert result == [], f"io 서술('동안')이 frequency로 오매칭됨: {result}"


def test_bare_frequency_number_pattern_requires_suffix():
    """'4시간마다'류 접미사 없이 단순 숫자+시간만 있으면 매칭 안 되는지."""
    result = extract_frequency("4시간 관찰함")
    assert result == []


# ============================================================
# 10.5 실데이터 스캔 (별도 스크립트로 실행 - src/analysis/v4_crosscheck.py)
# ============================================================
# 100개 시나리오 실제 텍스트 전수 스캔은 유닛 테스트가 아니라
# src/analysis/v4_crosscheck.py에서 별도로 실행하고 결과를 보고한다.


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
