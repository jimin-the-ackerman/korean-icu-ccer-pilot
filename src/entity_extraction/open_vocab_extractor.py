"""
Open-vocabulary Entity Extraction

[Design Principle]
Claude는 Gold Transcript와 Whisper Transcript 각각에서 독립적으로,
텍스트에 실제로 나타난 임상 정보만 추출한다. 두 텍스트를 비교하거나
어느 쪽이 정답인지 판단하지 않는다 

Structured Output은 Anthropic Tool Use로 강제한다.
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
        "required": ["symptoms", "clinical_status", "interventions", "notification"],
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
            "interventions": {
                "type": "array",
                "description": "Clinical interventions or procedures explicitly mentioned (excluding medication administration).",
                "items": {"type": "string"}
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