"""KOSMI 2026 poster tables: post hoc recomputation from saved outputs (spec Section 13.2).

Recomputes, for the September primary run (three styles + Hybrid) and Condition A of the
Cross-ASR study (whisper1, gpt4o_transcribe, chirp3_ko):
  - nWER (normalize_text + jiwer, mean over samples), pooled Entity F1,
  - Micro- and Macro-CCER (Macro = unweighted mean of entity-type CCERs, as in SAP5)
    under the v4 scorer (saved matches) and under S1 (Korean particle attachment, Section 13:
    closed-vocab re-extraction with ko_particle_extractor; open-vocab matches reused),
  - entity-type CCER under v4 and S1.

No API call. Reads saved transcripts, scaffolds and matched entities only. Before computing S1,
the saved v4 closed-vocab matches are re-derived from the transcript and must reproduce exactly.

Usage:  python -m src.cross_asr.kosmi2026_tables            (writes results/cross_asr/kosmi2026_tables/)
        python -m src.cross_asr.kosmi2026_tables --dry-run  (prints only)
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import jiwer

from src.cross_asr.common import load_cross_asr_config
from src.cross_asr import ko_particle_extractor as s1
from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities as extract_v4
from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab
from src.evaluation.ccer_eval import ERROR_WEIGHTS
from src.evaluation.flatten_matches import flatten_all_matches
from src.evaluation.wer_eval import normalize_text
from src.matching.entity_matcher import match_closed_vocab

STYLES = ["formal_template", "clinical_charting", "telegraphic_icu"]
OUT_DIR = Path("results/cross_asr/kosmi2026_tables")


def style_of(sid):
    return "_".join(sid.split("_")[2:])


def conditions(paths):
    root = Path(paths["output_root"])
    sept_ent, sept_stt = Path(paths["original_entities_dir"]), Path("data/stt_transcripts")
    out = [("whisper1_v4_sept", sept_ent, sept_stt, STYLES + ["hybrid"])]
    out += [(a, root / a / "entities", root / a / "stt_transcripts", STYLES)
            for a in ("whisper1", "gpt4o_transcribe", "chirp3_ko")]
    return out


def add(agg, recs):
    for r in recs:
        c = agg[r["entity_type"]]
        if r["gold_value"] is not None:
            c[1] += 1
        if r["error_type"] is not None:
            c[0] += ERROR_WEIGHTS.get(r["error_type"], 0)


def micro_macro(agg):
    micro = sum(v[0] for v in agg.values()) / sum(v[1] for v in agg.values())
    types = [v[0] / v[1] for v in agg.values() if v[1] > 0]
    return micro, sum(types) / len(types), len(types)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    paths = load_cross_asr_config()["paths"]
    gen_dir = Path(paths["generated_text_dir"])
    if not args.dry_run and OUT_DIR.exists():
        sys.exit(f"STOP: {OUT_DIR} already exists; not overwriting.")

    overall, by_type = [], []
    for cond, ent_dir, stt_dir, styles in conditions(paths):
        files = sorted(f for f in ent_dir.glob("scenario_*_matched.json")
                       if style_of(f.name[: -len("_matched.json")]) in styles)
        expected = 100 * len(styles)
        if len(files) != expected:
            sys.exit(f"STOP [{cond}]: expected {expected} matched files in {ent_dir}, found {len(files)}")
        wer, recs = defaultdict(list), defaultdict(list)
        agg = {k: defaultdict(lambda: defaultdict(lambda: [0.0, 0])) for k in ("v4", "s1")}
        bad = 0
        for f in files:
            m = json.load(open(f, encoding="utf-8"))
            sid = m["sample_id"]
            st = style_of(sid)
            text = json.load(open(stt_dir / f"{sid}.json", encoding="utf-8"))["whisper_transcript"]
            ref = json.load(open(gen_dir / f"{sid}.json", encoding="utf-8"))["text"]
            wer[st].append(jiwer.wer(normalize_text(ref), normalize_text(text)))
            gold = scaffold_to_closed_vocab(json.load(open(Path("data/scenarios") / f"{sid[:12]}.json", encoding="utf-8")))
            if match_closed_vocab(gold, extract_v4(text)) != m["closed_vocab_matches"]:
                bad += 1
            m_s1 = {"closed_vocab_matches": match_closed_vocab(gold, s1.extract_closed_vocab_entities_s1(text)),
                    "open_vocab_matches": m["open_vocab_matches"]}
            r4 = flatten_all_matches(m)
            recs[st].extend(r4)
            add(agg["v4"][st], r4)
            add(agg["s1"][st], flatten_all_matches(m_s1))
        print(f"[{cond}] v4 closed-vocab reproduction failures: {bad}/{len(files)}")
        if bad:
            sys.exit("STOP: saved v4 matches do not reproduce; S1 comparison would be invalid.")
        for st in styles:
            R = recs[st]
            g = sum(1 for r in R if r["gold_value"] is not None)
            h = sum(1 for r in R if r["whisper_value"] is not None)
            tp = sum(1 for r in R if r["match_status"] == "matched")
            p, rc = (tp / h if h else 0), (tp / g if g else 0)
            f1 = 2 * p * rc / (p + rc) if p + rc else 0
            mi4, ma4, nt = micro_macro(agg["v4"][st])
            mi1, ma1, _ = micro_macro(agg["s1"][st])
            overall.append({"condition": cond, "style": st, "n_samples": len(wer[st]), "gold_entities": g,
                            "nwer": round(sum(wer[st]) / len(wer[st]), 4), "entity_f1": round(f1, 4),
                            "micro_ccer_v4": round(mi4, 4), "macro_ccer_v4": round(ma4, 4),
                            "micro_ccer_s1": round(mi1, 4), "macro_ccer_s1": round(ma1, 4), "n_entity_types": nt})
            for et in sorted(agg["v4"][st]):
                w4, g4 = agg["v4"][st][et]
                w1, g1 = agg["s1"][st][et]
                by_type.append({"condition": cond, "style": st, "entity_type": et, "gold_v4": g4,
                                "weighted_v4": w4, "ccer_v4": round(w4 / g4, 4) if g4 else "",
                                "gold_s1": g1, "weighted_s1": w1, "ccer_s1": round(w1 / g1, 4) if g1 else ""})

    cols = ["condition", "style", "nwer", "entity_f1", "micro_ccer_v4", "macro_ccer_v4", "micro_ccer_s1", "macro_ccer_s1"]
    print("\n" + " ".join(f"{c:>17s}" for c in cols))
    for r in overall:
        print(" ".join(f"{str(r[c]):>17s}" for c in cols))
    if args.dry_run:
        return
    OUT_DIR.mkdir(parents=True)
    for name, rows in (("overall_metrics.csv", overall), ("entity_type_ccer.csv", by_type)):
        with open(OUT_DIR / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"\nwrote {OUT_DIR}/overall_metrics.csv ({len(overall)} rows), entity_type_ccer.csv ({len(by_type)} rows)")


if __name__ == "__main__":
    main()
