"""
Content Scaffold를 Gold Standard Entity로 변환

[Design Change from Proposal]
Gold Transcript에서 텍스트 기반으로 Entity를 추출하는 것을
전제했다. 파일럿 구현 중, Style(Documentation Register)에 따라 문장 구조가
달라지면서 정규식/Claude 추출기가 포착하는 Entity 개수 자체가 달라지는
문제가 발견되었다 (예: Formal Style의 완전한 문장형 표현을 정규식이
포착하지 못함). 이는 Style 간 비교의 공정성을 훼손하므로, Gold Standard를
Content Scaffold(생성 시점의 구조화된 임상 정보, Style 무관)로 대체한다.

Content Scaffold는 이미 구조화되어 있으므로 "추출"이 아니라 "포맷 변환"이다.
closed_vocab_extractor / open_vocab_extractor와 동일한 출력 형태로 맞춘다.

[v3 변경 - docs/taxonomy_audit.md 대응]
독립적으로 정립한 CCER Operational Taxonomy(§5) 및 파이프라인 전체 alignment
audit(§8) 결과에 따라, scaffold_to_open_vocab()에 medication_identity/
intake_output 두 필드를 신규 매핑한다. scaffold_to_closed_vocab()은 device/
oxygen_support 처리가 이미 taxonomy와 정합함이 확인되어(§8.2) 변경하지 않는다.
"""


def scaffold_to_closed_vocab(scaffold: dict) -> dict:
    """
    closed_vocab_extractor.extract_closed_vocab_entities()와 동일한 형태로 변환.
    """
    result = {"route": [], "frequency": [], "device": [], "vital_sign": [], "dose": []}

    med = scaffold.get("medication")
    if med:
        result["route"].append({
            "raw": med["route"], "normalized": med["route"].lower(), "position": 0
        })
        if med.get("frequency"):
            result["frequency"].append({
                "raw": med["frequency"], "normalized": med["frequency"].lower(), "position": 0
            })
        result["dose"].append({
            "raw": med["dose"],
            "value": "".join(c for c in med["dose"] if c.isdigit() or c == "."),
            "unit": "".join(c for c in med["dose"] if c.isalpha()).lower(),
            "position": 0
        })

    device = scaffold.get("device")
    if device:
        result["device"].append({
            "raw": device, "normalized": device.lower(), "position": 0
        })

    # oxygen_support -> device(nc)로 취급 (Style Controller가 NC/ventilator 등으로 표현하는 원본 정보)
    oxygen = scaffold.get("oxygen_support")
    if oxygen:
        result["device"].append({
            "raw": oxygen, "normalized": "nc", "position": 0
        })

    vs = scaffold.get("vital_signs", {})
    label_map = {"BP": "bp", "HR": "hr", "RR": "rr", "BT": "bt", "SpO2": "spo2"}
    for key, label in label_map.items():
        if key in vs:
            value = vs[key].rstrip(".")
            result["vital_sign"].append({
                "raw": f"{key} {value}", "label": label, "value": value, "position": 0
            })

    return result


def scaffold_to_open_vocab(scaffold: dict) -> dict:
    """
    open_vocab_extractor.extract_open_vocab_entities()와 동일한 형태로 변환.

    [v3 변경 - docs/taxonomy_audit.md §5, §8 대응]
    확정된 CCER Operational Taxonomy(11개 카테고리)에 따라 두 필드를 신규
    매핑한다. 이전에는 scaffold["medication"]["name"](약물 정체)과
    scaffold["io"](intake/output)가 Gold 쪽 어디에도 대응하는 entity_type이
    없어, Whisper가 이 정보를 정확히 전사해도 항상 whisper_only(hallucination)
    로 오분류되거나(io), 아예 오류 탐지 자체가 불가능했다(medication.name).

    - medication_identity: "무엇을 투여했는가"라는 약물 정체성. dose/route/
      frequency(투여 속성)와는 별도 정보 축이라는 FHIR MedicationRequest의
      medicationCodeableConcept ≠ dosageInstruction 구조를 근거로 분리했다.
    - intake_output: 체액 섭취/배설 관측값. intervention(Procedure)과는 다른
      관측 축(Observable entity)이라는 FHIR/SNOMED CT 근거로 별도 카테고리로
      신설했으며, intervention에 편입시키지 않았다.

    둘 다 단일값 open-vocab 필드로, clinical_status/notification과 동일한
    처리 패턴을 따른다 (symptoms/interventions처럼 리스트가 아님).
    """
    symptoms = []
    symptom = scaffold.get("symptom")
    if symptom:
        symptoms.append({
            "name": symptom["name"],
            "negation": symptom["negation"],
            "severity": symptom.get("severity")
        })

    interventions = []
    if scaffold.get("intervention"):
        interventions.append(scaffold["intervention"])

    med = scaffold.get("medication")
    medication_identity = med.get("name") if med else None

    return {
        "symptoms": symptoms,
        "clinical_status": scaffold.get("clinical_status"),
        "medication_identity": medication_identity,
        "interventions": interventions,
        "intake_output": scaffold.get("io"),
        "notification": scaffold.get("notification")
    }