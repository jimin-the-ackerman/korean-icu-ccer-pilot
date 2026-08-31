"""
Entity Matching - Open-vocabulary Semantic Matching 

Symptom, Clinical Status, Intervention, Notification은 표현이 자유로워
규칙 기반으로 매칭할 수 없다. Claude에게 Gold/Whisper 목록을 동시에 보여주고
의미 기반 매칭을 수행한다.

[Design Principle - differs from extraction step]
Entity Extraction 단계에서는 Gold/Whisper를 서로 모르게 독립적으로
추출했지만, 이 단계는 애초에 "비교"가 목적이므로 두 목록을 함께 제공한다.

[v3 변경 - docs/taxonomy_audit.md §5, §8 대응]
medication_identity_match, intake_output_match을 clinical_status_match와
동형 구조로 신설했다. 동시에 "value_substitution"이라는 match_basis를 4개
단일값 필드(clinical_status/medication_identity/intake_output/notification)
공통으로 신설하여, 기존 flatten_matches.py의 Known Limitation("값이 둘 다
있는데 서로 다른 경우를 표현할 방법이 없다")을 해소했다.

medication_identity는 다른 필드보다 훨씬 엄격한 semantic 판정 기준을 요구한다
— LASA(Look-Alike, Sound-Alike) 약물 오인은 ISMP가 별도로 관리할 만큼
잘 알려진 고위험 오류 유형이므로, 철자·발음이 비슷하다는 이유만으로
semantic 처리하면 실제 약물 오인 오류를 은폐하게 된다. 프롬프트에 긍정
사례(Ceftriaxone/Cephtriaxone, 실제 v3 spot-check에서 발견된 STT 철자
오류)와 부정 사례(Hydralazine/Hydroxyzine, ISMP 공식 LASA 목록에 등재된
쌍)를 모두 명시했다.
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
            "medication_identity_match",
            "intervention_matches", "whisper_only_interventions",
            "intake_output_match",
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
                        "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "value_substitution", "omission", "whisper_only", "both_null"]
                    }
                }
            },
            "medication_identity_match": {
                "type": "object",
                "description": "Match for the identity of the medication mentioned (which drug it is) — "
                               "NOT its dose/route/frequency, those are matched separately elsewhere.",
                "required": ["gold_value", "whisper_value", "match_basis"],
                "properties": {
                    "gold_value": {"type": ["string", "null"]},
                    "whisper_value": {"type": ["string", "null"]},
                    "match_basis": {
                        "type": "string",
                        "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "value_substitution", "omission", "whisper_only", "both_null"]
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
            "intake_output_match": {
                "type": "object",
                "description": "Match for intake/output or fluid-balance observations (e.g. urine output, "
                               "fluid balance).",
                "required": ["gold_value", "whisper_value", "match_basis"],
                "properties": {
                    "gold_value": {"type": ["string", "null"]},
                    "whisper_value": {"type": ["string", "null"]},
                    "match_basis": {
                        "type": "string",
                        "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "value_substitution", "omission", "whisper_only", "both_null"]
                    }
                }
            },
            "notification_match": {
                "type": "object",
                "required": ["gold_value", "whisper_value", "match_basis"],
                "properties": {
                    "gold_value": {"type": ["string", "null"]},
                    "whisper_value": {"type": ["string", "null"]},
                    "match_basis": {
                        "type": "string",
                        "enum": ["exact", "normalized", "semantic", "phonetic_artifact", "value_substitution", "omission", "whisper_only", "both_null"]
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
- If gold_value is null (no notification/clinical_status/medication_identity/intake_output in Gold)
  and whisper_value is also null, use match_basis "both_null". If Whisper has a value but Gold does
  not, use "whisper_only".
- Report Whisper symptoms/interventions with no Gold counterpart in the whisper_only_* lists.

Rule for "value_substitution" (applies to clinical_status_match, medication_identity_match,
intake_output_match, notification_match — the single-value fields):
- Use "value_substitution" when BOTH gold_value and whisper_value are non-null, and the two values
  are genuinely DIFFERENT real-world facts — not a wording variant of the same fact (that would be
  "semantic"/"exact"/"normalized") and not meaningless noise (that would be "phonetic_artifact").
  Example: Gold clinical_status "alert" vs Whisper "drowsy" — these are two different real clinical
  states, not a paraphrase of each other -> "value_substitution".

CRITICAL — medication_identity requires stricter judgment than other fields (patient safety):
For "medication_identity_match" specifically, apply a MUCH stricter bar for "semantic" than you
would for symptoms or other free text. This is because look-alike/sound-alike (LASA) medication
name confusion is a well-documented, high-severity category of real-world medication error (see
e.g. the ISMP List of Confused Drug Names) — two DIFFERENT real drugs can have very similar
spelling or pronunciation, and treating that similarity as a "semantic match" would silently hide
a genuine drug-substitution error.
- Mark "semantic" ONLY when you are confident the Whisper string clearly refers to the SAME
  medication identity as Gold — e.g. it is an STT spelling/transcription artifact of the same drug
  name (letters swapped, a sound-alike misspelling), a brand vs. generic name for the same drug, or
  an abbreviation of the same drug. The bar is: "this is unmistakably the same drug, just written
  differently."
- Mark "value_substitution" whenever the Whisper string could plausibly name a DIFFERENT real drug
  from Gold — even if the spelling or pronunciation is close. Similarity of spelling/sound is NOT
  sufficient evidence of a match for medication identity; when in doubt between "semantic" and
  "value_substitution" for a medication, prefer "value_substitution" (a missed true match is a much
  smaller risk than silently hiding a real drug-substitution error).
  - Example (semantic, correct): Gold "Ceftriaxone" vs Whisper "Cephtriaxone" -> "semantic". This is
    an STT spelling artifact (the "f" and "ph" sounds are identical in English pronunciation) of the
    unmistakably same antibiotic name — there is no other real drug this could plausibly refer to.
  - Example (value_substitution, NOT semantic, even though the names look/sound alike): Gold
    "Hydralazine" (an antihypertensive) vs Whisper "Hydroxyzine" (an antihistamine/anxiolytic) ->
    "value_substitution", NOT "semantic". These are two well-documented LASA (look-alike,
    sound-alike) drugs on the ISMP confused-drug-names list that are frequently mixed up in real
    clinical practice — despite the similar spelling, they are different real medications with
    different clinical uses, so conflating them would hide a genuine and dangerous identity error.

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
        "medication_identity_match",
        "intervention_matches", "whisper_only_interventions",
        "intake_output_match",
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
    if not isinstance(result["medication_identity_match"], dict):
        return False
    if not isinstance(result["intake_output_match"], dict):
        return False
    if not isinstance(result["notification_match"], dict):
        return False

    return True