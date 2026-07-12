"""
Matched 결과 통합 변환

closed_vocab_matches와 open_vocab_matches는 저장 구조가 다르므로,
Entity-level Evaluation과 CCER 양쪽에서 재사용 가능한 단일 레코드 형태로 변환한다.

통일된 레코드 형태:
{
  "entity_type": str,
  "gold_value": str | None,
  "whisper_value": str | None,
  "match_status": "matched" | "error" | "omission" | "whisper_only",
  "error_type": str | None
}

[Known Limitation]
open_vocab_matches의 clinical_status_match / notification_match 스키마는
"omission / whisper_only / both_null / (exact/normalized/semantic=matched)"만
구분하며, "값이 존재하지만 서로 다른 경우(예: alert vs drowsy)"에 대한
명시적 오류 카테고리가 없다. 이 경우 Claude가 match_basis를 semantic으로
잘못 넣을 위험이 있으며, 이는 스키마 설계의 한계로 README에 명시한다.
"""


def flatten_closed_vocab(closed_matches: list) -> list:
    """이미 통일된 형태이므로 그대로 반환."""
    return list(closed_matches)


def flatten_open_vocab(open_matches: dict) -> list:
    records = []

    # symptoms: negation/severity 불일치를 error_type으로 변환
    for m in open_matches.get("symptom_matches", []):
        if m["match_basis"] == "omission":
            records.append({
                "entity_type": "symptom",
                "gold_value": m["gold_value"], "whisper_value": None,
                "match_status": "omission", "error_type": "omission"
            })
        elif m.get("negation_match") is False:
            records.append({
                "entity_type": "symptom",
                "gold_value": m["gold_value"], "whisper_value": m["whisper_value"],
                "match_status": "error", "error_type": "negation_flip"
            })
        elif m.get("severity_match") is False:
            records.append({
                "entity_type": "symptom",
                "gold_value": m["gold_value"], "whisper_value": m["whisper_value"],
                "match_status": "error", "error_type": "severity_shift"
            })
        else:
            records.append({
                "entity_type": "symptom",
                "gold_value": m["gold_value"], "whisper_value": m["whisper_value"],
                "match_status": "matched", "error_type": None
            })

    for s in open_matches.get("whisper_only_symptoms", []):
        records.append({
            "entity_type": "symptom",
            "gold_value": None, "whisper_value": s,
            "match_status": "whisper_only", "error_type": None
        })

    # interventions
    for m in open_matches.get("intervention_matches", []):
        if m["match_basis"] == "omission":
            records.append({
                "entity_type": "intervention",
                "gold_value": m["gold_value"], "whisper_value": None,
                "match_status": "omission", "error_type": "omission"
            })
        else:
            records.append({
                "entity_type": "intervention",
                "gold_value": m["gold_value"], "whisper_value": m["whisper_value"],
                "match_status": "matched", "error_type": None
            })

    for s in open_matches.get("whisper_only_interventions", []):
        records.append({
            "entity_type": "intervention",
            "gold_value": None, "whisper_value": s,
            "match_status": "whisper_only", "error_type": None
        })

    # clinical_status, notification (single-value fields)
    for field_name, entity_type in [("clinical_status_match", "clinical_status"),
                                     ("notification_match", "notification")]:
        m = open_matches.get(field_name)
        if not m:
            continue
        basis = m["match_basis"]
        if basis == "both_null":
            continue  # 애초에 정보가 없었던 경우, 집계 대상 아님
        elif basis == "omission":
            records.append({
                "entity_type": entity_type,
                "gold_value": m["gold_value"], "whisper_value": None,
                "match_status": "omission", "error_type": "omission"
            })
        elif basis == "whisper_only":
            records.append({
                "entity_type": entity_type,
                "gold_value": None, "whisper_value": m["whisper_value"],
                "match_status": "whisper_only", "error_type": None
            })
        else:  # exact, normalized, semantic
            records.append({
                "entity_type": entity_type,
                "gold_value": m["gold_value"], "whisper_value": m["whisper_value"],
                "match_status": "matched", "error_type": None
            })

    return records


def flatten_all_matches(matched_data: dict) -> list:
    """closed + open vocab 결과를 하나의 레코드 리스트로 통합."""
    records = []
    records += flatten_closed_vocab(matched_data.get("closed_vocab_matches", []))
    records += flatten_open_vocab(matched_data.get("open_vocab_matches", {}))
    return records