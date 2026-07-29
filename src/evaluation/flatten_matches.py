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

[v2 변경 - limitations.md #6 대응]
match_status가 "whisper_only"인 레코드(Gold에는 없고 Whisper 전사에만 존재하는
entity = 환각성 삽입)는 이전에는 error_type=None으로 남아 CCER 집계
(Counter(error_type ...))에서 완전히 제외되었다. v2부터는 이 레코드에
error_type="hallucination"을 부여하여 CCER 공식에서 penalize한다
(가중치는 src/evaluation/ccer_eval.py의 ERROR_WEIGHTS 참조).

[v2 변경 - limitations.md #5 대응]
open_vocab_matches의 match_basis에 "phonetic_artifact"가 추가되었다
(src/matching/semantic_matcher.py 참조). Whisper가 음차 전사로 인해
임상적 의미 없는 문자열을 생성한 경우로, 평가 관점에서는 정보가 실질적으로
보존되지 않은 것이므로 "omission"과 동일하게 취급한다. 다만 원본 매칭
데이터(*_matched.json)에는 "phonetic_artifact"로 구분 기록되어, 이후 분석에서
"진짜 semantic match"와 "음차 오판정을 바로잡은 사례"를 구분 집계할 수 있다.

[Known Limitation - 유지]
clinical_status_match / notification_match 스키마는 "값이 존재하지만 서로
다른 경우(예: alert vs drowsy)"에 대한 명시적 오류 카테고리가 없다. 이 경우
Claude가 match_basis를 semantic으로 잘못 넣을 위험이 있으며, 이는 스키마
설계의 한계로 README에 명시한다.
"""

# omission과 동일하게 취급하는 match_basis 값들.
# "omission": Gold에 있었지만 Whisper에서 아예 누락됨
# "phonetic_artifact": Whisper 전사가 존재하긴 하나 음차 잡음일 뿐 임상적 의미를
#   전달하지 못하므로, 정보 보존 관점에서는 omission과 동등하게 처리한다.
OMISSION_EQUIVALENT_BASES = ("omission", "phonetic_artifact")


def flatten_closed_vocab(closed_matches: list) -> list:
    """entity_matcher.py 결과를 그대로 사용하되, whisper_only에 error_type을 채운다.

    entity_matcher.py는 매칭 로직에만 집중하도록 error_type=None으로 남겨두고,
    CCER 관점의 의미 부여(= hallucination penalty)는 이 함수에서 담당한다.
    """
    records = []
    for r in closed_matches:
        r = dict(r)
        if r["match_status"] == "whisper_only" and r["error_type"] is None:
            r["error_type"] = "hallucination"
        records.append(r)
    return records


def flatten_open_vocab(open_matches: dict) -> list:
    records = []

    # symptoms: negation/severity 불일치를 error_type으로 변환
    for m in open_matches.get("symptom_matches", []):
        if m["match_basis"] in OMISSION_EQUIVALENT_BASES:
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
            "match_status": "whisper_only", "error_type": "hallucination"
        })

    # interventions
    for m in open_matches.get("intervention_matches", []):
        if m["match_basis"] in OMISSION_EQUIVALENT_BASES:
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
            "match_status": "whisper_only", "error_type": "hallucination"
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
        elif basis in OMISSION_EQUIVALENT_BASES:
            records.append({
                "entity_type": entity_type,
                "gold_value": m["gold_value"], "whisper_value": None,
                "match_status": "omission", "error_type": "omission"
            })
        elif basis == "whisper_only":
            records.append({
                "entity_type": entity_type,
                "gold_value": None, "whisper_value": m["whisper_value"],
                "match_status": "whisper_only", "error_type": "hallucination"
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