"""
Tests for the v4 -> S1 record pairing (src/cross_asr/sensitivity_ko_particle.align). No API call.
Run:  python -m pytest tests/test_sensitivity_ko_particle_align.py -q
 or:  python -m tests.test_sensitivity_ko_particle_align
"""
from src.cross_asr.sensitivity_ko_particle import align, status_of


def g(etype, gold, whisper, status, error=None, label=None):
    """Closed-vocab record with a gold value."""
    r = {"entity_type": etype, "gold_value": gold, "whisper_value": whisper, "match_status": status, "error_type": error}
    if label:
        r["label"] = label
    return r


def w(etype, whisper):
    """Whisper-only (hallucination) record."""
    return {"entity_type": etype, "gold_value": None, "whisper_value": whisper, "match_status": "whisper_only",
            "error_type": "hallucination"}


OM = ("omission", "omission")


def test_unique_key_is_paired():
    items = align([g("route", "iv", None, *OM)], [g("route", "iv", "iv", "matched")])
    assert len(items) == 1 and items[0]["kind"] == "pair" and items[0]["pairing"] == "unique"
    assert status_of(items[0]["a"]) == "omission" and status_of(items[0]["b"]) == "matched"


def test_labels_keep_vital_signs_apart():
    v4 = [g("vital_sign", "120", None, *OM, label="hr"), g("vital_sign", "120", "120", "matched", label="bp")]
    s1 = [g("vital_sign", "120", "120", "matched", label="hr"), g("vital_sign", "120", "120", "matched", label="bp")]
    items = align(v4, s1)
    assert all(i["kind"] == "pair" and i["pairing"] == "unique" for i in items)
    pairs = {(i["a"]["label"], status_of(i["a"]), status_of(i["b"])) for i in items}
    assert pairs == {("hr", "omission", "matched"), ("bp", "matched", "matched")}


def test_duplicate_key_same_judgements_not_reported_as_change():
    v4 = [g("device", "nc", "nc", "matched"), g("device", "nc", "nc", "matched")]
    items = align(v4, [dict(r) for r in v4])
    assert [i["pairing"] for i in items] == ["duplicate_same", "duplicate_same"]
    assert all(status_of(i["a"]) == status_of(i["b"]) for i in items)


def test_duplicate_key_with_differing_judgements_is_one_ambiguous_group():
    # gold has "nc" twice (device + oxygen support); v4 matched one, S1 matched both
    v4 = [g("device", "nc", "nc", "matched"), g("device", "nc", None, *OM)]
    s1 = [g("device", "nc", "nc", "matched"), g("device", "nc", "nc", "matched")]
    items = align(v4, s1)
    assert len(items) == 1 and items[0]["kind"] == "group" and items[0]["pairing"] == "ambiguous_group"
    assert sorted(map(status_of, items[0]["a"])) == ["matched", "omission"]
    assert sorted(map(status_of, items[0]["b"])) == ["matched", "matched"]


def test_duplicate_key_same_statuses_but_different_values_is_ambiguous():
    v4 = [g("dose", "40mg", "40mg", "matched"), g("dose", "40mg", "4mg", "error", "numeric_error")]
    s1 = [g("dose", "40mg", "40mg", "matched"), g("dose", "40mg", "400mg", "error", "numeric_error")]
    items = align(v4, s1)
    assert len(items) == 1 and items[0]["pairing"] == "ambiguous_group"


def test_ambiguous_group_does_not_hide_unique_neighbours():
    v4 = [g("device", "nc", "nc", "matched"), g("device", "nc", None, *OM), g("route", "iv", None, *OM)]
    s1 = [g("device", "nc", "nc", "matched"), g("device", "nc", "nc", "matched"), g("route", "iv", "iv", "matched")]
    kinds = sorted((i["kind"], i["pairing"]) for i in align(v4, s1))
    assert kinds == [("group", "ambiguous_group"), ("pair", "unique")]


def test_whisper_only_appears_and_disappears():
    items = align([w("dose", "60mg")], [w("route", "iv")])
    got = {(i["a"]["whisper_value"] if i["a"] else None, i["b"]["whisper_value"] if i["b"] else None) for i in items}
    assert got == {(None, "iv"), ("60mg", None)}
    assert all(i["pairing"] == "unique" for i in items)


def test_whisper_only_count_increase():
    items = align([w("route", "iv")], [w("route", "iv"), w("route", "iv")])
    assert len(items) == 2
    assert sum(1 for i in items if i["a"] is None and i["b"] is not None) == 1
    assert all(i["pairing"] == "duplicate_same" for i in items)


def test_every_record_accounted_for_once():
    v4 = [g("device", "nc", "nc", "matched"), g("device", "nc", None, *OM), g("route", "iv", None, *OM),
          w("dose", "60mg"), w("route", "iv")]
    s1 = [g("device", "nc", "nc", "matched"), g("device", "nc", "nc", "matched"), g("route", "iv", "iv", "matched"),
          w("route", "iv"), w("route", "iv")]
    n_a = n_b = 0
    for i in align(v4, s1):
        if i["kind"] == "group":
            n_a, n_b = n_a + len(i["a"]), n_b + len(i["b"])
        else:
            n_a, n_b = n_a + (i["a"] is not None), n_b + (i["b"] is not None)
    assert (n_a, n_b) == (len(v4), len(s1))


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"{n} tests passed")
