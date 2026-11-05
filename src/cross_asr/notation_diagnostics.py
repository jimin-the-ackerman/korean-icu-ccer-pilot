"""
Notation diagnostics (docs/cross_asr_spec.md Section 8; RQ3). No API call; nothing in the primary
evaluation is changed and no new normalization rule is adopted.

Part 1  Notation counts over each condition's 300 transcripts, by style: Hangul particle attached to
        an ASCII token ("2g을", "IV로"), Korean unit words ("밀리그램", "퍼센트"), Sino-Korean number
        words ("육십", "백이십"), Korean transliterations of devices/abbreviations ("C라인",
        "캐테터", "네이절") - forms the v4 closed-vocab extractor does not read.

Part 2  Diagnostic bound for the closed-vocab part only: the v4 extractor and v4 matcher are re-run
        on a "lenient" copy of each transcript in which only the forms of Part 1 are rewritten
        (a space between an ASCII token and a following Hangul particle; device aliases; Korean unit
        words). Open-vocab (LLM) results are taken unchanged from the match files. The resulting
        CCER shows how much of each condition's CCER, and of the style contrasts, depends on
        notation the v4 extractor cannot read. It is an upper-bound style diagnostic, not a
        corrected score: the lenient rewrite can also create matches or insertions of its own.
        Sino-Korean number words are counted only (not rewritten).

Part 3  Case-review sheets (spec Section 8 table, fixed seed) for manual labelling:
        10 random transcripts (all entity records), 5 random error records, 5 notation-suspect
        records (closed-vocab records whose v4 judgement changes under the lenient rewrite), per
        Condition A system. Label column: ASR error / evaluator miss due to notation / correct /
        undetermined. Strata are not pooled.

Output: results/cross_asr/notation_diagnostics/  (stops if it exists; use --out)
Usage:  python -m src.cross_asr.notation_diagnostics
"""
import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from src.cross_asr.analysis import STYLES, COND_A, COND_B, joint_bootstrap, pooled_table
from src.cross_asr.common import load_cross_asr_config, primary_samples, git_commit, now_utc
from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities
from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab
from src.evaluation.ccer_eval import ERROR_WEIGHTS
from src.evaluation.flatten_matches import flatten_all_matches
from src.matching.entity_matcher import match_closed_vocab

# ---------- Part 1 patterns (counted) ----------
PATTERNS = {
    "particle_after_ascii": re.compile(r"[A-Za-z0-9%°℃][가-힣]"),
    "korean_unit_word": re.compile(r"밀리그램|밀리리터|마이크로그램|그램|리터|퍼센트|프로(?![가-힣])"),
    "sino_korean_number": re.compile(r"(?<![가-힣])(?:[일이삼사오육칠팔구]?[십백천])+[일이삼사오육칠팔구]?(?![가-힣])"),
    "device_transliteration": re.compile(r"[Cc]\s*-?\s*라인|씨\s*라인|캐테터|캔?눌라|카눌라|네이절|나잘|네이잘"),
}

# ---------- Part 2 lenient rewrite (diagnostic only) ----------
LENIENT_STEPS = [
    ("device alias C-line", re.compile(r"[Cc]\s*-?\s*라인|씨\s*라인"), "C-line"),
    ("device alias catheter", re.compile(r"캐테터"), "카테터"),
    ("device alias cannula", re.compile(r"캔?눌라|카눌라|캐눌라"), "캐뉼라"),
    ("device alias nasal", re.compile(r"(?:네이절|나잘|네이잘)\s*"), "비강 "),
    ("unit word mg", re.compile(r"(\d)\s*밀리그램"), r"\1mg"),
    ("unit word mL", re.compile(r"(\d)\s*밀리리터"), r"\1mL"),
    ("unit word mcg", re.compile(r"(\d)\s*마이크로그램"), r"\1mcg"),
    ("unit word g", re.compile(r"(\d)\s*그램"), r"\1g"),
    ("unit word percent", re.compile(r"(\d)\s*(?:퍼센트|프로(?![가-힣]))"), r"\1%"),
    ("space before particle", re.compile(r"([A-Za-z0-9%°℃])([가-힣])"), r"\1 \2"),
]


def lenient(text: str) -> str:
    for _, pat, rep in LENIENT_STEPS:
        text = pat.sub(rep, text)
    return text


def weighted_and_gold(records: list) -> tuple[float, int]:
    gold = sum(1 for r in records if r["gold_value"] is not None)
    w = sum(ERROR_WEIGHTS.get(r["error_type"], 0) for r in records if r["error_type"] is not None)
    return float(w), gold


def rec_key(r: dict) -> tuple:
    return (r["entity_type"], r.get("label"), r["gold_value"], r["whisper_value"], r["match_status"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = load_cross_asr_config()
    out = Path(args.out or Path(cfg["paths"]["results_root"]) / "notation_diagnostics")
    if out.exists():
        print(f"STOP: {out} already exists (not overwritten) - use --out")
        return 1
    root = Path(cfg["paths"]["output_root"])
    samples = primary_samples(cfg)
    scenarios = sorted({s["scenario_id"] for s in samples})
    scaffolds = {sc: json.load(open(Path(cfg["paths"]["scenarios_dir"]) / f"{sc}.json", encoding="utf-8"))
                 for sc in scenarios}
    conds = [c for c in COND_A + COND_B if (root / c / "entities").exists()]

    count_rows, bound_rows, data_v4, data_len, changed = [], [], {}, {}, {}
    for c in conds:
        rows_v4, rows_len, ch = [], [], []
        cnt = {st: Counter() for st in STYLES}
        for s in samples:
            sid, st = s["sample_id"], s["style_condition"]
            tp = root / c / "stt_transcripts" / f"{sid}.json"
            text = json.load(open(tp, encoding="utf-8"))["whisper_transcript"] if tp.exists() else ""
            for name, pat in PATTERNS.items():
                cnt[st][name] += len(pat.findall(text))
            cnt[st]["transcripts"] += 1
            m = json.load(open(root / c / "entities" / f"{sid}_matched.json", encoding="utf-8"))
            w, g = weighted_and_gold(flatten_all_matches(m))
            rows_v4.append({**s, "weighted": w, "gold": g, "ccer": w / g})
            gold_closed = scaffold_to_closed_vocab(scaffolds[s["scenario_id"]])
            closed_v4 = m["closed_vocab_matches"]
            closed_len = match_closed_vocab(gold_closed, extract_closed_vocab_entities(lenient(text)))
            m_len = {"closed_vocab_matches": closed_len, "open_vocab_matches": m["open_vocab_matches"]}
            wl, gl = weighted_and_gold(flatten_all_matches(m_len))
            rows_len.append({**s, "weighted": wl, "gold": gl, "ccer": wl / gl})
            a, b = Counter(map(rec_key, closed_v4)), Counter(map(rec_key, closed_len))
            for r in closed_v4:
                if (a - b)[rec_key(r)] > 0 and r["match_status"] != "matched" and r["gold_value"] is not None:
                    new_r = next((x for x in closed_len if x["entity_type"] == r["entity_type"]
                                  and x.get("label") == r.get("label") and x["gold_value"] == r["gold_value"]), None)
                    ch.append({"sample_id": sid, "style": st, "entity_type": r["entity_type"],
                               "label": r.get("label"), "gold_value": r["gold_value"],
                               "v4_whisper_value": r["whisper_value"], "v4_status": r["match_status"],
                               "v4_error_type": r["error_type"],
                               "lenient_whisper_value": new_r["whisper_value"] if new_r else None,
                               "lenient_status": new_r["match_status"] if new_r else None,
                               "lenient_error_type": new_r["error_type"] if new_r else None})
            if not tp.exists():
                rows_len[-1].update(weighted=w, gold=g, ccer=w / g)     # empty-response rule sample
        for st in STYLES:
            n = cnt[st]["transcripts"]
            count_rows.append({"condition": c, "style": st, "transcripts": n,
                               **{f"{k}_per_transcript": round(cnt[st][k] / n, 3) for k in PATTERNS}})
        data_v4[c], data_len[c], changed[c] = pd.DataFrame(rows_v4), pd.DataFrame(rows_len), ch
        sub = pd.DataFrame(ch)
        for st in STYLES:
            k = sub[sub["style"] == st] if len(sub) else sub
            bound_rows.append({"condition": c, "style": st, "closed_records_changed": len(k),
                               **{f"changed_{et}": int((k["entity_type"] == et).sum()) if len(k) else 0
                                  for et in ("route", "frequency", "device", "dose", "vital_sign")}})

    out.mkdir(parents=True)
    pd.DataFrame(count_rows).to_csv(out / "part1_notation_counts.csv", index=False)
    pv4, plen = pooled_table(data_v4, scenarios), pooled_table(data_len, scenarios)
    comp = pv4[["condition", "style", "pooled_micro_ccer"]].rename(columns={"pooled_micro_ccer": "ccer_v4"}).merge(
        plen[["condition", "style", "pooled_micro_ccer"]].rename(columns={"pooled_micro_ccer": "ccer_lenient_closed"}),
        on=["condition", "style"])
    comp["difference"] = (comp.ccer_lenient_closed - comp.ccer_v4).round(4)
    comp = comp.merge(pd.DataFrame(bound_rows), on=["condition", "style"])
    comp.to_csv(out / "part2_lenient_closed_bound.csv", index=False)
    acfg = cfg["analysis"]
    a_conds = [c for c in COND_A if c in data_len]
    d_v4, _ = joint_bootstrap({c: data_v4[c] for c in a_conds}, scenarios, int(acfg["bootstrap_iterations"]),
                              int(acfg["bootstrap_seed"]), float(acfg["ci_level"]))
    d_len, _ = joint_bootstrap({c: data_len[c] for c in a_conds}, scenarios, int(acfg["bootstrap_iterations"]),
                               int(acfg["bootstrap_seed"]), float(acfg["ci_level"]))
    dd = d_v4.merge(d_len, on=["condition", "contrast", "role"], suffixes=("_v4", "_lenient"))
    dd.to_csv(out / "part2_delta_v4_vs_lenient_condA.csv", index=False)
    pd.concat([pd.DataFrame(changed[c]).assign(condition=c) for c in conds if changed[c]]).to_csv(
        out / "part2_changed_closed_records.csv", index=False)

    # Part 3: case-review sheets (Condition A), fixed seed
    ccfg = cfg["case_review"]
    for c in a_conds:
        rng = random.Random(f"{ccfg['seed']}-{c}")
        rows = []
        all_recs = []
        for s in samples:
            m = json.load(open(root / c / "entities" / f"{s['sample_id']}_matched.json", encoding="utf-8"))
            for r in flatten_all_matches(m):
                all_recs.append({"sample_id": s["sample_id"], "style": s["style_condition"], **r})
        ids = sorted({s["sample_id"] for s in samples})
        pick = set(rng.sample(ids, ccfg["n_random_transcripts"]))
        rows += [{"stratum": "random_transcript", **r} for r in all_recs if r["sample_id"] in pick]
        errs = [r for r in all_recs if r["error_type"] is not None]
        rows += [{"stratum": "random_error_record", **r} for r in rng.sample(errs, ccfg["n_random_error_records"])]
        susp = changed[c]
        rows += [{"stratum": "notation_suspect_record", **r}
                 for r in rng.sample(susp, min(ccfg["n_notation_suspect_records"], len(susp)))]
        sheet = pd.DataFrame(rows)
        texts = {sid: json.load(open(root / c / "stt_transcripts" / f"{sid}.json", encoding="utf-8"))["whisper_transcript"]
                 for sid in sheet["sample_id"].unique() if (root / c / "stt_transcripts" / f"{sid}.json").exists()}
        sheet["transcript"] = sheet["sample_id"].map(texts)
        sheet["label"] = ""      # ASR error / evaluator miss due to notation / correct / undetermined
        sheet.to_csv(out / f"part3_case_review_{c}.csv", index=False, encoding="utf-8-sig")

    json.dump({"created_at": now_utc(), "git_commit": git_commit(), "conditions": conds,
               "lenient_steps": [n for n, _, _ in LENIENT_STEPS],
               "note": "diagnostic only; primary CCER unchanged; open-vocab results reused unchanged"},
              open(out / "meta.json", "w", encoding="utf-8"), indent=2)

    pd.set_option("display.width", 200)
    print("=== Part 1: notation per transcript (forms the v4 closed-vocab extractor does not read) ===")
    print(pd.DataFrame(count_rows).to_string(index=False))
    print("\n=== Part 2: pooled CCER, v4 vs lenient closed-vocab rewrite (diagnostic bound) ===")
    print(comp[["condition", "style", "ccer_v4", "ccer_lenient_closed", "difference", "closed_records_changed",
                "changed_route", "changed_frequency", "changed_device", "changed_dose", "changed_vital_sign"]].to_string(index=False))
    print("\n=== Part 2: Condition A contrasts, v4 vs lenient ===")
    print(dd[["condition", "contrast", "estimate_v4", "ci_low_v4", "ci_high_v4",
              "estimate_lenient", "ci_low_lenient", "ci_high_lenient"]].to_string(index=False))
    allch = pd.concat([pd.DataFrame(changed[c]).assign(condition=c) for c in conds if changed[c]])
    if len(allch):
        print("\n=== Part 2: changed closed-vocab gold records, v4 status -> lenient status ===")
        print(allch.groupby(["condition", "style", "v4_status", "lenient_status"], dropna=False).size()
              .unstack(fill_value=0).to_string())
    print(f"\nPart 3 sheets: {[f'part3_case_review_{c}.csv' for c in a_conds]} (label column empty)")
    print(f"written: {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
