"""
Post hoc evaluator sensitivity analysis S1: Korean particle attachment (docs/cross_asr_spec.md
Section 13). The v4 evaluation remains the PRIMARY analysis; S1 is a sensitivity analysis designed
after the notation diagnostics (Section 12.8).

No API call (Claude or ASR). For every sample of the September v4 run and of the six Cross-ASR
conditions:
    closed-vocab  v4  : read from the saved *_matched.json; it is first re-derived from the transcript
                        and the scaffold with the unchanged v4 code, and any mismatch stops the run
                  S1  : src.cross_asr.ko_particle_extractor on the same transcript, then the unchanged
                        v4 matcher against the unchanged scaffold gold
    open-vocab        : reused unchanged from the saved *_matched.json (the LLM steps do not use the
                        regex extractor)
    CCER / statistics : v4 weights and flattening; functions of src/cross_asr/analysis.py with the same
                        seed (joint scenario bootstrap, Friedman, Wilcoxon-Holm); all 100 scenarios and
                        n = 98 (scenarios 007 and 063 excluded)

Modes (only --run writes anything)
    (default)    dry run: input completeness and the plan; nothing is computed or written
    --verify-v4  read-only check on the real data: are the saved v4 closed-vocab matches of every
                 condition reproduced exactly from the transcripts and the scaffold? Writes nothing.
    --run        computes everything into a temporary folder next to the output folder and moves it
                 to results/cross_asr/sensitivity_ko_particle/ only after every file was written and
                 checked; on any failure the temporary folder is removed and nothing is left behind.
                 Stops if the output folder already exists.

Record pairing (transition table, record changes): closed-vocab records of v4 and S1 are paired by
(entity_type, label, gold_value); whisper-only records by (entity_type, whisper_value). When one key
occurs more than once in a sample and the multisets of judgements differ, the individual pairing is
ambiguous: such a key is reported once as a group ("ambiguous_group", v4 judgements -> S1 judgements)
and not as individual transitions. Aggregate counts (CCER, error types) never depend on pairing.

Outputs (with --run): meta.json, inputs_sha256.csv, per_sample_ccer.csv,
pooled_ccer_{primary,n98}.csv, error_type_counts.csv, delta_bootstrap_{primary,n98}.csv,
delta_between_systems_{primary,n98}.csv, friedman_{primary,n98}.csv, wilcoxon_holm_{primary,n98}.csv,
condB_descriptive.csv, transitions.csv, record_changes.csv, side_effect_audit.csv,
omission_to_matched_stratified_sample.csv, case15_notation_suspects.csv

Usage
    python -m src.cross_asr.sensitivity_ko_particle                 # dry run
    python -m src.cross_asr.sensitivity_ko_particle --verify-v4     # read-only reproduction check
    python -m src.cross_asr.sensitivity_ko_particle --run
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from src.cross_asr import ko_particle_extractor as s1mod
from src.cross_asr.analysis import (STYLES, COND_A, COND_B, B_PAIR, V4_LABEL, TTS_SUSPECT_SCENARIOS,
                                    pooled_table, joint_bootstrap, delta_differences, v4_tests, rank_string)
from src.cross_asr.common import (load_cross_asr_config, primary_samples, git_commit, git_dirty_paths,
                                  now_utc, sha256_file, CROSS_ASR_CONFIG)
from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities as extract_v4
from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab
from src.evaluation.ccer_eval import ERROR_WEIGHTS
from src.evaluation.flatten_matches import flatten_all_matches, flatten_closed_vocab
from src.matching.entity_matcher import match_closed_vocab

EMPTY_RESPONSE_RULE = {"chirp3_auto": {"scenario_063_telegraphic_icu"}}     # spec 12.2
SAMPLE_PER_STRATUM = 2
OUT_NAME = "sensitivity_ko_particle"
ASCII_PARTICLE = re.compile(rf"[A-Za-z0-9%](?:{s1mod.PARTICLE_ALT})(?:\s|[{s1mod.PUNCT}]|\Z)")
OUTPUT_FILES = ["meta.json", "inputs_sha256.csv", "per_sample_ccer.csv", "pooled_ccer_primary.csv",
                "pooled_ccer_n98.csv", "error_type_counts.csv", "delta_bootstrap_primary.csv",
                "delta_bootstrap_n98.csv", "delta_between_systems_primary.csv", "delta_between_systems_n98.csv",
                "friedman_primary.csv", "friedman_n98.csv", "wilcoxon_holm_primary.csv", "wilcoxon_holm_n98.csv",
                "condB_descriptive.csv", "transitions.csv", "record_changes.csv", "side_effect_audit.csv",
                "omission_to_matched_stratified_sample.csv", "case15_notation_suspects.csv"]
CODE_FILES = ["src/cross_asr/ko_particle_extractor.py", "src/cross_asr/sensitivity_ko_particle.py",
              "src/cross_asr/analysis.py", "src/cross_asr/common.py",
              "src/entity_extraction/closed_vocab_extractor.py", "src/entity_extraction/scaffold_as_gold.py",
              "src/matching/entity_matcher.py", "src/evaluation/flatten_matches.py", "src/evaluation/ccer_eval.py"]


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def weighted_gold(records):
    gold = sum(1 for r in records if r["gold_value"] is not None)
    w = sum(ERROR_WEIGHTS.get(r["error_type"], 0) for r in records if r["error_type"] is not None)
    return float(w), gold


def status_of(r) -> str:
    if r is None:
        return "absent"
    return r["match_status"] if r["error_type"] is None or r["match_status"] == "omission" else \
        f"{r['match_status']}:{r['error_type']}"


def judgement(r) -> tuple:
    return (status_of(r), r.get("whisper_value") if r else None)


def align(v4_recs: list, s1_recs: list) -> list:
    """Pair closed-vocab records of v4 and S1 (see module docstring).

    Returns items:
      {"kind": "pair", "a": rec|None, "b": rec|None, "pairing": "unique" | "duplicate_same"}
      {"kind": "group", "key": (...), "a": [recs], "b": [recs], "pairing": "ambiguous_group"}
    """
    items = []

    def add_groups(gv: dict, gs: dict):
        for k in sorted(set(gv) | set(gs), key=str):
            a, b = gv.get(k, []), gs.get(k, [])
            if len(a) <= 1 and len(b) <= 1:
                items.append({"kind": "pair", "a": a[0] if a else None, "b": b[0] if b else None, "pairing": "unique"})
            elif sorted(map(judgement, a)) == sorted(map(judgement, b)):
                for x, y in zip(sorted(a, key=judgement), sorted(b, key=judgement)):
                    items.append({"kind": "pair", "a": x, "b": y, "pairing": "duplicate_same"})
            else:
                items.append({"kind": "group", "key": k, "a": a, "b": b, "pairing": "ambiguous_group"})

    gv, gs, wv, ws = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for r in v4_recs:
        (gv[(r["entity_type"], r.get("label"), r["gold_value"])] if r["gold_value"] is not None
         else wv[(r["entity_type"], r.get("label"), "whisper:" + str(r["whisper_value"]))]).append(r)
    for r in s1_recs:
        (gs[(r["entity_type"], r.get("label"), r["gold_value"])] if r["gold_value"] is not None
         else ws[(r["entity_type"], r.get("label"), "whisper:" + str(r["whisper_value"]))]).append(r)
    add_groups(gv, gs)
    # whisper-only records with the same value are identical, so pairing them by count is not ambiguous
    for k in sorted(set(wv) | set(ws), key=str):
        a, b = wv.get(k, []), ws.get(k, [])
        for i in range(max(len(a), len(b))):
            items.append({"kind": "pair", "a": a[i] if i < len(a) else None, "b": b[i] if i < len(b) else None,
                          "pairing": "unique" if max(len(a), len(b)) == 1 else "duplicate_same"})
    return items


def context(text: str, extraction: dict, etype: str, value, width: int = 40) -> str:
    """Transcript snippet around the S1 extraction of this entity value ("" if not extracted)."""
    if value is None:
        return ""
    for it in extraction.get(etype, []):
        v = it.get("normalized") or (it["value"] if etype == "vital_sign" else f"{it.get('value')}{it.get('unit')}")
        if str(v) == str(value):
            p = it["position"]
            return text[max(0, p - width): p + len(it["raw"]) + width].replace("\n", " ")
    return ""


CHANGE_COLUMNS = ["condition", "sample_id", "style", "entity_type", "label", "gold_value", "pairing",
                  "v4_whisper_value", "v4_status", "s1_whisper_value", "s1_status", "weight_change", "context_s1",
                  "transcript"]
SIDE_EFFECT_COLUMNS = CHANGE_COLUMNS + ["auto_flag", "review_label"]
STRATIFIED_COLUMNS = CHANGE_COLUMNS + ["stratum_size", "review_label"]
CASE15_COLUMNS = ["condition", "sample_id", "entity_type", "gold_value", "extracted_v4", "extracted_s1",
                  "n_gold_records", "n_matched_v4", "n_matched_s1", "match_level_s1", "s1_judgements",
                  "ascii_form_in_transcript", "ascii_form_followed_by_listed_particle", "code_check",
                  "needs_human_review", "review_note"]


def stratified_sample(ch: pd.DataFrame, seed: int, k: int = SAMPLE_PER_STRATUM) -> pd.DataFrame:
    """omission -> matched changes (unique pairings only), k per condition x style x entity type.
    Always returns the STRATIFIED_COLUMNS, also when there is no such change."""
    om = ch[(ch.v4_status == "omission") & (ch.s1_status == "matched") & (ch.pairing != "ambiguous_group")]
    rng = random.Random(seed)
    rows = []
    for _, g in om.groupby(["condition", "style", "entity_type"], sort=True):
        idx = sorted(g.index)
        for i in rng.sample(idx, min(k, len(idx))):
            rows.append({**om.loc[i].to_dict(), "stratum_size": len(idx), "review_label": ""})
    return pd.DataFrame(rows, columns=STRATIFIED_COLUMNS)


def side_effect_table(ch: pd.DataFrame, extractions: dict) -> pd.DataFrame:
    """Every changed record / group not ending as "matched", with an automatic flag (a candidate
    label for review, not a conclusion). Always returns the SIDE_EFFECT_COLUMNS."""
    se = ch[ch.s1_status != "matched"].copy()

    def flag(r):
        if r.pairing == "ambiguous_group":
            return "ambiguous_group (duplicate gold key; review the group as a whole)"
        if r.s1_status == "absent":
            return "removed_under_S1 (v4 record no longer produced)"
        if str(r.s1_status).startswith("whisper_only"):
            ext = extractions.get((r.condition, r.sample_id), {})
            n_ext = sum(1 for it in ext.get(r.entity_type, [])
                        if str(it.get("normalized") or (it.get("value") if r.entity_type == "vital_sign"
                                                         else f"{it.get('value')}{it.get('unit')}")) == str(r.s1_whisper_value))
            if n_ext >= 2:
                return "duplicate_mention (same value extracted >=2 times; evaluator artifact candidate)"
            if r.entity_type == "dose" and re.search(r"플루이드|fluid|수액|식염수|saline", r.context_s1 or "", re.I):
                return "possible_fluid_volume_as_dose (v4 ownership limit; evaluator artifact candidate)"
            return "other_insertion (check: real ASR insertion?)"
        return "new_error_on_gold_entity (check: real ASR error?)"

    se["auto_flag"] = [flag(r) for r in se.itertuples()]
    se["review_label"] = ""   # evaluator_duplicate / evaluator_other / asr_hallucination / asr_error / unclear
    return se.reindex(columns=SIDE_EFFECT_COLUMNS)


def value_of(item: dict, etype: str) -> str:
    if etype == "vital_sign":
        return str(item.get("value"))
    return str(item.get("normalized") or f"{item.get('value')}{item.get('unit')}")


def ascii_forms(text: str, etype: str, gold: str) -> list:
    """Code-checkable fact: occurrences of an ASCII form of the gold value, found with the v4 patterns
    for that value WITHOUT their final boundary, and the text right after each occurrence."""
    import src.entity_extraction.closed_vocab_extractor as v4
    pats = []
    if etype in ("route", "frequency", "device"):
        group = {"route": v4.ROUTE_PATTERNS, "frequency": v4.FREQUENCY_PATTERNS, "device": v4.DEVICE_PATTERNS}[etype]
        pats = [p for p, norm in group if norm == gold and p.pattern.endswith(r"\b")]
        mq = re.fullmatch(r"q(\d+)h", gold or "")
        if etype == "frequency" and mq:
            pats.append(re.compile(rf"\bq[\s-]?{mq.group(1)}\s*h", re.I))
    elif etype == "dose":
        md = re.fullmatch(r"([\d.]+)([A-Za-z/]+)", gold or "")
        if md:
            pats.append(re.compile(rf"(?<![\d.]){re.escape(md.group(1))}\s*{re.escape(md.group(2))}\b", re.I))
    out = []
    for p in pats:
        core = re.compile(p.pattern[:-2], p.flags) if p.pattern.endswith(r"\b") else p
        for m in core.finditer(text):
            out.append((m.start(), m.end(), text[m.end():m.end() + 4]))
    return out


def case_check(text: str, ext_v4: dict, ext_s1: dict, closed_v4: list, closed_s1: list, etype: str, gold: str) -> dict:
    """One manually reviewed record: extraction and final matching reported separately; duplicate
    gold records counted. Facts the code can verify are kept apart from what needs human review."""
    def extracted(ext):
        return any(value_of(it, etype) == gold for it in ext.get(etype, []))
    recs_s1 = [x for x in closed_s1 if x["entity_type"] == etype and str(x["gold_value"]) == gold]
    recs_v4 = [x for x in closed_v4 if x["entity_type"] == etype and str(x["gold_value"]) == gold]
    n, m1 = len(recs_s1), sum(1 for x in recs_s1 if x["match_status"] == "matched")
    m0 = sum(1 for x in recs_v4 if x["match_status"] == "matched")
    level = "no_gold_record" if n == 0 else ("all" if m1 == n else ("partial" if m1 > 0 else "none"))
    forms = ascii_forms(text, etype, gold)
    particle = re.compile(rf"(?:{s1mod.PARTICLE_ALT})(?:\s|[{s1mod.PUNCT}]|\Z)")
    with_particle = [f for f in forms if particle.match(f[2])]
    e1 = extracted(ext_s1)
    if e1 and level == "all":
        check, review = "extracted by S1 and all gold records matched", False
    elif e1:
        check, review = "extracted by S1 but not all gold records matched", True
    elif not forms:
        check, review = "no ASCII form of the gold value found in the transcript (outside S1 scope)", True
    elif with_particle:
        check, review = "ASCII form followed by a listed particle is present but S1 did not extract it", True
    else:
        check, review = "ASCII form present only without a listed particle + boundary (outside S1 scope)", True
    return {"extracted_v4": extracted(ext_v4), "extracted_s1": e1, "n_gold_records": n, "n_matched_v4": m0,
            "n_matched_s1": m1, "match_level_s1": level,
            "s1_judgements": "|".join(sorted(status_of(x) for x in recs_s1)),
            "ascii_form_in_transcript": len(forms), "ascii_form_followed_by_listed_particle": len(with_particle),
            "code_check": check, "needs_human_review": review, "review_note": ""}


def case_sheet_paths(res_root: Path) -> dict:
    return {c: res_root / "notation_diagnostics" / f"part3_case_review_{c}.csv" for c in COND_A}


def load_case15(res_root: Path) -> pd.DataFrame | None:
    rows = []
    for c, p in case_sheet_paths(res_root).items():
        if not p.exists():
            return None
        d = pd.read_csv(p, encoding="utf-8-sig")
        d = d[d.stratum == "notation_suspect_record"]
        rows += [{"condition": c, "sample_id": r.sample_id, "entity_type": r.entity_type, "gold_value": str(r.gold_value)}
                 for r in d.itertuples()]
    return pd.DataFrame(rows)


def setup(cfg: dict):
    samples = primary_samples(cfg)
    root = Path(cfg["paths"]["output_root"])
    sources = {V4_LABEL: (Path(cfg["paths"]["original_stt_dir"]), Path(cfg["paths"]["original_entities_dir"]))}
    for c in COND_A + COND_B:
        sources[c] = (root / c / "stt_transcripts", root / c / "entities")
    problems = []
    for c, (sd, ed) in sources.items():
        for s in samples:
            sid = s["sample_id"]
            if not (ed / f"{sid}_matched.json").exists():
                problems.append(f"{c}: {sid}_matched.json missing")
            if not (sd / f"{sid}.json").exists() and sid not in EMPTY_RESPONSE_RULE.get(c, set()):
                problems.append(f"{c}: transcript {sid} missing")
    scen_dir = Path(cfg["paths"]["scenarios_dir"])
    for scn in sorted({s["scenario_id"] for s in samples}):
        if not (scen_dir / f"{scn}.json").exists():
            problems.append(f"scaffold {scn}.json missing")
    return samples, sources, problems


def load_sample(sd: Path, ed: Path, scen_dir: Path, s: dict):
    sid = s["sample_id"]
    m = json.load(open(ed / f"{sid}_matched.json", encoding="utf-8"))
    tp = sd / f"{sid}.json"
    text = json.load(open(tp, encoding="utf-8"))["whisper_transcript"] if tp.exists() else ""
    gold_closed = scaffold_to_closed_vocab(json.load(open(scen_dir / f"{s['scenario_id']}.json", encoding="utf-8")))
    return m, text, gold_closed


def verify_v4(cfg: dict, samples: list, sources: dict) -> int:
    """Read-only: saved v4 closed-vocab matches == v4 code applied to transcript + scaffold."""
    scen_dir = Path(cfg["paths"]["scenarios_dir"])
    bad_total = 0
    print("=== read-only check: saved v4 closed-vocab matches reproduced from transcript + scaffold ===")
    for c, (sd, ed) in sources.items():
        bad = []
        for s in samples:
            m, text, gold_closed = load_sample(sd, ed, scen_dir, s)
            if match_closed_vocab(gold_closed, extract_v4(text)) != m["closed_vocab_matches"]:
                bad.append(s["sample_id"])
        bad_total += len(bad)
        print(f"{c:22s} reproduced {len(samples) - len(bad)}/{len(samples)}" + (f"  NOT reproduced: {bad[:5]}" if bad else ""))
    print("VERIFY OK - all saved v4 closed-vocab matches reproduced (nothing written)" if bad_total == 0 else
          f"VERIFY FAILED - {bad_total} samples not reproduced (nothing written)")
    return 0 if bad_total == 0 else 1


def input_files(cfg: dict, samples: list, sources: dict, res_root: Path) -> list:
    files = [Path(CROSS_ASR_CONFIG), Path(cfg["base_config"]), Path(cfg["paths"]["output_root"]) / "pilot_samples.json"]
    files += list(case_sheet_paths(res_root).values())
    gen = Path(cfg["paths"]["generated_text_dir"])
    files += [gen / f"{s['sample_id']}.json" for s in samples]                       # sample list / style
    scen = Path(cfg["paths"]["scenarios_dir"])
    files += [scen / f"{x}.json" for x in sorted({s["scenario_id"] for s in samples})]   # gold scaffold
    for c, (sd, ed) in sources.items():
        for s in samples:
            files.append(ed / f"{s['sample_id']}_matched.json")
            tp = sd / f"{s['sample_id']}.json"
            if tp.exists():
                files.append(tp)
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify-v4", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = load_cross_asr_config()
    res_root = Path(cfg["paths"]["results_root"])
    out = Path(args.out or res_root / OUT_NAME)
    samples, sources, problems = setup(cfg)

    if args.verify_v4:
        if problems:
            print(f"STOP: {len(problems)} input problems, e.g. {problems[:3]}")
            return 1
        return verify_v4(cfg, samples, sources)

    acfg = cfg["analysis"]
    n_boot, seed, ci = int(acfg["bootstrap_iterations"]), int(acfg["bootstrap_seed"]), float(acfg["ci_level"])
    scenarios = sorted({s["scenario_id"] for s in samples})
    case15 = load_case15(res_root)
    print("=== S1 sensitivity analysis (post hoc; v4 remains primary) - plan ===")
    print(f"conditions          : {list(sources)}")
    print(f"samples per cond.   : {len(samples)}; scenarios {len(scenarios)}; n98 excludes {TTS_SUSPECT_SCENARIOS}")
    print(f"patched v4 regexes  : {len(s1mod.PATCH_LOG)} (expected 41); v4 module unchanged: {s1mod.v4_patterns_unchanged()}")
    print(f"particles ({len(s1mod.PARTICLES)})      : {' '.join(s1mod.PARTICLES)}")
    print(f"boundary after it   : whitespace, one of {s1mod.PUNCT!r}, or end of text")
    print(f"bootstrap           : {n_boot} resamples, seed {seed}; stratified review sample: "
          f"{SAMPLE_PER_STRATUM} per stratum, seed {seed}")
    print(f"case-15 sheets      : {'found' if case15 is not None else 'MISSING (notation_diagnostics part3 sheets)'}"
          + (f" ({len(case15)} records)" if case15 is not None else ""))
    print(f"inputs to hash      : configs, pilot list, case sheets, generated_text (300), scaffolds "
          f"({len(scenarios)}), match files and transcripts of {len(sources)} conditions")
    print(f"API calls           : 0 (Claude 0, ASR 0)")
    print(f"output folder       : {out}  ({'EXISTS - would stop' if out.exists() else 'new'}); written via a "
          f"temporary folder and moved only when complete")
    print(f"files to write      : {', '.join(OUTPUT_FILES)}")
    if problems:
        print(f"STOP: {len(problems)} input problems, e.g. {problems[:3]}")
        return 1
    if case15 is None or out.exists() or not s1mod.v4_patterns_unchanged() or len(s1mod.PATCH_LOG) != 41:
        print("STOP: see the plan lines above")
        return 1
    if not args.run:
        print("DRY RUN - nothing computed or written (add --verify-v4 for the read-only check, --run to compute)")
        return 0

    tmp = out.with_name(f".{out.name}.tmp-{os.getpid()}")
    if tmp.exists():
        print(f"STOP: temporary folder {tmp} exists")
        return 1
    try:
        tmp.mkdir(parents=True)
        rc = compute(cfg, samples, sources, scenarios, case15, res_root, tmp, n_boot, seed, ci)
        if rc != 0:
            raise RuntimeError("computation stopped")
        missing = [f for f in OUTPUT_FILES if not (tmp / f).exists()]
        if missing:
            raise RuntimeError(f"output files missing: {missing}")
        if out.exists():
            raise RuntimeError(f"{out} appeared during the run")
        os.rename(tmp, out)
    except BaseException as e:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"RUN FAILED - nothing written ({type(e).__name__}: {e})")
        return 2
    print(f"written: {out}/  ({len(OUTPUT_FILES)} files)")
    return 0


def compute(cfg, samples, sources, scenarios, case15, res_root, out, n_boot, seed, ci) -> int:
    scen_dir = Path(cfg["paths"]["scenarios_dir"])
    data_v4, data_s1, per_sample, trans, changes = {}, {}, [], Counter(), []
    err_counts = Counter()
    texts, ext_s1_cache, closed_s1_cache, closed_v4_cache = {}, {}, {}, {}
    for c, (sd, ed) in sources.items():
        rv, rs = [], []
        for s in samples:
            sid, st = s["sample_id"], s["style_condition"]
            m, text, gold_closed = load_sample(sd, ed, scen_dir, s)
            texts[(c, sid)] = text
            if match_closed_vocab(gold_closed, extract_v4(text)) != m["closed_vocab_matches"]:
                print(f"STOP: {c} {sid}: saved closed-vocab matches are not reproduced from the transcript")
                return 1
            e1 = s1mod.extract_closed_vocab_entities_s1(text)
            closed_s1 = match_closed_vocab(gold_closed, e1)
            ext_s1_cache[(c, sid)], closed_s1_cache[(c, sid)] = e1, flatten_closed_vocab(closed_s1)
            closed_v4_cache[(c, sid)] = flatten_closed_vocab(m["closed_vocab_matches"])
            rec_v4 = flatten_all_matches(m)
            rec_s1 = flatten_all_matches({"closed_vocab_matches": closed_s1, "open_vocab_matches": m["open_vocab_matches"]})
            wv, gv = weighted_gold(rec_v4)
            ws, gs = weighted_gold(rec_s1)
            rv.append({**s, "weighted": wv, "gold": gv, "ccer": wv / gv})
            rs.append({**s, "weighted": ws, "gold": gs, "ccer": ws / gs})
            per_sample.append({"condition": c, "sample_id": sid, "style": st, "gold": gv,
                               "weighted_v4": wv, "weighted_s1": ws, "ccer_v4": round(wv / gv, 4),
                               "ccer_s1": round(ws / gs, 4), "transcript_sha256": sha_text(text),
                               "particle_forms_in_transcript": len(ASCII_PARTICLE.findall(text))})
            for side, recs in (("v4", rec_v4), ("s1", rec_s1)):
                for r in recs:
                    if r["error_type"]:
                        err_counts[(c, st, r["error_type"], side)] += 1
            for it in align(closed_v4_cache[(c, sid)], closed_s1_cache[(c, sid)]):
                if it["kind"] == "group":
                    et, label, gold = it["key"]
                    sa = "|".join(sorted(status_of(r) for r in it["a"])) or "absent"
                    sb = "|".join(sorted(status_of(r) for r in it["b"])) or "absent"
                    trans[(c, st, et, sa, sb, "ambiguous_group")] += 1
                    changes.append({"condition": c, "sample_id": sid, "style": st, "entity_type": et, "label": label,
                                    "gold_value": gold, "pairing": "ambiguous_group",
                                    "v4_whisper_value": "|".join(str(r.get("whisper_value")) for r in it["a"]),
                                    "v4_status": sa,
                                    "s1_whisper_value": "|".join(str(r.get("whisper_value")) for r in it["b"]),
                                    "s1_status": sb,
                                    "weight_change": sum(ERROR_WEIGHTS.get(r["error_type"], 0) for r in it["b"] if r["error_type"])
                                    - sum(ERROR_WEIGHTS.get(r["error_type"], 0) for r in it["a"] if r["error_type"]),
                                    "context_s1": "", "transcript": text})
                    continue
                a, b = it["a"], it["b"]
                ref = a or b
                sa, sb = status_of(a), status_of(b)
                trans[(c, st, ref["entity_type"], sa, sb, it["pairing"])] += 1
                if judgement(a) != judgement(b):
                    wa = ERROR_WEIGHTS.get(a["error_type"], 0) if a and a["error_type"] else 0
                    wb = ERROR_WEIGHTS.get(b["error_type"], 0) if b and b["error_type"] else 0
                    changes.append({"condition": c, "sample_id": sid, "style": st, "entity_type": ref["entity_type"],
                                    "label": ref.get("label"), "gold_value": ref["gold_value"], "pairing": it["pairing"],
                                    "v4_whisper_value": a.get("whisper_value") if a else None, "v4_status": sa,
                                    "s1_whisper_value": b.get("whisper_value") if b else None, "s1_status": sb,
                                    "weight_change": wb - wa,
                                    "context_s1": context(text, e1, ref["entity_type"], b.get("whisper_value") if b else None),
                                    "transcript": text})
        data_v4[c], data_s1[c] = pd.DataFrame(rv), pd.DataFrame(rs)

    # files: inputs, per sample, transitions, changes, error types
    rows = [{"path": str(p), "sha256": sha256_file(p)} for p in input_files(cfg, samples, sources, res_root)]
    pd.DataFrame(rows).drop_duplicates().to_csv(out / "inputs_sha256.csv", index=False)
    pd.DataFrame(per_sample).to_csv(out / "per_sample_ccer.csv", index=False)
    tr = pd.DataFrame([{"condition": k[0], "style": k[1], "entity_type": k[2], "v4": k[3], "s1": k[4],
                        "pairing": k[5], "n": n} for k, n in sorted(trans.items())])
    tr.to_csv(out / "transitions.csv", index=False)
    ch = pd.DataFrame(changes, columns=CHANGE_COLUMNS)
    ch.to_csv(out / "record_changes.csv", index=False, encoding="utf-8-sig")
    et_rows = []
    for (c, st) in sorted({(k[0], k[1]) for k in err_counts}):
        for et in sorted({k[2] for k in err_counts if k[0] == c and k[1] == st}):
            v, s_ = err_counts[(c, st, et, "v4")], err_counts[(c, st, et, "s1")]
            et_rows.append({"condition": c, "style": st, "error_type": et, "v4": v, "s1": s_, "change": s_ - v})
    pd.DataFrame(et_rows).to_csv(out / "error_type_counts.csv", index=False)

    # side-effect audit, stratified sample (fixed columns even when empty)
    se = side_effect_table(ch, ext_s1_cache)
    se.to_csv(out / "side_effect_audit.csv", index=False, encoding="utf-8-sig")
    sdf = stratified_sample(ch, seed)
    sdf.to_csv(out / "omission_to_matched_stratified_sample.csv", index=False, encoding="utf-8-sig")

    # case 15: extraction and final match reported separately; improvement is not required
    c15 = []
    for r in case15.itertuples():
        key = (r.condition, r.sample_id)
        c15.append({"condition": r.condition, "sample_id": r.sample_id, "entity_type": r.entity_type,
                    "gold_value": r.gold_value,
                    **case_check(texts[key], extract_v4(texts[key]), ext_s1_cache[key], closed_v4_cache[key],
                                 closed_s1_cache[key], r.entity_type, r.gold_value)})
    c15df = pd.DataFrame(c15, columns=CASE15_COLUMNS)
    c15df.to_csv(out / "case15_notation_suspects.csv", index=False, encoding="utf-8-sig")

    # pooled, deltas, tests (same functions and seed as analysis.py)
    a_conds = [V4_LABEL] + COND_A
    summary = {}
    for tag, scen in (("primary", scenarios), ("n98", [s for s in scenarios if s not in TTS_SUSPECT_SCENARIOS])):
        p4 = pooled_table(data_v4, scen).rename(columns={"pooled_micro_ccer": "ccer_v4", "sample_mean_ccer": "sample_mean_v4",
                                                         "weighted_errors": "weighted_v4"})
        p1 = pooled_table(data_s1, scen).rename(columns={"pooled_micro_ccer": "ccer_s1", "sample_mean_ccer": "sample_mean_s1",
                                                         "weighted_errors": "weighted_s1"})
        pooled = p4.merge(p1[["condition", "style", "ccer_s1", "sample_mean_s1", "weighted_s1"]], on=["condition", "style"])
        pooled["change"] = (pooled.ccer_s1 - pooled.ccer_v4).round(4)
        ranks = {c: (rank_string(pooled_table({c: data_v4[c]}, scen), c), rank_string(pooled_table({c: data_s1[c]}, scen), c))
                 for c in data_v4}
        pooled["rank_v4"] = pooled.condition.map(lambda c: ranks[c][0])
        pooled["rank_s1"] = pooled.condition.map(lambda c: ranks[c][1])
        pooled.to_csv(out / f"pooled_ccer_{tag}.csv", index=False)
        d4, b4 = joint_bootstrap({c: data_v4[c] for c in a_conds}, scen, n_boot, seed, ci)
        d1, b1 = joint_bootstrap({c: data_s1[c] for c in a_conds}, scen, n_boot, seed, ci)
        dd = d4.merge(d1, on=["condition", "contrast", "role"], suffixes=("_v4", "_s1"))
        dd.to_csv(out / f"delta_bootstrap_{tag}.csv", index=False)
        pairs = [(a, b) for i, a in enumerate(COND_A) for b in COND_A[i + 1:]]
        x4 = delta_differences(b4, {c: data_v4[c] for c in a_conds}, scen, pairs, ci)
        x1 = delta_differences(b1, {c: data_s1[c] for c in a_conds}, scen, pairs, ci)
        xx = x4.merge(x1, on=["comparison", "contrast"], suffixes=("_v4", "_s1"))
        xx.to_csv(out / f"delta_between_systems_{tag}.csv", index=False)
        fr, wil = [], []
        for c in a_conds:
            f, w = v4_tests(data_s1[c][data_s1[c].scenario_id.isin(scen)], c)
            fr.append(f)
            wil.append(w)
        pd.DataFrame(fr).to_csv(out / f"friedman_{tag}.csv", index=False)
        pd.concat(wil).to_csv(out / f"wilcoxon_holm_{tag}.csv", index=False)
        summary[tag] = (pooled, dd, xx, pd.DataFrame(fr), pd.concat(wil))

    root = Path(cfg["paths"]["output_root"])
    pilot = json.load(open(root / "pilot_samples.json", encoding="utf-8"))["sample_ids"]
    pilot_scen = sorted({"_".join(x.split("_")[:2]) for x in pilot})
    brows = []
    for b in COND_B:
        a = B_PAIR[b]
        for scope, scen in (("pilot30_prespecified", pilot_scen), ("all300_extension", scenarios)):
            for side, data in (("v4", data_v4), ("s1", data_s1)):
                pa, pb = pooled_table({a: data[a]}, scen), pooled_table({b: data[b]}, scen)
                for st in STYLES:
                    va = pa[pa["style"] == st].pooled_micro_ccer.iloc[0]
                    vb = pb[pb["style"] == st].pooled_micro_ccer.iloc[0]
                    brows.append({"scorer": side, "scope": scope, "system": a, "style": st, "ko_specified": va,
                                  "not_specified": vb, "difference_B_minus_A": round(vb - va, 4)})
    pd.DataFrame(brows).to_csv(out / "condB_descriptive.csv", index=False)

    meta = {"created_at": now_utc(), "git_commit": git_commit(), "git_dirty_tracked": git_dirty_paths(),
            "status": "post hoc evaluator sensitivity analysis; v4 is the primary analysis (spec Section 13)",
            "code_sha256": {p: sha256_file(Path(p)) for p in CODE_FILES},
            "particles": list(s1mod.PARTICLES), "boundary_after_particle": f"whitespace | [{s1mod.PUNCT}] | end of text",
            "patched_regexes": s1mod.PATCH_LOG, "bootstrap": {"iterations": n_boot, "seed": seed, "ci": ci},
            "stratified_sample": {"per_stratum": SAMPLE_PER_STRATUM, "seed": seed},
            "conditions": list(sources), "n98_excluded": TTS_SUSPECT_SCENARIOS,
            "empty_response_rule": {k: sorted(v) for k, v in EMPTY_RESPONSE_RULE.items()},
            "pairing_rule": "by (entity_type, label, gold_value); duplicate keys with differing judgements "
                            "reported as ambiguous_group, not as individual transitions",
            "n_input_files_hashed": len(rows), "api_calls": 0}
    json.dump(meta, open(out / "meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # console
    pd.set_option("display.width", 220)
    for tag in summary:
        pooled, dd, xx, fr, wil = summary[tag]
        print("\n" + "=" * 110 + f"\n[{tag}] pooled micro-CCER v4 vs S1")
        print(pooled[["condition", "style", "gold_entities", "ccer_v4", "ccer_s1", "change", "rank_v4", "rank_s1"]].to_string(index=False))
        print(f"\n[{tag}] Delta (95% joint bootstrap CI), v4 vs S1")
        print(dd[["condition", "contrast", "estimate_v4", "ci_low_v4", "ci_high_v4", "estimate_s1", "ci_low_s1",
                  "ci_high_s1", "ci_excludes_0_s1"]].to_string(index=False))
        print(f"\n[{tag}] between-system differences of Delta, v4 vs S1")
        print(xx.to_string(index=False))
        print(f"\n[{tag}] Friedman (S1)")
        print(fr.round(6).to_string(index=False))
        print(f"\n[{tag}] Wilcoxon-Holm (S1)")
        print(wil.round(6).to_string(index=False))
    print("\n" + "=" * 110 + "\nclosed-vocab transitions v4 -> S1 (changed only; ambiguous groups listed as groups)")
    tc = tr[tr.v4 != tr.s1].groupby(["condition", "pairing", "v4", "s1"])["n"].sum()
    print(tc.to_string())
    print(f"\nside-effect records/groups (changed, not to matched): {len(se)}")
    if len(se):
        print(se.groupby(["condition", "auto_flag"]).size().to_string())
    lv = c15df.match_level_s1.value_counts().to_dict()
    print(f"\ncase-15: extracted by S1 {int(c15df.extracted_s1.sum())}/{len(c15df)}; gold records matched "
          f"{int(c15df.n_matched_s1.sum())}/{int(c15df.n_gold_records.sum())} (v4 {int(c15df.n_matched_v4.sum())}); "
          f"match level all/partial/none: {lv.get('all', 0)}/{lv.get('partial', 0)}/{lv.get('none', 0)}"
          f"; needs human review: {int(c15df.needs_human_review.sum())}")
    print(c15df[["condition", "sample_id", "entity_type", "gold_value", "extracted_v4", "extracted_s1",
                 "n_matched_s1", "n_gold_records", "match_level_s1", "code_check"]].to_string(index=False))
    print(f"\nstratified review sample: {len(sdf)} records "
          f"({sdf.groupby(['condition', 'style', 'entity_type']).ngroups if len(sdf) else 0} strata)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
