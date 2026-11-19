"""
Audio manifest + pilot list for the Cross-ASR experiment (no API calls).

For the 300 primary samples (Hybrid excluded) it records, per sample:
audio path / size / SHA-256 / duration / decode check, and whether the matching
scaffold, gold text, original whisper-1 transcript and original v4 matched file exist.
It also fixes the 30-sample pilot set (10 scenarios x 3 styles, seed in configs/cross_asr.yaml).

Outputs (new files only, in data/cross_asr/):
    audio_manifest.csv      per-sample record
    pilot_samples.json      pilot scenarios and samples
    manifest_summary.json   counts + SHA-256 of the two files above (written last = completion marker)

Safe writing: all three files are first written to hidden temporary files (fsync). Only after
all three are written are they moved into place with os.replace, manifest_summary.json last.
Each os.replace is atomic for that single file, but the three moves together are NOT one atomic
operation: if the process fails between moves, a partial set of final files can remain.
This is handled on the next run: outputs are treated as complete only if all three files exist
and the summary's recorded hashes match the other two; otherwise the script stops (partial
outputs or leftover temporary files) and writes nothing. A failure while writing the
temporaries leaves no final file.

Re-running never overwrites. If complete outputs exist, it verifies them:
    - the three files are mutually consistent (hashes, counts, pilot)
    - the current dataset has exactly the same samples (sample_id, scenario_id, style)
    - structure: 300 samples, 100 scenarios, 100 per style, no duplicates
    - every audio file still has the recorded SHA-256
If outputs are partial or inconsistent, it stops and writes nothing.

Usage:
    python -m src.cross_asr.manifest
"""
import csv
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from src.cross_asr.common import (
    load_cross_asr_config, primary_samples, pilot_scenarios, sha256_file,
    git_commit, now_utc,
)

FIELDS = ["sample_id", "scenario_id", "style_condition", "audio_path", "audio_exists",
          "bytes", "sha256", "duration_sec", "decode_ok", "scaffold_exists",
          "gold_text_nonempty", "original_transcript_exists", "original_matched_exists"]
MANIFEST, PILOT, SUMMARY = "audio_manifest.csv", "pilot_samples.json", "manifest_summary.json"
N_SCENARIOS, N_PER_STYLE = 100, 100


# ---------- checks ----------

def probe_duration(path: Path) -> str:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "error"


def decode_ok(path: Path) -> str:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True)
    return "yes" if (r.returncode == 0 and not r.stderr.strip()) else "no"


def structure_errors(rows: list[dict], styles: list[str]) -> list[str]:
    """300 samples, 100 scenarios, 100 per style, no duplicate sample_id or (scenario, style),
    every scenario has exactly one sample per style."""
    errs = []
    n_expected = N_SCENARIOS * len(styles)
    if len(rows) != n_expected:
        errs.append(f"n_samples={len(rows)} (expected {n_expected})")
    dup_ids = [k for k, v in Counter(r["sample_id"] for r in rows).items() if v > 1]
    if dup_ids:
        errs.append(f"duplicate sample_id: {dup_ids[:5]}")
    dup_pairs = [k for k, v in Counter((r["scenario_id"], r["style_condition"]) for r in rows).items() if v > 1]
    if dup_pairs:
        errs.append(f"duplicate (scenario_id, style): {dup_pairs[:5]}")
    scen = {r["scenario_id"] for r in rows}
    if len(scen) != N_SCENARIOS:
        errs.append(f"n_scenarios={len(scen)} (expected {N_SCENARIOS})")
    per_style = Counter(r["style_condition"] for r in rows)
    for st in styles:
        if per_style.get(st, 0) != N_PER_STYLE:
            errs.append(f"style {st}: {per_style.get(st, 0)} (expected {N_PER_STYLE})")
    extra = set(per_style) - set(styles)
    if extra:
        errs.append(f"unexpected styles: {sorted(extra)}")
    by_scen = {}
    for r in rows:
        by_scen.setdefault(r["scenario_id"], []).append(r["style_condition"])
    bad = [s for s, sts in by_scen.items() if sorted(sts) != sorted(styles)]
    if bad:
        errs.append(f"scenarios without exactly one sample per style: {bad[:5]}")
    return errs


def pilot_errors(pilot: dict, rows: list[dict], cfg: dict) -> list[str]:
    """Pilot = the seeded 10 scenarios, each with exactly one sample per style (30 total)."""
    errs = []
    styles = cfg["styles"]
    expected_ids = pilot_scenarios(cfg, [r["scenario_id"] for r in rows])
    if pilot.get("seed") != cfg["pilot"]["seed"]:
        errs.append(f"pilot seed {pilot.get('seed')} != config seed {cfg['pilot']['seed']}")
    if sorted(pilot.get("scenario_ids", [])) != expected_ids:
        errs.append("pilot scenario_ids differ from seeded selection")
    if len(set(pilot.get("scenario_ids", []))) != cfg["pilot"]["n_scenarios"]:
        errs.append(f"pilot has {len(set(pilot.get('scenario_ids', [])))} scenarios "
                    f"(expected {cfg['pilot']['n_scenarios']})")
    lookup = {r["sample_id"]: r for r in rows}
    samples = pilot.get("sample_ids", [])
    if len(samples) != len(set(samples)):
        errs.append("duplicate pilot sample_ids")
    unknown = [s for s in samples if s not in lookup]
    if unknown:
        errs.append(f"pilot samples not in manifest: {unknown[:5]}")
    for scen in pilot.get("scenario_ids", []):
        sts = sorted(lookup[s]["style_condition"] for s in samples
                     if s in lookup and lookup[s]["scenario_id"] == scen)
        if sts != sorted(styles):
            errs.append(f"pilot {scen}: styles {sts} (expected one each of {styles})")
    if len(samples) != cfg["pilot"]["n_scenarios"] * len(styles):
        errs.append(f"pilot n_samples={len(samples)} (expected {cfg['pilot']['n_scenarios'] * len(styles)})")
    return errs


# ---------- build ----------

def build_rows(cfg: dict) -> list[dict]:
    p = cfg["paths"]
    rows = []
    for s in primary_samples(cfg):
        sid, scen = s["sample_id"], s["scenario_id"]
        audio = Path(p["audio_dir"]) / f"{sid}.mp3"
        gold = json.load(open(Path(p["generated_text_dir"]) / f"{sid}.json", encoding="utf-8"))
        exists = audio.exists()
        row = {
            **s,
            "audio_path": str(audio),
            "audio_exists": exists,
            "bytes": audio.stat().st_size if exists else "",
            "sha256": sha256_file(audio) if exists else "",
            "duration_sec": probe_duration(audio) if exists else "",
            "decode_ok": decode_ok(audio) if exists else "",
            "scaffold_exists": (Path(p["scenarios_dir"]) / f"{scen}.json").exists(),
            "gold_text_nonempty": bool(gold.get("text", "").strip()),
            "original_transcript_exists": (Path(p["original_stt_dir"]) / f"{sid}.json").exists(),
            "original_matched_exists": (Path(p["original_entities_dir"]) / f"{sid}_matched.json").exists(),
        }
        rows.append(row)
        print(f"[{len(rows)}] {sid} sha256={row['sha256'][:12]} decode={row['decode_ok']}")
    return rows


def content_counts(rows: list[dict]) -> dict:
    def count(key, val=True):
        return sum(1 for r in rows if r[key] == val)
    return {
        "n_samples": len(rows),
        "n_scenarios": len({r["scenario_id"] for r in rows}),
        "by_style": dict(sorted(Counter(r["style_condition"] for r in rows).items())),
        "audio_exists": count("audio_exists"),
        "decode_ok_yes": count("decode_ok", "yes"),
        "scaffold_exists": count("scaffold_exists"),
        "gold_text_nonempty": count("gold_text_nonempty"),
        "original_transcript_exists": count("original_transcript_exists"),
        "original_matched_exists": count("original_matched_exists"),
    }


def _write_tmp(path: Path, write_fn) -> Path:
    """Write to a hidden temporary file next to `path` and fsync it; returns the temp path."""
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            write_fn(f)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise
    return tmp


def create(cfg: dict, out: Path) -> int:
    if not (shutil.which("ffprobe") and shutil.which("ffmpeg")):
        print("STOP: ffmpeg/ffprobe not found - install with: sudo apt install ffmpeg")
        return 1

    rows = build_rows(cfg)
    counts = content_counts(rows)
    pilot_ids = pilot_scenarios(cfg, [r["scenario_id"] for r in rows])
    pilot = {"seed": cfg["pilot"]["seed"], "scenario_ids": pilot_ids,
             "sample_ids": sorted(r["sample_id"] for r in rows if r["scenario_id"] in pilot_ids)}

    print("\n=== counts ===")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(f"pilot scenarios ({len(pilot_ids)}): {pilot_ids}")

    errs = structure_errors(rows, cfg["styles"]) + pilot_errors(pilot, rows, cfg)
    for key in ["audio_exists", "decode_ok_yes", "scaffold_exists", "gold_text_nonempty",
                "original_transcript_exists", "original_matched_exists"]:
        if counts[key] != len(rows):
            errs.append(f"{key}={counts[key]} (expected {len(rows)})")
    if errs:
        print("\n".join(["", "MANIFEST INCOMPLETE - nothing written:"] + [f"  - {e}" for e in errs]))
        return 1

    out.mkdir(parents=True, exist_ok=True)

    def write_csv(f):
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    # Stage all three files as temporaries first, then move them into place (summary last).
    # A failure while staging leaves no final file. The moves are atomic per file but not as a
    # group: a failure between moves can leave partial outputs, which main() detects and refuses.
    staged = []
    try:
        staged.append((_write_tmp(out / MANIFEST, write_csv), out / MANIFEST))
        staged.append((_write_tmp(out / PILOT, lambda f: json.dump(pilot, f, ensure_ascii=False, indent=2)),
                       out / PILOT))
        summary = {
            **counts,
            "pilot_scenarios": pilot_ids,
            "files_sha256": {MANIFEST: sha256_file(staged[0][0]), PILOT: sha256_file(staged[1][0])},
            "created_at": now_utc(),
            "git_commit": git_commit(),
            "config_version": cfg["version"],
        }
        staged.append((_write_tmp(out / SUMMARY, lambda f: json.dump(summary, f, ensure_ascii=False, indent=2)),
                       out / SUMMARY))
        for tmp, final in staged:          # MANIFEST, PILOT, then SUMMARY (completion marker)
            os.replace(tmp, final)
    finally:
        for tmp, _ in staged:
            if tmp.exists():
                tmp.unlink()
    print(f"\nMANIFEST OK -> {out}  ({MANIFEST}, {PILOT}, {SUMMARY})")
    return 0


# ---------- verify ----------

def verify(cfg: dict, out: Path) -> int:
    errs = []
    summary = json.load(open(out / SUMMARY, encoding="utf-8"))
    recorded = summary.get("files_sha256", {})
    for name in (MANIFEST, PILOT):
        if sha256_file(out / name) != recorded.get(name):
            errs.append(f"{name} does not match the hash recorded in {SUMMARY}")
    if errs:
        return report(errs, "files inconsistent")

    stored = list(csv.DictReader(open(out / MANIFEST, encoding="utf-8")))
    pilot = json.load(open(out / PILOT, encoding="utf-8"))

    # 1) structure of stored manifest + pilot
    errs += structure_errors(stored, cfg["styles"])
    errs += pilot_errors(pilot, stored, cfg)

    # 2) stored counts == summary counts
    stored_counts = {"n_samples": len(stored),
                     "n_scenarios": len({r["scenario_id"] for r in stored}),
                     "by_style": dict(sorted(Counter(r["style_condition"] for r in stored).items()))}
    for k, v in stored_counts.items():
        if summary.get(k) != v:
            errs.append(f"summary {k}={summary.get(k)} but manifest has {v}")
    if summary.get("pilot_scenarios") != pilot.get("scenario_ids"):
        errs.append("summary pilot_scenarios differ from pilot_samples.json")

    # 3) current dataset == stored manifest (exact sample set)
    current = {(s["sample_id"], s["scenario_id"], s["style_condition"]) for s in primary_samples(cfg)}
    saved = {(r["sample_id"], r["scenario_id"], r["style_condition"]) for r in stored}
    if current != saved:
        errs.append(f"dataset differs from manifest: only in current={sorted(current - saved)[:3]}, "
                    f"only in manifest={sorted(saved - current)[:3]}")

    # 4) audio unchanged
    missing, changed = [], []
    for r in stored:
        a = Path(r["audio_path"])
        if not a.exists():
            missing.append(r["sample_id"])
        elif sha256_file(a) != r["sha256"]:
            changed.append(r["sample_id"])
    if missing:
        errs.append(f"missing audio: {len(missing)} {missing[:5]}")
    if changed:
        errs.append(f"audio hash changed: {len(changed)} {changed[:5]}")

    print(f"verify existing outputs in {out} (not overwritten)")
    print(f"  samples={len(stored)} scenarios={stored_counts['n_scenarios']} by_style={stored_counts['by_style']}")
    print(f"  pilot scenarios={pilot.get('scenario_ids')}")
    print(f"  audio missing={len(missing)} changed={len(changed)}")
    return report(errs, "MANIFEST VERIFIED")


def report(errs: list[str], ok_msg: str) -> int:
    if errs:
        print("MANIFEST MISMATCH:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(ok_msg)
    return 0


def main() -> int:
    cfg = load_cross_asr_config()
    out = Path(cfg["paths"]["output_root"])
    present = [n for n in (MANIFEST, PILOT, SUMMARY) if (out / n).exists()]
    leftovers = sorted(p.name for p in out.glob(".*.tmp-*")) if out.exists() else []
    if leftovers:
        print(f"STOP: leftover temporary files from an interrupted run: {leftovers}")
        print("      move them out of data/cross_asr/ and run again (nothing written)")
        return 1
    if not present:
        return create(cfg, out)
    if len(present) < 3:
        missing = sorted({MANIFEST, PILOT, SUMMARY} - set(present))
        print(f"STOP: partial manifest outputs (present={present}, missing={missing}).")
        print("      Not treated as valid; move the present files out of data/cross_asr/ "
              "and run again (nothing written)")
        return 1
    return verify(cfg, out)


if __name__ == "__main__":
    sys.exit(main())
