"""
Closed-vocabulary Entity Extraction

Dictionary/정규식 기반 규칙 추출.
Dictionary 출처: docs/reference_analysis.md Category 3 (Clinical Abbreviation Lists)

추출과 동시에 정규화(normalization)를 수행한다 — 표기 변이(대소문자, 첨자 SpO2/SpO₂ 등)를
흡수하여 이후 Entity Matching 단계를 단순화하기 위함이다.

지원 Entity Type: route, frequency, vital_sign, device, dose

[v4 변경 - docs/v4_style_invariant_extraction_spec.md 대응]
기존 정규식은 영어 약어/단어만 인식해, Formal Template처럼 clinical entity
label을 한국어 완전 표기로 렌더링하는 스타일에서 vital_sign/route/
frequency/device가 구조적으로 omission 처리되는 문제가 있었다(스타일
설계 문서 `style_controller.py`의 CODE_SWITCHING_RULE과 Formal Template
고유 규칙 간 충돌에서 기인, 100개 데이터 실측: Formal Template의 영어
약어 부재율 vital_sign 100%/route 87%/frequency 92%/device 88%).

이번 변경으로 각 entity type은 "surface form → canonical concept/value →
비교"의 3단계로 분리되며, 한국어 전체 표기·영어 전체 표기·일부 관행적
음차(v4 spec §3.6)까지 인식하도록 확장했다. 매칭 로직(entity_matcher.py)은
이미 canonical 값(label/normalized)만 놓고 비교하는 구조라 변경하지
않는다 — 이 파일만 canonical 값 공간으로 정규화하는 surface form 커버리지를
넓히는 역할을 한다.

`dose`는 추가로 entity ownership hierarchy(v4 spec §3.5)를 적용한다:
문맥 무관하게 숫자+단위만 잡던 기존 방식이 vital_sign(BP가 STT로 뭉개진
경우)/intake_output 값을 dose로 오인하는 문제가 있었다(한계 #10).
"medication_dose = 특정 약물의 투여량"이라는 ownership 정의를 기준으로,
(1) 더 구체적인 소유권(vital_sign/io/범용 수액)을 가진 값을 먼저 배제하고
(2) 남은 후보만 medication-administration context(route/frequency/투약
동사 — ownership의 정의가 아니라 그 문맥을 추정하는 deterministic proxy)
로 재확인한다. 절/구두점 경계는 이 확인의 보조 파싱 수단일 뿐이다.
"""

import re

# ============================================================
# route
# ============================================================
# v4: 영어 약어/전체표기 + 한국어 전체표기 + 관행적 음차(아이비)를 canonical
# 값(iv/po/im/sc/sl/pr)으로 정규화. "정맥"은 §3.2에서 100개 데이터 실증
# 스캔 결과(42건 중 29%가 route가 아닌 device/symptom) 확인한 대로,
# 접미사(으로/주사/내/수액)가 있을 때만 인정하고 관/류가 바로 붙으면 제외.
ROUTE_PATTERNS = [
    (re.compile(r"\bIV\b", re.IGNORECASE), "iv"),
    (re.compile(r"\bPO\b", re.IGNORECASE), "po"),
    (re.compile(r"\bIM\b", re.IGNORECASE), "im"),
    (re.compile(r"\b(SC|SUBQ)\b", re.IGNORECASE), "sc"),
    (re.compile(r"\bSL\b", re.IGNORECASE), "sl"),
    (re.compile(r"\bPR\b", re.IGNORECASE), "pr"),
    (re.compile(r"\bintravenous(ly)?\b", re.IGNORECASE), "iv"),
    (re.compile(r"\b(oral(ly)?|per\s*os)\b", re.IGNORECASE), "po"),
    (re.compile(r"\bintramuscular(ly)?\b", re.IGNORECASE), "im"),
    (re.compile(r"\bsubcutaneous(ly)?\b", re.IGNORECASE), "sc"),
    (re.compile(r"\bsublingual(ly)?\b", re.IGNORECASE), "sl"),
    (re.compile(r"\b(rectal(ly)?|per\s*rectum)\b", re.IGNORECASE), "pr"),
    # 관행적 음차 (v4 spec §3.6: conventional abbreviation pronunciation)
    (re.compile(r"아이비"), "iv"),
    # 한국어 전체 표기 - "정맥"은 관/류가 바로 뒤따르면 제외, 접미사 필수
    (re.compile(r"정맥(?!관|류)\s*(?:으로|주사(?:로)?|내|수액)"), "iv"),
    (re.compile(r"경구(?:로)?"), "po"),
    (re.compile(r"근육(?:주사)?(?:으로)?"), "im"),
    (re.compile(r"피하(?:주사)?(?:로)?"), "sc"),
    (re.compile(r"설하(?:로)?"), "sl"),
    (re.compile(r"직장(?:으로)?"), "pr"),
]

# ============================================================
# frequency
# ============================================================
FREQUENCY_PATTERNS = [
    (re.compile(r"\bBID\b", re.IGNORECASE), "bid"),
    (re.compile(r"\bTID\b", re.IGNORECASE), "tid"),
    (re.compile(r"\bQID\b", re.IGNORECASE), "qid"),
    (re.compile(r"\bPRN\b", re.IGNORECASE), "prn"),
    (re.compile(r"\bSTAT\b", re.IGNORECASE), "stat"),
    (re.compile(r"\btwice\s*daily\b", re.IGNORECASE), "bid"),
    (re.compile(r"\bthree\s*times\s*daily\b", re.IGNORECASE), "tid"),
    (re.compile(r"\bfour\s*times\s*daily\b", re.IGNORECASE), "qid"),
    (re.compile(r"\bas\s*needed\b", re.IGNORECASE), "prn"),
    (re.compile(r"\bimmediately\b", re.IGNORECASE), "stat"),
    # 관행적 음차 (v4 spec §3.6: conventional clinical spoken form)
    (re.compile(r"스탯"), "stat"),
    # 한국어 전체 표기
    (re.compile(r"하루\s*(?:에)?\s*2\s*(?:회|번)"), "bid"),
    (re.compile(r"하루\s*(?:에)?\s*3\s*(?:회|번)"), "tid"),
    (re.compile(r"하루\s*(?:에)?\s*4\s*(?:회|번)"), "qid"),
    (re.compile(r"필요\s*시|필요할\s*때"), "prn"),
    (re.compile(r"즉시"), "stat"),
]

# q{N}h: 값(N)이 있는 유일한 frequency 패턴 -> 별도 값 파싱 필요 (v4 spec §4)
FREQUENCY_QH_PATTERN = re.compile(r"\bq[\s-]?(\d+)\s*h\b", re.IGNORECASE)
FREQUENCY_QH_KOREAN_PATTERN = re.compile(r"(?:매\s*)?(\d+)\s*시간마다")
FREQUENCY_QH_ENGLISH_FULL_PATTERN = re.compile(r"\bevery\s*(\d+)\s*hours?\b", re.IGNORECASE)

# ============================================================
# device
# ============================================================
DEVICE_PATTERNS = [
    (re.compile(r"\bfoley(\s*catheter)?\b", re.IGNORECASE), "foley"),
    (re.compile(r"\b(c-line|central\s*line)\b", re.IGNORECASE), "c-line"),
    (re.compile(r"\bventilator\b", re.IGNORECASE), "ventilator"),
    (re.compile(r"\b(ng\s*tube|nasogastric\s*tube)\b", re.IGNORECASE), "ng tube"),
    (re.compile(r"\b(high-?flow\s*)?nasal\s*cannula\b", re.IGNORECASE), "nc"),
    (re.compile(r"\bnc\b", re.IGNORECASE), "nc"),
    # 한국어 전체 표기
    (re.compile(r"폴리\s*카테터|유치도뇨관"), "foley"),
    (re.compile(r"중심정맥관"), "c-line"),
    (re.compile(r"인공호흡기"), "ventilator"),
    (re.compile(r"비위관"), "ng tube"),
    (re.compile(r"비강\s*캐뉼라"), "nc"),
]

# ============================================================
# vital_sign
# ============================================================
# 라벨(canonical key)과 값을 분리 처리. 라벨 후보를 먼저 찾고, 그 직후
# (구두점/조사 허용)에 오는 숫자를 값으로 파싱한다.
VITAL_SIGN_LABEL_PATTERNS = [
    (re.compile(r"\bBP\b", re.IGNORECASE), "bp"),
    (re.compile(r"\bHR\b", re.IGNORECASE), "hr"),
    (re.compile(r"\bRR\b", re.IGNORECASE), "rr"),
    (re.compile(r"\bBT\b", re.IGNORECASE), "bt"),
    (re.compile(r"\b(SpO2|SpO₂|SAT)\b", re.IGNORECASE), "spo2"),
    (re.compile(r"\bblood\s*pressure\b", re.IGNORECASE), "bp"),
    (re.compile(r"\b(heart\s*rate|pulse)\b", re.IGNORECASE), "hr"),
    (re.compile(r"\b(respiratory\s*rate|respiration)\b", re.IGNORECASE), "rr"),
    (re.compile(r"\b(body\s*temperature|temperature)\b", re.IGNORECASE), "bt"),
    (re.compile(r"\boxygen\s*saturation\b", re.IGNORECASE), "spo2"),
    # 한국어 전체 표기
    (re.compile(r"혈압"), "bp"),
    (re.compile(r"심박수|맥박"), "hr"),
    # "호흡"만 단독으로 쓰이면 호흡곤란(symptom)/호흡 상태(intervention)와
    # 충돌 위험이 있어(v4 spec §5.2), 호흡수를 우선 매칭하고 단독 "호흡"은
    # 곤란/상태가 바로 뒤따르지 않을 때만 인정
    (re.compile(r"호흡수"), "rr"),
    (re.compile(r"호흡(?!\s*곤란|\s*상태)"), "rr"),
    (re.compile(r"체온"), "bt"),
    (re.compile(r"산소포화도"), "spo2"),
]

# 라벨 뒤 값 사이에 올 수 있는 구분자(콜론/공백/조사)
_VALUE_GAP = r"[:\s]*(?:은|는|이|가)?[:\s]*"
VITAL_SIGN_VALUE_PATTERN = re.compile(rf"^{_VALUE_GAP}([\d./%]+)")

# ============================================================
# dose (entity ownership hierarchy 적용 - v4 spec §3.5)
# ============================================================
DOSE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mg|mL|ml|cc|g|mcg|L/min|l/min)\b",
    re.IGNORECASE
)

# 2b단계: intake/output 어휘 (있으면 dose 후보에서 제외)
IO_VOCAB_PATTERN = re.compile(
    r"urine|output|intake|소변량|섭취량|배설량|drain|배액량",
    re.IGNORECASE
)

# 2b단계: 범용 수액 명칭 denylist (v4 spec §3.5.1 - medication_dose 아니라
# intervention 소관으로 이미 확정됨)
FLUID_VOLUME_DENYLIST = re.compile(
    r"IV\s*fluids|\bNS\b|normal\s*saline|D5W|\bLR\b|수액",
    re.IGNORECASE
)

# 3단계: medication-administration context proxy (ownership의 정의가 아니라
# 그 문맥을 추정하는 deterministic 수단 - v4 spec §3.5)
ADMIN_VERB_PATTERN = re.compile(
    r"투여|주입|복용|처방|적용|administer|given",
    re.IGNORECASE
)

# 4단계: 절 경계 - 숫자 사이의 소수점(예: "0.3mg")은 절 경계로 오인하지 않음
CLAUSE_BOUNDARY_PATTERN = re.compile(r"(?<!\d)[.\n](?!\d)")

# 4단계 fallback 반경 (절 경계 자체를 못 찾는 run-on 텍스트에서만 사용,
# primary 판정 기준이 아님 - v4 spec §3.5)
RUNON_CLAUSE_LEN_THRESHOLD = 250
FALLBACK_WINDOW = 120


def extract_route(text: str) -> list[dict]:
    results = []
    for pattern, normalized in ROUTE_PATTERNS:
        for m in pattern.finditer(text):
            results.append({
                "raw": m.group(0),
                "normalized": normalized,
                "position": m.start()
            })
    return results


def extract_frequency(text: str) -> list[dict]:
    results = []
    for pattern, normalized in FREQUENCY_PATTERNS:
        for m in pattern.finditer(text):
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
    for m in FREQUENCY_QH_KOREAN_PATTERN.finditer(text):
        results.append({
            "raw": m.group(0),
            "normalized": f"q{m.group(1)}h",
            "position": m.start()
        })
    for m in FREQUENCY_QH_ENGLISH_FULL_PATTERN.finditer(text):
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
    for pattern, normalized_label in VITAL_SIGN_LABEL_PATTERNS:
        for m in pattern.finditer(text):
            after = text[m.end():m.end() + 20]
            value_match = VITAL_SIGN_VALUE_PATTERN.match(after)
            if not value_match:
                continue
            value_raw = value_match.group(1).rstrip(".")
            results.append({
                "raw": text[m.start():m.end() + value_match.end()],
                "label": normalized_label,
                "value": value_raw,
                "position": m.start()
            })
    return results


def _clause_bounds(text: str, pos: int) -> tuple:
    """pos가 속한 절의 (시작, 끝, run-on 여부)를 반환.
    run-on 여부는 해당 절이 비정상적으로 길 때(구두점 소실 등) True."""
    boundaries = [0] + [m.end() for m in CLAUSE_BOUNDARY_PATTERN.finditer(text)] + [len(text)]
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        if start <= pos < end:
            is_runon = (end - start) > RUNON_CLAUSE_LEN_THRESHOLD
            return start, end, is_runon
    return 0, len(text), True


def extract_dose(text: str, vital_sign_matches: list, route_matches: list,
                  frequency_matches: list) -> list[dict]:
    """
    Entity ownership hierarchy (v4 spec §3.5):
    1단계: 숫자+단위 후보 탐지
    2단계: 더 구체적인 소유권(vital_sign/io/fluid volume)을 가진 값 배제
    3단계: 남은 후보만 medication-administration context(proxy) 확인
    4단계: 절 경계는 3단계 판정의 보조 파싱 수단(run-on 시에만 fallback)
    """
    results = []
    vital_sign_spans = [
        (vs["position"], vs["position"] + len(vs["raw"])) for vs in vital_sign_matches
    ]

    for m in DOSE_PATTERN.finditer(text):
        pos = m.start()
        value, unit = m.group(1), m.group(2)

        # 2a: vital_sign이 이미 이 숫자를 소유하면 dose 후보에서 제외
        if any(start <= pos < end for start, end in vital_sign_spans):
            continue

        # 2b: 부피 단위 + io 어휘/범용 수액 denylist -> 제외
        if unit.lower() in ("ml", "l", "cc"):
            local_ctx = text[max(0, pos - 40):pos + 40]
            if IO_VOCAB_PATTERN.search(local_ctx) or FLUID_VOLUME_DENYLIST.search(local_ctx):
                continue

        # 3단계: 같은 절 안에 route/frequency/투약동사 신호가 있는지 확인
        clause_start, clause_end, is_runon = _clause_bounds(text, pos)

        def _in_clause(items, cs=clause_start, ce=clause_end):
            return any(cs <= it["position"] < ce for it in items)

        has_signal = (
            _in_clause(route_matches) or
            _in_clause(frequency_matches) or
            bool(ADMIN_VERB_PATTERN.search(text[clause_start:clause_end]))
        )

        # 4단계: 절 경계를 못 찾는(run-on) 경우에만 넓은 반경으로 재확인(fallback)
        if not has_signal and is_runon:
            lo, hi = max(0, pos - FALLBACK_WINDOW), pos + FALLBACK_WINDOW
            has_signal = (
                any(lo <= r["position"] < hi for r in route_matches) or
                any(lo <= f["position"] < hi for f in frequency_matches) or
                bool(ADMIN_VERB_PATTERN.search(text[lo:hi]))
            )

        if not has_signal:
            continue

        results.append({
            "raw": m.group(0),
            "value": value,
            "unit": unit.lower(),
            "position": pos
        })
    return results


def extract_closed_vocab_entities(text: str) -> dict:
    """텍스트 하나에서 모든 closed-vocabulary entity type을 추출."""
    route = extract_route(text)
    frequency = extract_frequency(text)
    device = extract_device(text)
    vital_sign = extract_vital_sign(text)
    dose = extract_dose(text, vital_sign, route, frequency)
    return {
        "route": route,
        "frequency": frequency,
        "device": device,
        "vital_sign": vital_sign,
        "dose": dose
    }
