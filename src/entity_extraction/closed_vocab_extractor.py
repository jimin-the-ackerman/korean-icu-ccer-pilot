"""
Closed-vocabulary Entity Extraction

Dictionary/정규식 기반 규칙 추출.
Dictionary 출처: docs/reference_analysis.md Category 3 (Clinical Abbreviation Lists)

추출과 동시에 정규화(normalization)를 수행한다 — 표기 변이(대소문자, 첨자 SpO2/SpO₂ 등)를
흡수하여 이후 Entity Matching 단계를 단순화하기 위함이다.

지원 Entity Type: route, frequency, vital_sign, device, dose
"""

import re

ROUTE_DICT = {
    "IV": "iv", "PO": "po", "IM": "im",
    "SC": "sc", "SUBQ": "sc", "SL": "sl", "PR": "pr"
}

FREQUENCY_DICT = {
    "BID": "bid", "TID": "tid", "QID": "qid",
    "PRN": "prn", "STAT": "stat"
}

FREQUENCY_QH_PATTERN = re.compile(r"\bq(\d+)h\b", re.IGNORECASE)

DEVICE_PATTERNS = [
    (re.compile(r"\bfoley\b", re.IGNORECASE), "foley"),
    (re.compile(r"\bc-line\b", re.IGNORECASE), "c-line"),
    (re.compile(r"\bventilator\b", re.IGNORECASE), "ventilator"),
    (re.compile(r"\bng\s*tube\b", re.IGNORECASE), "ng tube"),
    (re.compile(r"\b(high-?flow\s*)?nasal\s*cannula\b", re.IGNORECASE), "nc"),
    (re.compile(r"\bnc\b", re.IGNORECASE), "nc"),
]

VITAL_SIGN_PATTERN = re.compile(
    r"\b(BP|HR|RR|BT|SpO2|SpO₂|SAT)\b[:\s]*([\d./%]+)",
    re.IGNORECASE
)

VITAL_SIGN_LABEL_MAP = {
    "bp": "bp", "hr": "hr", "rr": "rr", "bt": "bt",
    "spo2": "spo2", "spo₂": "spo2", "sat": "spo2"
}

DOSE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mg|mL|ml|cc|g|mcg|L/min|l/min)\b",
    re.IGNORECASE
)


def extract_route(text: str) -> list[dict]:
    results = []
    for raw_key, normalized in ROUTE_DICT.items():
        for m in re.finditer(rf"\b{re.escape(raw_key)}\b", text, re.IGNORECASE):
            results.append({
                "raw": m.group(0),
                "normalized": normalized,
                "position": m.start()
            })
    return results


def extract_frequency(text: str) -> list[dict]:
    results = []
    for raw_key, normalized in FREQUENCY_DICT.items():
        for m in re.finditer(rf"\b{re.escape(raw_key)}\b", text, re.IGNORECASE):
            results.append({
                "raw": m.group(0),
                "normalized": normalized,
                "position": m.start()
            })
    for m in FREQUENCY_QH_PATTERN.finditer(text):
        results.append({
            "raw": m.group(0),
            "normalized": f"q{m.group(1)}h",
            "position": m.start()
        })
    return results


def extract_device(text: str) -> list[dict]:
    results = []
    for pattern, normalized in DEVICE_PATTERNS:
        for m in pattern.finditer(text):
            results.append({
                "raw": m.group(0),
                "normalized": normalized,
                "position": m.start()
            })
    return results


def extract_vital_sign(text: str) -> list[dict]:
    results = []
    for m in VITAL_SIGN_PATTERN.finditer(text):
        label_raw = m.group(1)
        value_raw = m.group(2)
        normalized_label = VITAL_SIGN_LABEL_MAP.get(label_raw.lower(), label_raw.lower())
        results.append({
            "raw": m.group(0),
            "label": normalized_label,
            "value": value_raw,
            "position": m.start()
        })
    return results


def extract_dose(text: str) -> list[dict]:
    results = []
    for m in DOSE_PATTERN.finditer(text):
        value, unit = m.group(1), m.group(2)
        results.append({
            "raw": m.group(0),
            "value": value,
            "unit": unit.lower(),
            "position": m.start()
        })
    return results


def extract_closed_vocab_entities(text: str) -> dict:
    """텍스트 하나에서 모든 closed-vocabulary entity type을 추출."""
    return {
        "route": extract_route(text),
        "frequency": extract_frequency(text),
        "device": extract_device(text),
        "vital_sign": extract_vital_sign(text),
        "dose": extract_dose(text)
    }