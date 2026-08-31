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

[v3 변경 - docs/taxonomy_audit.md §5, §8 대응]
아래 두 가지를 동시에 반영했다:
1. medication_identity_match, intake_output_match을 신규 처리 대상에 추가
   (scaffold_as_gold.py / open_vocab_extractor.py / semantic_matcher.py에서
   신설된 카테고리와 짝을 맞춤).
2. 과거 "Known Limitation"으로 남아있던 문제 — clinical_status_match /
   notification_match 스키마에 "값이 존재하지만 서로 다른 경우(예: alert vs
   drowsy)"를 표현할 방법이 없던 것 — 를 semantic_matcher.py에 신설한
   "value_substitution" match_basis로 해소했다. 이 하나의 match_basis를
   4개 단일값 필드(clinical_status/medication_identity/intake_output/
   notification) 공통으로 적용하되, entity_type에 따라 다른 error_type으로
   매핑한다(VALUE_SUBSTITUTION_ERROR_TYPE) — medication_identity만 최상위
   위험군으로 별도 error_type("medication_identity_error")을 가지며, 근거는
   ccer_eval.py의 Methodological Note(LASA 약물 오인 위험) 참고.
"""

# omission과 동일하게 취급하는 match_basis 값들.
# "omission": Gold에 있었지만 Whisper에서 아예 누락됨
# "phonetic_artifact": Whisper 전사가 존재하긴 하나 음차 잡음일 뿐 임상적 의미를
#   전달하지 못하므로, 정보 보존 관점에서는 omission과 동등하게 처리한다.
OMISSION_EQUIVALENT_BASES = ("omission", "phonetic_artifact")

# "value_substitution"(Gold/Whisper 양쪽에 값이 있으나 서로 다른 실제 값인 경우,
# 예: alert vs drowsy) 발생 시 entity_type별로 다른 error_type을 부여한다.
# medication_identity만 최상위 위험군으로 별도 error_type을 갖고, 명시되지
# 않은 나머지(clinical_status/intake_output/notification)는 기존 "substitution"을
# 그대로 쓴다 (docs/taxonomy_audit.md §5.3 참고).
VALUE_SUBSTITUTION_ERROR_TYPE = {
    "medication_identity": "medication_identity_error",
}


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

    # clinical_status, medication_identity, intake_output, notification (single-value fields)
    #
    # [v3 변경 - docs/taxonomy_audit.md §5.3, §8 대응]
    # medication_identity_match, intake_output_match을 신규로 처리 대상에 포함한다.
    # 동시에 "value_substitution"(Gold/Whisper 양쪽에 값이 있으나 서로 다른 실제
    # 값인 경우, 예: alert vs drowsy)을 entity_type별로 다른 error_type에 매핑한다
    # (VALUE_SUBSTITUTION_ERROR_TYPE 참고). 이전까지는 이 케이스 자체를 표현할
    # 방법이 없다는 Known Limitation이었으나 이번 변경으로 해소되었다.
    for field_name, entity_type in [("clinical_status_match", "clinical_status"),
                                     ("medication_identity_match", "medication_identity"),
                                     ("intake_output_match", "intake_output"),
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
        elif basis == "value_substitution":
            error_type = VALUE_SUBSTITUTION_ERROR_TYPE.get(entity_type, "substitution")
            records.append({
                "entity_type": entity_type,
                "gold_value": m["gold_value"], "whisper_value": m["whisper_value"],
                "match_status": "error", "error_type": error_type
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