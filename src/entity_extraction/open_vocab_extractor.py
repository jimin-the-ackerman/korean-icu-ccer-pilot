"""
Open-vocabulary Entity Extraction

[Design Principle]
Claude는 Gold Transcript와 Whisper Transcript 각각에서 독립적으로,
텍스트에 실제로 나타난 임상 정보만 추출한다. 두 텍스트를 비교하거나
어느 쪽이 정답인지 판단하지 않는다 

Structured Output은 Anthropic Tool Use로 강제한다.

[v3 변경 - docs/taxonomy_audit.md §5, §8 대응]
확정된 CCER Operational Taxonomy에 따라 두 필드를 신설(medication_identity,
intake_output)하고, `interventions`의 범위를 명확히 좁혔다. 기존에는
`interventions`가 "투약 제외"라고만 되어 있어 device/oxygen_support/io 관련
언급을 폭넓게 흡수했고, 이것이 taxonomy_audit.md §3.3에서 확인된 duplicated
concept 문제(device·oxygen_support가 closed-vocab과 interventions 양쪽에
중복 추출됨)의 원인이었다. SYSTEM_PROMPT에 device/의료기기/intake-output을
명시적으로 제외하는 체크리스트와 실제 파일럿 데이터 기반 반례를 추가했다.
"""

import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

EXTRACTION_TOOL = {
    "name": "record_clinical_entities",
    "description": "Record the clinical entities that literally appear in the given nursing documentation text.",
    "input_schema": {
        "type": "object",
        "required": ["symptoms", "clinical_status", "medication_identity",
                     "interventions", "intake_output", "notification"],
        "properties": {
            "symptoms": {
                "type": "array",
                "description": "All symptoms explicitly mentioned in the text, whether present or negated.",
                "items": {
                    "type": "object",
                    "required": ["name", "negation"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Symptom name as it appears or its clinical equivalent, e.g. 'dyspnea'."
                        },
                        "negation": {
                            "type": "boolean",
                            "description": "True if the text explicitly denies or negates this symptom."
                        },
                        "severity": {
                            "type": ["string", "null"],
                            "enum": ["mild", "moderate", "severe", None],
                            "description": "Severity if explicitly stated or clearly implied, otherwise null."
                        }
                    }
                }
            },
            "clinical_status": {
                "type": ["string", "null"],
                "description": "Patient's consciousness/clinical status if mentioned, e.g. 'alert', 'drowsy'. Null if not mentioned."
            },
            "medication_identity": {
                "type": ["string", "null"],
                "description": "The IDENTITY of a medication mentioned (i.e. which drug it is, e.g. 'Ceftriaxone', "
                               "'morphine') — not its dose, route, or frequency. Report the drug name only, even if "
                               "the text also mentions its dose/route/frequency separately. Null if no medication "
                               "name is mentioned."
            },
            "interventions": {
                "type": "array",
                "description": "Clinical interventions or procedures explicitly mentioned, EXCLUDING all of the "
                               "following (each is captured elsewhere, do not duplicate them here): "
                               "(1) medication administration or any medication name/dose/route/frequency, "
                               "(2) use of a respiratory/oxygen-support device (ventilator, nasal cannula, oxygen "
                               "mask, etc.) or any other physical medical device (Foley catheter, C-line, NG tube, "
                               "etc.) — these are devices, not interventions, "
                               "(3) intake/output or fluid-balance observations (urine output, fluid balance, etc.). "
                               "Only report genuinely distinct procedures/actions here, e.g. 'fluid resuscitation', "
                               "'cardiac monitoring', 'wound dressing change'.",
                "items": {"type": "string"}
            },
            "intake_output": {
                "type": ["string", "null"],
                "description": "Intake/output or fluid-balance observation if mentioned, e.g. 'urine output 200 mL "
                               "over 4 hours', 'negative fluid balance'. Null if not mentioned."
            },
            "notification": {
                "type": ["string", "null"],
                "description": "Physician/staff notification statement if mentioned, otherwise null."
            }
        }
    }
}

SYSTEM_PROMPT = """You extract clinical entities that are literally present in a single piece of Korean ICU nursing documentation text.

CRITICAL RULE - Verbatim extraction only:
- Extract ONLY entities that are explicitly named or written in the text, using the words actually present.
- If the text contains garbled, distorted, or nonsensical fragments (e.g. transcription errors), do NOT guess
  what the original word "probably was" and do NOT silently correct it into a clinically plausible term.
  If a fragment is unintelligible, simply do not report an entity for it.
- Do NOT infer a symptom or diagnosis from a numeric value alone. For example, a low SpO2 number by itself
  is NOT evidence that "hypoxia" was mentioned as a symptom — only report it if the word/concept is actually
  stated in the text.
- Do NOT add clinical knowledge, diagnoses, or symptoms that a clinician might plausibly infer from context.
  Your job is transcription-level extraction, not clinical reasoning.
- Do NOT compare this text against any other text, and do NOT assume this text is correct or complete.

Concrete counter-example (do NOT do this):
- Text contains a garbled phrase with no recognizable symptom word, but the text separately mentions a
  diagnosis like "pneumonia" and a low oxygen number. INCORRECT behavior: inferring and adding "dyspnea" or
  "hypoxia" as symptoms because they would clinically make sense together. CORRECT behavior: do not report
  those symptoms unless the words/concepts literally appear in the text.

CRITICAL RULE - Category boundaries (each real-world fact belongs to exactly ONE field):
Several categories can superficially look like "interventions" but must be reported in their own dedicated
field instead, never duplicated into `interventions`. Use this checklist before adding anything to
`interventions`:
- Is it a medication (name, dose, route, or frequency)? -> `medication_identity` (name only), never `interventions`.
- Is it the use of a physical device — a ventilator, nasal cannula, oxygen mask, Foley catheter, C-line,
  NG tube, or any other respiratory-support or indwelling device? -> this belongs to a separate closed-vocabulary
  device category that is handled elsewhere in the pipeline, NOT to `interventions`. Do not report device usage
  as an intervention.
- Is it an intake/output or fluid-balance observation (urine output, fluid balance, drain output, etc.)?
  -> `intake_output`, never `interventions`.
- Only if none of the above apply — e.g. "fluid resuscitation", "cardiac monitoring", "wound dressing change",
  "repositioning" — does it belong in `interventions`.

Worked examples:
- "Ventilator 사용 중" -> NOT an intervention (device usage). Do not add to `interventions`.
- "High-flow nasal cannula 산소 지원 유지함" -> NOT an intervention (device/oxygen-support usage). Do not add to `interventions`.
- "Ceftriaxone 1g IV q12h 적용함" -> medication_identity: "Ceftriaxone" (the name only). Not an intervention.
- "Urine output 200 mL over 4 hours 확인됨" -> intake_output: "urine output 200 mL over 4 hours". Not an intervention.
- "Fluid resuscitation 시행함" -> interventions: ["fluid resuscitation"]. This is a genuine procedure, not a device/medication/io fact.

If a category has no information literally present in the text, return an empty list or null as appropriate.
Use the record_clinical_entities tool to report your findings."""


def extract_open_vocab_entities(client, model, text):
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_clinical_entities"},
        messages=[
            {"role": "user", "content": f"Nursing documentation text:\n\n{text}"}
        ]
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_clinical_entities":
            return block.input

    raise RuntimeError("Claude가 tool_use 블록을 반환하지 않음")

def repair_nested_json_string(result: dict) -> dict:
    """
    Claude가 드물게 필드 값 자리에 전체 JSON을 문자열로 중첩시키는 경우를 복구.
    예: result["symptoms"]가 리스트가 아니라 '{"symptoms": [...]}' 형태의 문자열로 온 경우.
    """
    import json as json_module

    if isinstance(result.get("symptoms"), str):
        try:
            parsed = json_module.loads(result["symptoms"])
            if isinstance(parsed, dict) and "symptoms" in parsed:
                result["symptoms"] = parsed["symptoms"]
            elif isinstance(parsed, list):
                result["symptoms"] = parsed
        except (json_module.JSONDecodeError, TypeError):
            pass

    return result