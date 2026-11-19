"""
Tests for the output helpers of src/cross_asr/sensitivity_ko_particle.py (no API call):
empty inputs keep the CSV structure; case checks count duplicate gold records and separate
code-checkable facts from points that need human review.
Run:  python -m pytest tests/test_sensitivity_ko_particle_helpers.py -q
 or:  python -m tests.test_sensitivity_ko_particle_helpers
"""
import pandas as pd

from src.cross_asr.ko_particle_extractor import extract_closed_vocab_entities_s1 as ex_s1
from src.cross_asr.sensitivity_ko_particle import (CHANGE_COLUMNS, CASE15_COLUMNS, SIDE_EFFECT_COLUMNS,
                                                   STRATIFIED_COLUMNS, case_check, side_effect_table,
                                                   stratified_sample)
from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities as ex_v4


def change(**kw):
    row = {c: None for c in CHANGE_COLUMNS}
    row.update({"condition": "c1", "sample_id": "s1", "style": "formal_template", "pairing": "unique",
                "weight_change": 0, "context_s1": "", "transcript": ""})
    row.update(kw)
    return row


def rec(etype, gold, whisper, status):
    return {"entity_type": etype, "gold_value": gold, "whisper_value": whisper, "match_status": status,
            "error_type": None if status == "matched" else "omission"}


def test_empty_changes_keep_columns():
    ch = pd.DataFrame([], columns=CHANGE_COLUMNS)
    s = stratified_sample(ch, seed=1)
    e = side_effect_table(ch, {})
    assert len(s) == 0 and list(s.columns) == STRATIFIED_COLUMNS
    assert len(e) == 0 and list(e.columns) == SIDE_EFFECT_COLUMNS
    # the CSV written from an empty table still has the header and reads back with the same columns
    import io
    buf = io.StringIO()
    s.to_csv(buf, index=False)
    assert list(pd.read_csv(io.StringIO(buf.getvalue())).columns) == STRATIFIED_COLUMNS


def test_no_omission_to_matched_but_other_changes():
    ch = pd.DataFrame([change(entity_type="dose", gold_value="40mg", v4_status="omission",
                              s1_status="error:numeric_error", s1_whisper_value="4mg")], columns=CHANGE_COLUMNS)
    s = stratified_sample(ch, seed=1)
    e = side_effect_table(ch, {})
    assert len(s) == 0 and list(s.columns) == STRATIFIED_COLUMNS
    assert len(e) == 1 and e.auto_flag.iloc[0].startswith("new_error_on_gold_entity")


def test_stratified_sample_is_reproducible_and_capped():
    rows = [change(sample_id=f"s{i}", entity_type="route", gold_value="iv", v4_status="omission",
                   s1_status="matched") for i in range(7)]
    rows += [change(sample_id="g", entity_type="device", gold_value="nc", v4_status="omission",
                    s1_status="matched", pairing="ambiguous_group")]
    ch = pd.DataFrame(rows, columns=CHANGE_COLUMNS)
    a, b = stratified_sample(ch, seed=7, k=2), stratified_sample(ch, seed=7, k=2)
    assert len(a) == 2 and a.sample_id.tolist() == b.sample_id.tolist()
    assert set(a.stratum_size) == {7} and "g" not in set(a.sample_id)        # ambiguous groups excluded


def test_case_all_partial_none_with_duplicate_gold():
    text = "Foley 유지, NC로 산소 공급"
    closed_v4 = [rec("device", "nc", None, "omission"), rec("device", "nc", None, "omission")]
    closed_s1 = [rec("device", "nc", "nc", "matched"), rec("device", "nc", None, "omission")]
    r = case_check(text, ex_v4(text), ex_s1(text), closed_v4, closed_s1, "device", "nc")
    assert set(r) == set(CASE15_COLUMNS) - {"condition", "sample_id", "entity_type", "gold_value"}
    assert (r["n_gold_records"], r["n_matched_v4"], r["n_matched_s1"]) == (2, 0, 1)
    assert r["match_level_s1"] == "partial" and r["needs_human_review"]
    closed_s1_all = [rec("device", "nc", "nc", "matched"), rec("device", "nc", "nc", "matched")]
    r2 = case_check(text, ex_v4(text), ex_s1(text), closed_v4, closed_s1_all, "device", "nc")
    assert r2["match_level_s1"] == "all" and not r2["needs_human_review"]


def test_case_code_checks_are_facts_not_conclusions():
    # attached particle, extracted and matched
    t1 = "Furosemide 40mg을 IV로 투여"
    r = case_check(t1, ex_v4(t1), ex_s1(t1), [rec("route", "iv", None, "omission")],
                   [rec("route", "iv", "iv", "matched")], "route", "iv")
    assert r["extracted_s1"] and r["ascii_form_followed_by_listed_particle"] == 1 and not r["needs_human_review"]
    # ASR misspelling: no ASCII form of the value at all -> outside S1, needs review
    t2 = "Furosemide 40mg을 IB로 투여"
    r = case_check(t2, ex_v4(t2), ex_s1(t2), [rec("route", "iv", None, "omission")],
                   [rec("route", "iv", None, "omission")], "route", "iv")
    assert not r["extracted_s1"] and r["ascii_form_in_transcript"] == 0
    assert r["code_check"].startswith("no ASCII form") and r["needs_human_review"] and r["match_level_s1"] == "none"
    # ASCII form with a non-particle suffix -> outside S1, needs review
    t3 = "Furosemide 40mg IV주사 시행"
    r = case_check(t3, ex_v4(t3), ex_s1(t3), [rec("route", "iv", None, "omission")],
                   [rec("route", "iv", None, "omission")], "route", "iv")
    assert r["ascii_form_in_transcript"] == 1 and r["ascii_form_followed_by_listed_particle"] == 0
    assert r["code_check"].startswith("ASCII form present only without") and r["needs_human_review"]
    # transliterated device: no ASCII form
    t4 = "폴리 캐테터가 삽입되어 있다"
    r = case_check(t4, ex_v4(t4), ex_s1(t4), [rec("device", "foley", None, "omission")],
                   [rec("device", "foley", None, "omission")], "device", "foley")
    assert r["ascii_form_in_transcript"] == 0 and r["needs_human_review"]


def test_case_dose_forms():
    t = "Lactulose 30ml를 PO로 복용"
    r = case_check(t, ex_v4(t), ex_s1(t), [rec("dose", "30ml", None, "omission")],
                   [rec("dose", "30ml", "30ml", "matched")], "dose", "30ml")
    assert r["extracted_s1"] and not r["extracted_v4"] and r["ascii_form_followed_by_listed_particle"] == 1


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"{n} tests passed")
