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

    return {
        "symptoms": symptoms,
        "clinical_status": scaffold.get("clinical_status"),
        "interventions": interventions,
        "notification": scaffold.get("notification")
    }