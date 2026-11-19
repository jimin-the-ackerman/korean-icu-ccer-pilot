"""
Quick side-by-side comparison of transcripts across ASR systems (no API calls, no files written).

Diagnostic only - this is NOT the CCER evaluation. For each sample it prints the gold text and each
available ASR transcript, plus three simple indicators:
    nWER        word error rate after the same normalization as src/evaluation/wer_eval.py
    CER         character error rate on the normalized text with spaces removed
    numbers     how many numbers in the gold text appear (as the same digits) in the transcript,
                and which ones are missing. Numbers written in words or Korean numerals
                ("60 milligram" is found, "육십" is not) count as missing here.

Usage:
    python -m src.cross_asr.compare_transcripts
    python -m src.cross_asr.compare_transcripts --samples scenario_012_formal_template,scenario_018_telegraphic_icu
    python -m src.cross_asr.compare_transcripts --asr whisper1,gpt4o_transcribe --summary-only
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import jiwer

from src.cross_asr.common import load_cross_asr_config
from src.evaluation.wer_eval import normalize_text   # same normalization as the v4 WER

DEFAULT_SAMPLES = [
    "scenario_007_clinical_charting",
    "scenario_012_formal_template",
    "scenario_018_telegraphic_icu",
    "scenario_019_clinical_charting",
    "scenario_021_formal_template",
    "scenario_025_telegraphic_icu",
]
DEFAULT_ASR = ["whisper1", "gpt4o_transcribe", "clova_enko"]
NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers(text: str) -> Counter:
    return Counter(NUM.findall(text))


def indicators(gold: str, hyp: str) -> dict:
    g, h = normalize_text(gold), normalize_text(hyp)
    gn, hn = numbers(gold), numbers(hyp)
    found = sum(min(c, hn[k]) for k, c in gn.items())
    missing = sorted((gn - hn).elements(), key=lambda x: float(x))
    return {
        "nWER": jiwer.wer(g, h),
        "CER": jiwer.cer(g.replace(" ", ""), h.replace(" ", "")),
        "numbers_found": found,
        "numbers_total": sum(gn.values()),
        "missing_numbers": missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", default=",".join(DEFAULT_SAMPLES))
    ap.add_argument("--asr", default=",".join(DEFAULT_ASR))
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    cfg = load_cross_asr_config()
    root = Path(cfg["paths"]["output_root"])
    samples = [s.strip() for s in args.samples.split(",") if s.strip()]
    systems = [a.strip() for a in args.asr.split(",") if a.strip()]
    rows = []

    for sid in samples:
        gpath = Path(cfg["paths"]["generated_text_dir"]) / f"{sid}.json"
        if not gpath.exists():
            print(f"STOP: unknown sample {sid}")
            return 1
        gold = json.load(open(gpath, encoding="utf-8"))["text"]
        if not args.summary_only:
            print("=" * 100)
            print(f"{sid}\n[GOLD] {' '.join(gold.split())}")
        for asr in systems:
            p = root / asr / "stt_transcripts" / f"{sid}.json"
            if not p.exists():
                if not args.summary_only:
                    print(f"\n[{asr}] (no transcript yet)")
                continue
            hyp = json.load(open(p, encoding="utf-8"))["whisper_transcript"]
            ind = indicators(gold, hyp)
            rows.append({"sample_id": sid, "asr": asr, **ind})
            if not args.summary_only:
                print(f"\n[{asr}] nWER={ind['nWER']:.3f}  CER={ind['CER']:.3f}  "
                      f"numbers {ind['numbers_found']}/{ind['numbers_total']}  missing={ind['missing_numbers']}")
                print(hyp)
        if not args.summary_only:
            print()

    def summarize(title, keep):
        print("=" * 100)
        print(title)
        print(f"{'asr':18s} {'n':>3s} {'mean nWER':>10s} {'mean CER':>9s} {'numbers found':>15s}")
        for asr in systems:
            r = [x for x in rows if x["asr"] == asr and keep(x["sample_id"])]
            if not r:
                print(f"{asr:18s} {0:>3d} {'-':>10s} {'-':>9s} {'-':>15s}")
                continue
            nf, nt = sum(x["numbers_found"] for x in r), sum(x["numbers_total"] for x in r)
            print(f"{asr:18s} {len(r):>3d} {sum(x['nWER'] for x in r) / len(r):>10.3f} "
                  f"{sum(x['CER'] for x in r) / len(r):>9.3f} {f'{nf}/{nt}':>15s}")

    summarize("SUMMARY - all available transcripts (diagnostic, not CCER)", lambda s: True)
    have = {a: {x["sample_id"] for x in rows if x["asr"] == a} for a in systems}
    present = [a for a in systems if have[a]]
    common = set.intersection(*[have[a] for a in present]) if present else set()
    if present and len(present) < len(systems):
        print(f"note: no transcripts yet for {[a for a in systems if a not in present]}")
    if common and any(have[a] != common for a in present):
        summarize(f"SUMMARY - same {len(common)} samples for {present} (use this for comparison)",
                  lambda s: s in common)
    return 0


if __name__ == "__main__":
    sys.exit(main())
