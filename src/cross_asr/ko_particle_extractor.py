"""
S1 closed-vocab extractor: v4 + Korean particle attachment (post hoc evaluator sensitivity analysis,
docs/cross_asr_spec.md Section 13). The v4 extractor remains the primary evaluator.

What changes (and nothing else):
    In the v4 module src/entity_extraction/closed_vocab_extractor.py, exactly the 41 patterns whose
    source ends with the word boundary \\b (ASCII route / frequency / device / vital-sign labels /
    dose) get that final \\b replaced by
        (?:\\b|(?=(?:PARTICLE)(?:\\s|[PUNCT]|\\Z)))
    i.e. every v4 match is kept, and an ASCII token followed directly by one of the listed Korean
    particles is also accepted - only when the particle itself is followed by whitespace, listed
    punctuation or the end of the text ("IV로 투여", "2g을, ", "C-line이다." ; not "IV로ABC",
    "IV로123", "40mg을test", "IV주사", "IVIG", "IB로").
What does not change:
    leading boundaries, Korean patterns, value / unit parsing and canonical values, the dose ownership
    hierarchy, matching (entity_matcher), flattening, weights, gold scaffold, open-vocab (LLM) results.

The v4 module is not edited: its function code objects are re-bound to a copy of its namespace in
which only those 41 pattern objects are replaced. v4 itself keeps returning v4 results.
"""
import re
import types

import src.entity_extraction.closed_vocab_extractor as v4

PARTICLES = ("으로써", "으로", "에서", "에게", "까지", "부터", "이며", "이고", "이다", "이나", "이라",
             "라고", "마다", "와", "과", "을", "를", "이", "가", "은", "는", "의", "에", "로", "도", "만", "씩")
PUNCT = r".,;:!?)\]}\"'/·…"
PARTICLE_ALT = "|".join(sorted(PARTICLES, key=lambda p: (-len(p), p)))     # longest first
TRAIL = rf"(?:\b|(?=(?:{PARTICLE_ALT})(?:\s|[{PUNCT}]|\Z)))"
EXPECTED_PATCHED = 41

PATTERN_GROUPS = ["ROUTE_PATTERNS", "FREQUENCY_PATTERNS", "DEVICE_PATTERNS", "VITAL_SIGN_LABEL_PATTERNS"]
SINGLE_PATTERNS = ["FREQUENCY_QH_PATTERN", "FREQUENCY_QH_KOREAN_PATTERN",
                   "FREQUENCY_QH_ENGLISH_FULL_PATTERN", "DOSE_PATTERN"]


def _patch(p: re.Pattern, log: list, where: str) -> re.Pattern:
    s = p.pattern
    if s.endswith(r"\b") and not s.endswith(r"\\b"):
        new = re.compile(s[:-2] + TRAIL, p.flags)
        log.append({"where": where, "v4": s, "s1": new.pattern, "flags": int(p.flags)})
        return new
    return p


def _build():
    ns = dict(vars(v4))
    log = []
    for name in PATTERN_GROUPS:
        ns[name] = [(_patch(p, log, name), val) for p, val in ns[name]]
    for name in SINGLE_PATTERNS:
        ns[name] = _patch(ns[name], log, name)
    if len(log) != EXPECTED_PATCHED:
        raise RuntimeError(f"expected {EXPECTED_PATCHED} patched v4 patterns, found {len(log)} - "
                           f"the v4 extractor changed; review S1 before use")
    for name, obj in list(ns.items()):
        if isinstance(obj, types.FunctionType) and obj.__module__ == v4.__name__:
            f = types.FunctionType(obj.__code__, ns, obj.__name__, obj.__defaults__, obj.__closure__)
            f.__kwdefaults__ = obj.__kwdefaults__
            f.__doc__ = obj.__doc__
            ns[name] = f
    return ns, log


_NS, PATCH_LOG = _build()
extract_closed_vocab_entities_s1 = _NS["extract_closed_vocab_entities"]


def v4_patterns_unchanged() -> bool:
    """True if the v4 module still holds its own (unpatched) pattern objects."""
    for name in PATTERN_GROUPS:
        if any(TRAIL in p.pattern for p, _ in getattr(v4, name)):
            return False
    return all(TRAIL not in getattr(v4, n).pattern for n in SINGLE_PATTERNS)
