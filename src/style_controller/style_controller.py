"""
Style Controller (논문 3.6절)

[설계 원칙]
이 모듈은 텍스트를 직접 생성하지 않는다.
GPT-4o에게 전달할 스타일별 프롬프트를 구성하는 역할만 한다.

Documentation Generation 단계의 정보 보존은 Prompt Constraint를 통해
보장하는 것으로 가정하며, 별도의 정량적 평가는 수행하지 않는다.
(Entity-level 평가는 이후 Whisper STT Transcript를 대상으로 수행한다.)

[추적성(Traceability)]
각 스타일의 규칙은 docs/reference_analysis.md 에 근거한다.
아래 'source' 필드는 GPT-4o에게 전달되지 않는다 — 연구 재현성 문서화
(README, 부록) 목적으로만 코드에 남겨둔다.

[프롬프트 설계 원칙]
- GPT-4o가 이해할 수 없는 연구 내부 개념(예: CCER)은 프롬프트에 넣지 않는다.
  "왜"가 아니라 "무엇을 해야 하는가"만 규칙으로 남긴다.
- 예시는 반드시 Reference Analysis에서 실제로 확인된 패턴 범위 안에서만 사용한다.
  Reference 밖의 어휘(예: 확인되지 않은 약어)를 예시로 넣지 않는다.
- 프롬프트가 다루는 범위는 현재 Content Scaffold Schema와 정확히 일치시킨다
  (Schema에 없는 필드 종류를 프롬프트에서 언급하지 않는다).

실제 간호기록 텍스트 생성은 전적으로 GPT-4o가 수행한다.
"""

import json

STYLE_DEFINITIONS = {
    "formal_template": {
        "label": "Formal Template Style",
        "source": "docs/reference_analysis.md Category 2 - SBAR Situation/Background pattern",
        "rules": [
            "Use complete Korean sentences with appropriate subjects and particles (조사) — do not omit them.",
            "Use descriptive narrative sentence endings (e.g. '호흡곤란을 호소하였다', '산소포화도가 88%로 확인되었다').",
            "Prefer full clinical terms over abbreviations whenever natural.",
            "Maintain clear logical flow between clinical facts.",
            "Do not unnecessarily compress information.",
            "Represent every clinical fact contained in the Content Scaffold."
        ]
    },

    "clinical_charting": {
        "label": "Clinical Charting Style",
        "source": "docs/reference_analysis.md Category 2 - SBAR Assessment pattern",
        "rules": [
            "Use concise Korean-English mixed charting expressions.",
            "Represent ONE clinical fact per line whenever possible.",
            "Prioritize numerical observations over narrative explanation.",
            "Minor omission of subjects and particles (조사) is acceptable if meaning remains clear.",
            "Use charting-style verb endings (e.g. '호소함', '확인됨', '적용함', '유지함').",
            "Use standard clinical abbreviations naturally.",
            "Prefer concise documentation over complete grammatical sentences.",
            "Represent every clinical fact contained in the Content Scaffold."
        ]
    },

    "telegraphic_icu": {
        "label": "Telegraphic ICU Style",
        "source": "docs/reference_analysis.md Category 2 - SBAR emergency/urgent pattern",
        "rules": [
            "Produce the shortest documentation that still preserves all clinical information.",
            "Represent ONE clinical fact per line.",
            "Omit subjects whenever possible (e.g. '환자 SpO2 88% 확인됨' -> 'SpO2 88%.').",
            "Omit particles (조사) whenever possible.",
            "Omit verbs when the meaning remains unambiguous (e.g. 'Morphine 2mg IV 투여함' -> 'Morphine 2mg IV.').",
            "Prioritize numeric values and short clinical fragments over narrative wording.",
            "Aggressively use standard ICU abbreviations that appear in the Reference abbreviation list.",
            "Represent every clinical fact contained in the Content Scaffold."
        ]
    }
}

CODE_SWITCHING_RULE = """
Entity-conditioned Clinical Code-switching (applies to ALL styles)

General narrative and documentation expressions:
- Korean

Clinical entities:
- Symptoms
- Diagnoses
- Medication names
- Routes
- Devices
- Vital sign labels

-> Prefer English or standard clinical abbreviations.

Numeric values:
- Use numerals.

Units:
- Use standard English units (mg, mL, cc, L/min, mmHg, bpm, %, etc.).

Language choice should be determined by the clinical entity type,
not by arbitrary code-switching.
"""

NOTIFICATION_RULE = """
Notification Rule

If the Content Scaffold contains a Notification field,
express it appropriately for the selected documentation style.

Formal:
- complete recommendation/report sentence
  (e.g. '담당 의사에게 보고하였다.')

Clinical Charting:
- concise physician notification
  (e.g. '담당의 notify함.')

Telegraphic:
- minimal physician notification expression
  (e.g. 'Dr notify.')

Do not invent recommendations that are not present in the Content Scaffold.
"""

NEGATION_SEVERITY_RULE = """
Negation and Severity Rule

If symptom.negation is true:
- Explicitly and unambiguously indicate that the symptom is ABSENT or DENIED,
  even in the most compressed style.
- Do not phrase it in a way that could be misread as the symptom being present.

If symptom.severity is provided (mild / moderate / severe):
- Reflect the severity level explicitly, using a term or qualifier
  appropriate to the current style.
- Do not upgrade or downgrade the severity implied by the Content Scaffold.

These fields must never be omitted, even in the most compressed style.
"""

MEDICATION_EXPRESSION_RULE = """
Medication Expression Rule

Treat medication name, dose, route, and frequency as components of a
single clinical event.

If a component is present in the Content Scaffold, preserve it exactly.
Never substitute, paraphrase, or infer a missing component.
If frequency is null, omit it rather than inventing one.

Medication name, dose, route and frequency
should appear as one coherent medication event
whenever present.
"""


def build_generation_prompt(scaffold: dict, style_key: str):
    """
    Content Scaffold와 스타일 정의를 조합하여 GPT-4o에 전달할
    (system_prompt, user_prompt) 튜플을 반환한다.
    """
    if style_key not in STYLE_DEFINITIONS:
        raise ValueError(f"Unknown style_key: {style_key}")

    style = STYLE_DEFINITIONS[style_key]
    rules_text = "\n".join(f"- {rule}" for rule in style["rules"])

    system_prompt = f"""
You are generating ONE Korean ICU nursing documentation note.

Documentation Style: {style['label']}

Style Rules:
{rules_text}

{CODE_SWITCHING_RULE}

{NOTIFICATION_RULE}

{NEGATION_SEVERITY_RULE}

{MEDICATION_EXPRESSION_RULE}

Requirements

- Preserve ALL clinical facts contained in the Content Scaffold.
- Preserve the clinical meaning of every entity.
  Do not change, add, or remove clinical information.
- Never omit any entity, including negated symptoms.
- Never alter numerical values.
- Never invent new clinical information.
- If a Content Scaffold field is null, omit the corresponding statement
  naturally. Do not generate placeholder text (e.g. do not write
  something equivalent to "no notification" when notification is null).
- Follow the requested documentation style consistently.
- Output ONLY the nursing documentation.
- Do NOT output JSON.
- Do NOT output explanations.
"""

    user_prompt = f"""
Content Scaffold (JSON)

{json.dumps(scaffold, ensure_ascii=False, indent=2)}
"""

    return system_prompt, user_prompt


def get_all_style_keys() -> list[str]:
    return list(STYLE_DEFINITIONS.keys())


def get_reference_sources() -> dict:
    """연구 문서화(README, 부록)용 헬퍼. GPT-4o 프롬프트에는 사용되지 않는다."""
    return {key: val["source"] for key, val in STYLE_DEFINITIONS.items()}