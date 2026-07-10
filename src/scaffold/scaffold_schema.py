"""
Content Scaffold JSON Schema (paper Section 3.3)

Reference basis (docs/reference_analysis.md):
- Category 1 (Standard Forms) -> field structure
- Category 2 (SBAR examples)  -> Notification field justification
- Category 3 (Abbreviation Lists) -> route/frequency vocabulary constraints

This schema defines WHAT information must exist in a Content Scaffold.
It does NOT generate any values — GPT-4o generates values that must
validate against this schema.
"""

CONTENT_SCAFFOLD_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ContentScaffold",
    "type": "object",
    "required": [
        "scenario_id",
        "patient_context",
        "vital_signs",
        "symptom",
        "clinical_status"
    ],
    "properties": {
        "scenario_id": {
            "type": "string",
            "pattern": "^scenario_[0-9]{3}$",
            "description": "Unique identifier, e.g. scenario_001"
        },
        "patient_context": {
            "type": "string",
            "description": "Brief patient background (age, sex, diagnosis, admission reason)"
        },
        "vital_signs": {
            "type": "object",
            "required": ["BP", "HR", "RR", "BT", "SpO2"],
            "properties": {
                "BP": {"type": "string", "description": "e.g. '130/80'"},
                "HR": {"type": "string", "description": "e.g. '118'"},
                "RR": {"type": "string", "description": "e.g. '26'"},
                "BT": {"type": "string", "description": "e.g. '37.2'"},
                "SpO2": {"type": "string", "description": "e.g. '88%'"}
            }
        },
        "symptom": {
            "type": "object",
            "required": ["name", "negation"],
            "properties": {
                "name": {"type": "string", "description": "e.g. 'dyspnea'"},
                "negation": {"type": "boolean", "description": "True if symptom explicitly denied"},
                "severity": {
                    "type": ["string", "null"],
                    "enum": ["mild", "moderate", "severe", None]
                }
            }
        },
        "medication": {
            "type": ["object", "null"],
            "properties": {
                "name": {"type": "string"},
                "dose": {"type": "string"},
                "route": {
                    "type": "string",
                    "enum": ["IV", "PO", "IM", "SC", "SL", "PR"],
                    "description": "Constrained to Reference Analysis abbreviation list"
                },
                "frequency": {
                    "type": ["string", "null"],
                    "enum": ["BID", "TID", "QID", "PRN", "STAT", "q4h", "q6h", "q8h", "q12h", None]
                }
            }
        },
        "oxygen_support": {
            "type": ["string", "null"],
            "description": "e.g. 'O2 2L NC'"
        },
        "intervention": {
            "type": ["string", "null"]
        },
        "device": {
            "type": ["string", "null"],
            "enum": ["Foley", "C-line", "ventilator", "NG tube", None]
        },
        "io": {
            "type": ["string", "null"],
            "description": "e.g. 'urine 500cc'"
        },
        "clinical_status": {
            "type": "string",
            "enum": ["alert", "drowsy", "stuporous", "unresponsive"]
        },
        "notification": {
            "type": ["string", "null"],
            "description": "e.g. 'Dr notify' - justified by SBAR Recommendation section (Reference Analysis category 2)"
        }
    }
}


def get_schema() -> dict:
    """Content Scaffold Schema 반환. 검증/GPT-4o Prompt 양쪽에서 재사용."""
    return CONTENT_SCAFFOLD_SCHEMA