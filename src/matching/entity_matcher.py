"""
Entity Matching - Closed-vocabulary 

Route/Frequency/Device/Dose/Vital Sign은 이미 정규화된 값이 있으므로
규칙 기반(문자열/값 비교)으로 매칭한다. Claude 호출이 필요 없다.

[Note]
이 모듈은 매칭 로직(무엇이 matched/omission/whisper_only인지 판정)에만
집중한다. 'whisper_only'로 판정된 항목은 여기서는 error_type=None으로
남겨두며, CCER 관점의 페널티 부여(error_type="hallucination")는
src/evaluation/flatten_matches.py에서 일괄 처리한다 (v2, limitations.md #6 대응).

Multiset 매칭 후, 특정 entity_type에서 omission 1건과 whisper_only 1건이
동시에 남으면 이를 substitution(치환)으로 재해석한다 (예: route가 IV에서
PO로 바뀐 경우). 이는 파일럿 규모(entity 개수가 적음)에서 유효한 휴리스틱이며,
대규모 데이터에서는 더 정교한 정렬(alignment) 알고리즘이 필요할 수 있다.
"""

ENTITY_TYPE_ERROR_MAP = {
    "route": "route_error",
    "frequency": "frequency_error",
    "device": "device_error"
}


def match_value_list(gold_items: list, whisper_items: list, entity_type: str) -> list:
    """Route, Frequency, Device처럼 단순 값 목록인 entity_type에 대한 매칭."""
    gold_vals = [item["normalized"] for item in gold_items]
    whisper_vals_remaining = [item["normalized"] for item in whisper_items]

    matched = []
    omissions = []

    for val in gold_vals:
        if val in whisper_vals_remaining:
            whisper_vals_remaining.remove(val)
            matched.append({
                "entity_type": entity_type,
                "gold_value": val,
                "whisper_value": val,
                "match_status": "matched",
                "error_type": None
            })
        else:
            omissions.append(val)

    whisper_only = whisper_vals_remaining

    results = list(matched)

    # substitution 휴리스틱: omission 1건 + whisper_only 1건이면 치환으로 재해석
    if len(omissions) == 1 and len(whisper_only) == 1:
        results.append({
            "entity_type": entity_type,
            "gold_value": omissions[0],
            "whisper_value": whisper_only[0],
            "match_status": "error",
            "error_type": ENTITY_TYPE_ERROR_MAP.get(entity_type, "substitution")
        })
    else:
        for val in omissions:
            results.append({
                "entity_type": entity_type,
                "gold_value": val,
                "whisper_value": None,
                "match_status": "omission",
                "error_type": "omission"
            })
        for val in whisper_only:
            results.append({
                "entity_type": entity_type,
                "gold_value": None,
                "whisper_value": val,
                "match_status": "whisper_only",
                "error_type": None  # flatten_matches.py에서 "hallucination"으로 채워짐
            })

    return results


def match_dose(gold_items: list, whisper_items: list) -> list:
    """Dose는 (value, unit) 쌍으로 매칭. 값/단위 중 무엇이 달랐는지 구분."""
    gold_pairs = [(item["value"], item["unit"]) for item in gold_items]
    whisper_pairs_remaining = [(item["value"], item["unit"]) for item in whisper_items]

    matched = []
    omissions = []

    for pair in gold_pairs:
        if pair in whisper_pairs_remaining:
            whisper_pairs_remaining.remove(pair)
            matched.append({
                "entity_type": "dose",
                "gold_value": f"{pair[0]}{pair[1]}",
                "whisper_value": f"{pair[0]}{pair[1]}",
                "match_status": "matched",
                "error_type": None
            })
        else:
            omissions.append(pair)

    whisper_only = whisper_pairs_remaining
    results = list(matched)

    if len(omissions) == 1 and len(whisper_only) == 1:
        g_val, g_unit = omissions[0]
        w_val, w_unit = whisper_only[0]
        if g_val != w_val:
            error_type = "numeric_error"
        elif g_unit != w_unit:
            error_type = "unit_error"
        else:
            error_type = "substitution"
        results.append({
            "entity_type": "dose",
            "gold_value": f"{g_val}{g_unit}",
            "whisper_value": f"{w_val}{w_unit}",
            "match_status": "error",
            "error_type": error_type
        })
    else:
        for val, unit in omissions:
            results.append({
                "entity_type": "dose",
                "gold_value": f"{val}{unit}",
                "whisper_value": None,
                "match_status": "omission",
                "error_type": "omission"
            })
        for val, unit in whisper_only:
            results.append({
                "entity_type": "dose",
                "gold_value": None,
                "whisper_value": f"{val}{unit}",
                "match_status": "whisper_only",
                "error_type": None
            })

    return results


def match_vital_signs(gold_items: list, whisper_items: list) -> list:
    """Vital Sign은 label(bp, hr, rr, bt, spo2)을 key로 매칭."""
    gold_by_label = {}
    for item in gold_items:
        gold_by_label.setdefault(item["label"], []).append(item["value"])

    whisper_by_label = {}
    for item in whisper_items:
        whisper_by_label.setdefault(item["label"], []).append(item["value"])

    results = []
    checked_labels = set()

    for label, gold_values in gold_by_label.items():
        checked_labels.add(label)
        gold_value = gold_values[0]

        if label in whisper_by_label:
            whisper_value = whisper_by_label[label][0]
            if gold_value == whisper_value:
                results.append({
                    "entity_type": "vital_sign", "label": label,
                    "gold_value": gold_value, "whisper_value": whisper_value,
                    "match_status": "matched", "error_type": None
                })
            else:
                results.append({
                    "entity_type": "vital_sign", "label": label,
                    "gold_value": gold_value, "whisper_value": whisper_value,
                    "match_status": "error", "error_type": "numeric_error"
                })
        else:
            results.append({
                "entity_type": "vital_sign", "label": label,
                "gold_value": gold_value, "whisper_value": None,
                "match_status": "omission", "error_type": "omission"
            })

    for label, whisper_values in whisper_by_label.items():
        if label not in checked_labels:
            results.append({
                "entity_type": "vital_sign", "label": label,
                "gold_value": None, "whisper_value": whisper_values[0],
                "match_status": "whisper_only", "error_type": None
            })

    return results


def match_closed_vocab(gold_entities: dict, whisper_entities: dict) -> list:
    """Closed-vocabulary entity 전체(route/frequency/device/dose/vital_sign)에 대해 매칭 수행."""
    results = []
    results += match_value_list(gold_entities["route"], whisper_entities["route"], "route")
    results += match_value_list(gold_entities["frequency"], whisper_entities["frequency"], "frequency")
    results += match_value_list(gold_entities["device"], whisper_entities["device"], "device")
    results += match_dose(gold_entities["dose"], whisper_entities["dose"])
    results += match_vital_signs(gold_entities["vital_sign"], whisper_entities["vital_sign"])
    return results