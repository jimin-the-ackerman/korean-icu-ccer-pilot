"""
scaffold_as_gold.py 단위 테스트 (v3 taxonomy 반영 검증).

docs/taxonomy_audit.md §5, §8에서 확정한 대로:
- medication_identity: scaffold["medication"]["name"] -> 단일값 open-vocab
- intake_output: scaffold["io"] -> 단일값 open-vocab
- scaffold_to_closed_vocab()은 변경되지 않아야 함 (§8.2: device/oxygen_support
  는 이미 정합이었으므로 손대지 않음)
"""

from src.entity_extraction.scaffold_as_gold import (
    scaffold_to_open_vocab,
    scaffold_to_closed_vocab,
)


def _full_scaffold(**overrides):
    base = {
        "scenario_id": "scenario_999",
        "patient_context": "65-year-old male with pneumonia",
        "vital_signs": {"BP": "100/65", "HR": "110", "RR": "28", "BT": "38.1", "SpO2": "88%"},
        "symptom": {"name": "cough", "negation": False, "severity": "moderate"},
        "medication": {"name": "Ceftriaxone", "dose": "1g", "route": "IV", "frequency": "q12h"},
        "oxygen_support": "High-flow nasal cannula",
        "intervention": None,
        "device": "ventilator",
        "io": None,
        "clinical_status": "drowsy",
        "notification": "RT notified",
    }
    base.update(overrides)
    return base


def test_medication_identity_extracted_from_medication_name():
    scaffold = _full_scaffold()
    result = scaffold_to_open_vocab(scaffold)
    assert result["medication_identity"] == "Ceftriaxone"


def test_medication_identity_none_when_no_medication():
    scaffold = _full_scaffold(medication=None)
    result = scaffold_to_open_vocab(scaffold)
    assert result["medication_identity"] is None


def test_intake_output_extracted_from_io_field():
    scaffold = _full_scaffold(io="urine output 200 mL over 4 hours")
    result = scaffold_to_open_vocab(scaffold)
    assert result["intake_output"] == "urine output 200 mL over 4 hours"


def test_intake_output_none_when_io_absent():
    scaffold = _full_scaffold(io=None)
    result = scaffold_to_open_vocab(scaffold)
    assert result["intake_output"] is None


def test_existing_open_vocab_fields_unaffected():
    """회귀 방지: symptoms/clinical_status/interventions/notification은 그대로여야 함."""
    scaffold = _full_scaffold()
    result = scaffold_to_open_vocab(scaffold)
    assert result["symptoms"] == [{"name": "cough", "negation": False, "severity": "moderate"}]
    assert result["clinical_status"] == "drowsy"
    assert result["interventions"] == []  # intervention=None
    assert result["notification"] == "RT notified"


def test_open_vocab_output_has_exactly_six_keys():
    """v3 스키마 확정: symptoms, clinical_status, medication_identity,
    interventions, intake_output, notification 6개 키만 존재해야 함."""
    scaffold = _full_scaffold()
    result = scaffold_to_open_vocab(scaffold)
    assert set(result.keys()) == {
        "symptoms", "clinical_status", "medication_identity",
        "interventions", "intake_output", "notification"
    }


def test_closed_vocab_unaffected_by_v3_change():
    """§8.2 회귀 방지: device/oxygen_support 처리는 v3에서 변경 대상이 아니므로
    scaffold_to_closed_vocab()의 동작이 v2와 동일하게 유지되어야 한다."""
    scaffold = _full_scaffold()
    result = scaffold_to_closed_vocab(scaffold)
    assert {"raw": "ventilator", "normalized": "ventilator", "position": 0} in result["device"]
    assert {"raw": "High-flow nasal cannula", "normalized": "nc", "position": 0} in result["device"]
    assert len(result["device"]) == 2
    assert result["dose"][0]["raw"] == "1g"
    assert result["route"][0]["raw"] == "IV"


def test_real_scenario_002_medication_and_io_both_present():
    """실제 scenario_002 scaffold 값 기반 (medication.name='insulin', io='urine output low')."""
    scaffold = _full_scaffold(
        medication={"name": "insulin", "dose": "10 units", "route": "SC", "frequency": None},
        io="urine output low",
        device=None,
        oxygen_support=None,
        intervention="fluid resuscitation",
    )
    result = scaffold_to_open_vocab(scaffold)
    assert result["medication_identity"] == "insulin"
    assert result["intake_output"] == "urine output low"
    assert result["interventions"] == ["fluid resuscitation"]


if __name__ == "__main__":
    test_medication_identity_extracted_from_medication_name()
    test_medication_identity_none_when_no_medication()
    test_intake_output_extracted_from_io_field()
    test_intake_output_none_when_io_absent()
    test_existing_open_vocab_fields_unaffected()
    test_open_vocab_output_has_exactly_six_keys()
    test_closed_vocab_unaffected_by_v3_change()
    test_real_scenario_002_medication_and_io_both_present()
    print("All scaffold_as_gold v3 tests passed.")
