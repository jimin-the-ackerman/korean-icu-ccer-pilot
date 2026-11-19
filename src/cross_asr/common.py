"""Shared helpers for the Cross-ASR Robustness experiment (docs/cross_asr_spec.md).

Only reads existing project files; never writes outside data/cross_asr/ or results/cross_asr/.
"""
import hashlib
import json
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

CROSS_ASR_CONFIG = "configs/cross_asr.yaml"


def load_cross_asr_config(path: str = CROSS_ASR_CONFIG) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_base_config(cfg: dict) -> dict:
    with open(cfg["base_config"], "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def primary_samples(cfg: dict) -> list[dict]:
    """Primary samples (3 styles x 100 scenarios) from generated_text, sorted by sample_id."""
    styles = set(cfg["styles"])
    rows = []
    for f in sorted(Path(cfg["paths"]["generated_text_dir"]).glob("*.json")):
        if f.name == "generation_log.json":
            continue
        rec = json.load(open(f, encoding="utf-8"))
        if rec.get("style_condition") in styles:
            rows.append({
                "sample_id": rec["sample_id"],
                "scenario_id": rec["scenario_id"],
                "style_condition": rec["style_condition"],
            })
    return rows


def pilot_scenarios(cfg: dict, all_scenario_ids: list[str]) -> list[str]:
    rng = random.Random(cfg["pilot"]["seed"])
    return sorted(rng.sample(sorted(set(all_scenario_ids)), cfg["pilot"]["n_scenarios"]))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def git_dirty_paths() -> list[str]:
    try:
        out = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True, stderr=subprocess.DEVNULL)
        return [line[3:] for line in out.splitlines()]
    except Exception:
        return ["unknown"]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
