"""
Entity Matching - Open-vocabulary Semantic Matching 

Symptom, Clinical Status, Intervention, Notification은 표현이 자유로워
규칙 기반으로 매칭할 수 없다. Claude에게 Gold/Whisper 목록을 동시에 보여주고
의미 기반 매칭을 수행한다.

[Design Principle - differs from extraction step]
Entity Extraction 단계에서는 Gold/Whisper를 서로 모르게 독립적으로
추출했지만, 이 단계는 애초에 "비교"가 목적이므로 두 목록을 함께 제공한다.
"""

import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MATCH_TOOL = {
    "name": "record_semantic_matches",
    "description": "Record how Gold entities correspond to Whisper entities based on clinical meaning.",
    "input_schema": {
        "type": "object",
        "required": [
            "symptom_matches", "whisper_only_symptoms",
            "clinical_status_match",
            "intervention_matches", "whisper_only_interventions",
            "notification_match"
        ],
        "properties": {
            "symptom_matches": {
                "type": "array",
                "description": "One entry for EVERY gold symptom, even if no match was found (omission).",
                "items": {
                    "type": "object",
                    "required": ["gold_value", "whisper_value", "match_basis", "negation_match", "severity_match"],
                    "properties": {
                        "gold_value": {"type": "string"},
                        "whisper_value": {"type": ["string", "null"]},
                        "match_basis": {
                            "type": "string",
                            "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "omission"]
                        },
                        "negation_match": {
                            "type": ["boolean", "null"],
                            "description": "True if negation status agrees. Null if match_basis is omission or phonetic_artifact."
                        },
                        "severity_match": {
                            "type": ["boolean", "null"],
                            "description": "True if severity agrees or both are null. Null if match_basis is omission or phonetic_artifact."
                        }
                    }
                }
            },
            "whisper_only_symptoms": {
                "type": "array",
                "description": "Whisper symptoms with no corresponding gold symptom.",
                "items": {"type": "string"}
            },
            "clinical_status_match": {
                "type": "object",
                "required": ["gold_value", "whisper_value", "match_basis"],
                "properties": {
                    "gold_value": {"type": ["string", "null"]},
                    "whisper_value": {"type": ["string", "null"]},
                    "match_basis": {
                        "type": "string",
                        "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "omission", "whisper_only", "both_null"]
                    }
                }
            },
            "intervention_matches": {
                "type": "array",
                "description": "One entry for EVERY gold intervention, even if omitted.",
                "items": {
                    "type": "object",
                    "required": ["gold_value", "whisper_value", "match_basis"],
                    "properties": {
                        "gold_value": {"type": "string"},
                        "whisper_value": {"type": ["string", "null"]},
                        "match_basis": {
                            "type": "string",
                            "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "omission"]
                        }
                    }
                }
            },
            "whisper_only_interventions": {
                "type": "array",
                "items": {"type": "string"}
            },
            "notification_match": {
                "type": "object",
                "required": ["gold_value", "whisper_value", "match_basis"],
                "properties": {
                    "gold_value": {"type": ["string", "null"]},
                    "whisper_value": {"type": ["string", "null"]},
                    "match_basis": {
                        "type": "string",
                        "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "omission", "whisper_only", "both_null"]
                    }
                }
            }
        }
    }
}

SYSTEM_PROMPT = """You compare a Gold entity list against a Whisper entity list extracted from the same
clinical scenario, and determine which Gold entities were preserved.

Rules:
- Every Gold symptom and every Gold intervention MUST appear once in the output list, even when no
  Whisper counterpart exists (in that case whisper_value is null and match_basis is "omission").
- A "semantic" match means the two expressions refer to the same clinical concept even though the
  wording differs (e.g. "dyspnea" and "호흡곤란" both mean shortness of breath). Only mark semantic
  match when you are confident they refer to the same real-world clinical concept — do not force a
  match just because it's the only remaining unmatched item.
- Do NOT match two entities just because they co-occur in the same clinical scenario. Match based on
  actual shared clinical meaning only.
- CRITICAL — distinguish real semantic paraphrase from phonetic transliteration noise. Whisper
  sometimes mishears an English/loanword clinical term and outputs a Korean string that sounds
  similar when read aloud but is NOT itself a real word or clinical term (e.g. Gold "chest pain"
  transcribed by Whisper as "체스파인" — this is not a Korean word and conveys no clinical meaning
  on its own; it is a phonetic echo of the English syllables, not a translation of the concept).
  Ask yourself: "if a Korean-speaking nurse read only the Whisper string, with no access to the Gold
  text, would they understand which clinical concept it refers to?" If yes (it is a real clinical
  term or common paraphrase) -> "semantic". If no (it is meaningless or nonsensical on its own, even
  though it happens to sound like the Gold term) -> "phonetic_artifact". Do NOT use "semantic" just
  because the Whisper string is phonetically close to the Gold term.
  - Example (semantic, correct): Gold "dyspnea" vs Whisper "호흡곤란" -> "semantic". Both are real,
    independently meaningful clinical expressions for shortness of breath.
  - Example (phonetic_artifact, NOT semantic): Gold "chest pain" vs Whisper "체스파인" ->
    "phonetic_artifact". "체스파인" is not a Korean clinical term or any recognizable word; a reader
    given only "체스파인" could not identify chest pain from it.
  - Example (phonetic_artifact, NOT semantic): Gold "sepsis" vs Whisper "셉시스" is borderline —
    if "셉시스" is used as an actual (if nonstandard) transliteration that a clinician would
    recognize as referring to sepsis, treat it as "semantic"; if the string is garbled beyond
    recognition (e.g. "셋 있어" from mishearing), use "phonetic_artifact".
- negation_match / severity_match reflect whether those attributes agree between the matched pair.
  Set them to null when match_basis is "omission" or "phonetic_artifact" (the clinical concept was
  not intelligibly preserved, so negation/severity cannot be judged).
- If gold_value is null (no notification/clinical_status in Gold) and whisper_value is also null,
  use match_basis "both_null". If Whisper has a value but Gold does not, use "whisper_only".
- Report Whisper symptoms/interventions with no Gold counterpart in the whisper_only_* lists.

Use the record_semantic_matches tool to report your findings."""


def build_user_message(gold_entities: dict, whisper_entities: dict) -> str:
    import json
    return f"""Gold entities:
{json.dumps(gold_entities, ensure_ascii=False, indent=2)}

Whisper entities:
{json.dumps(whisper_entities, ensure_ascii=False, indent=2)}"""


def match_open_vocab(client, model, gold_entities: dict, whisper_entities: dict) -> dict:
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=[MATCH_TOOL],
        tool_choice={"type": "tool", "name": "record_semantic_matches"},
        messages=[
            {"role": "user", "content": build_user_message(gold_entities, whisper_entities)}
        ]
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_semantic_matches":
            return block.input

    raise RuntimeError("Claude가 tool_use 블록을 반환하지 않음")


def is_valid_match_result(result: dict) -> bool:
    """Content Scaffold 때와 동일한 목적의 구조 검증 (중첩 JSON-as-string 등 방지)."""
    if not isinstance(result, dict):
        return False

    required_keys = [
        "symptom_matches", "whisper_only_symptoms",
        "clinical_status_match",
        "intervention_matches", "whisper_only_interventions",
        "notification_match"
    ]
    if not all(k in result for k in required_keys):
        return False

    if not isinstance(result["symptom_matches"], list):
        return False
    for m in result["symptom_matches"]:
        if not isinstance(m, dict) or "gold_value" not in m or "match_basis" not in m:
            return False

    if not isinstance(result["intervention_matches"], list):
        return False
    for m in result["intervention_matches"]:
        if not isinstance(m, dict) or "gold_value" not in m or "match_basis" not in m:
            return False

    if not isinstance(result["clinical_status_match"], dict):
        return False
    if not isinstance(result["notification_match"], dict):
        return False

    return True