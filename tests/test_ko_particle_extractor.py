"""
Unit tests for the S1 extractor (src/cross_asr/ko_particle_extractor.py; spec Section 13).
No API call. Run:  python -m pytest tests/test_ko_particle_extractor.py -q
           or:     python -m tests.test_ko_particle_extractor
"""
import re

import src.entity_extraction.closed_vocab_extractor as v4
from src.cross_asr import ko_particle_extractor as s1
from src.cross_asr.ko_particle_extractor import extract_closed_vocab_entities_s1 as ex_s1

ex_v4 = v4.extract_closed_vocab_entities


def canon(d: dict) -> dict:
    """Extraction without raw text / position (what the matcher compares)."""
    return {k: sorted(tuple(sorted((a, b) for a, b in it.items() if a not in ("raw", "position"))) for it in v)
            for k, v in d.items()}


def vals(d: dict, etype: str) -> list:
    out = []
    for it in d[etype]:
        if etype == "vital_sign":
            out.append((it["label"], it["value"]))
        elif etype == "dose":
            out.append((it["value"], it["unit"]))
        else:
            out.append(it["normalized"])
    return sorted(out)


# ---------- positive: recognised by S1, not by v4 ----------
POSITIVE = [
    ("Ceftriaxone 2g을 IV로 q12h 투여", {"route": ["iv"], "dose": [("2", "g")], "frequency": ["q12h"]}),
    ("Lactulose 30ml를 PO로 투여", {"route": ["po"], "dose": [("30", "ml")]}),
    ("Furosemide 40mg을 IV로 투여", {"route": ["iv"], "dose": [("40", "mg")]}),
    ("Pip/tazo 4.5g이 IV로 투여되었다.", {"route": ["iv"], "dose": [("4.5", "g")]}),
    ("약물을 IV로, 투여", {"route": ["iv"]}),
    ("경로는 IV로", {"route": ["iv"]}),                                   # particle at end of text
    ("iv로 투여", {"route": ["iv"]}),                                      # case: v4 IGNORECASE kept
    ("Iv로 투여", {"route": ["iv"]}),
    ("Q8H로 투여", {"frequency": ["q8h"]}),
    ("q6h마다 투여", {"frequency": ["q6h"]}),
    ("PRN으로 투여", {"frequency": ["prn"]}),
    ("STAT으로 투여", {"frequency": ["stat"]}),
    ("BID로 투여", {"frequency": ["bid"]}),
    ("Foley를 유지", {"device": ["foley"]}),
    ("C-line이 삽입", {"device": ["c-line"]}),
    ("C-line이며 유지", {"device": ["c-line"]}),                           # 이며 (prefix 이)
    ("C-line이다.", {"device": ["c-line"]}),                               # 이다 (prefix 이)
    ("NC로 산소", {"device": ["nc"]}),
    ("ventilator를 적용", {"device": ["ventilator"]}),
    ("BP가 120/80", {"vital_sign": [("bp", "120/80")]}),
    ("SpO2는 95%", {"vital_sign": [("spo2", "95%")]}),
    ("HR이 110", {"vital_sign": [("hr", "110")]}),
    ("IV으로써 투여", {"route": ["iv"]}),                                  # 으로써 (prefix 으로, 로)
]

# ---------- negative: not recognised by S1 (and not by v4) ----------
NEGATIVE = [
    ("IVIG 투여", "route"), ("IVF로 투여", "route"), ("IB로 투여", "route"), ("PR간격 연장", "route"),
    ("IV주사 시행", "route"), ("IV투여 시행", "route"), ("IV로ABC 투여", "route"), ("IV로123 투여", "route"),
    ("IV로써먹 투여", "route"), ("IV로-1 투여", "route"),
    ("BPM 측정", "vital_sign"), ("NCT 시행", "device"), ("Foleyx를 유지", "device"),
    ("2gram을 IV로 투여", "dose"), ("40mg을test IV 투여", "dose"), ("40mg씩", "dose"),
    ("Q8H로ABC 투여", "frequency"), ("STATUS로 기록", "frequency"),
]

# ---------- regression: already recognised by v4, S1 must give the same result ----------
REGRESSION = [
    "Ceftriaxone 2g IV q12h 투여", "Lactulose 30 ml PO BID 투여함", "BP 120/80 mmHg, HR 110 bpm, RR 22, "
    "BT 37.2°C, SpO2 95% on room air", "Foley catheter 유지, C-line 삽입, NC 2L, ventilator 적용",
    "Furosemide 40 mg IV STAT", "Heparin 5000 units SC q8h", "혈압 110/70, 심박수 98, 정맥으로 투여",
    "Morphine 2 mg IV PRN for pain", "Insulin per os? no, sublingual nitroglycerin 0.4 mg SL",
    "IV fluids 100 mL/hr, urine output 30 mL", "NG tube 유지, high-flow nasal cannula 적용",
    "체온 38.5, 산소포화도는 실내 공기에서 92%", "Metoprolol 25 mg PO BID",
]


def test_patched_count_and_v4_untouched():
    assert len(s1.PATCH_LOG) == 41
    assert all(e["v4"].endswith(r"\b") and e["s1"].startswith(e["v4"][:-2]) for e in s1.PATCH_LOG)
    assert s1.v4_patterns_unchanged()
    assert ex_v4("Furosemide 40mg을 IV로 투여")["route"] == []          # v4 still behaves as v4


def test_particle_list():
    assert len(s1.PARTICLES) == len(set(s1.PARTICLES)) == 27
    assert all(re.fullmatch(r"[가-힣]+", p) for p in s1.PARTICLES)
    order = s1.PARTICLE_ALT.split("|")
    for i, a in enumerate(order):                      # a longer particle never comes after its prefix
        for b in order[i + 1:]:
            assert not b.startswith(a) or len(b) <= len(a)
    for p in s1.PARTICLES:                             # every particle works, at end and before a space
        for text in (f"약물을 IV{p} 투여", f"경로 IV{p}", f"경로 IV{p}."):
            assert vals(ex_s1(text), "route") == ["iv"], (p, text)
            assert vals(ex_v4(text), "route") == [], (p, text)


def test_positive():
    for text, expected in POSITIVE:
        got = ex_s1(text)
        for etype, want in expected.items():
            assert vals(got, etype) == sorted(want), (text, etype, vals(got, etype))


def test_negative():
    for text, etype in NEGATIVE:
        assert vals(ex_s1(text), etype) == [], (text, etype, vals(ex_s1(text), etype))
        assert vals(ex_v4(text), etype) == [], (text, etype)


def test_regression_identical_without_particles():
    for text in REGRESSION:
        assert canon(ex_s1(text)) == canon(ex_v4(text)), text


def test_pattern_level_superset():
    """Every span a v4 pattern matches is also matched by the corresponding S1 pattern."""
    corpus = REGRESSION + [t for t, _ in POSITIVE] + [t for t, _ in NEGATIVE]
    v4_pats = ([p for g in s1.PATTERN_GROUPS for p, _ in getattr(v4, g)] +
               [getattr(v4, n) for n in s1.SINGLE_PATTERNS])
    s1_pats = ([p for g in s1.PATTERN_GROUPS for p, _ in s1._NS[g]] + [s1._NS[n] for n in s1.SINGLE_PATTERNS])
    for pv, ps in zip(v4_pats, s1_pats):
        for text in corpus:
            spans_v4 = {m.span() for m in pv.finditer(text)}
            spans_s1 = {m.span() for m in ps.finditer(text)}
            assert spans_v4 <= spans_s1, (pv.pattern, text)


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"{n} tests passed")
