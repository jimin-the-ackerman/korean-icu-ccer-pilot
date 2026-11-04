"""
Diagnostic only: transcribe ONE audio file with CLOVA Speech using a different `language` value
and compare it with the existing clova_enko output. Not part of the primary Cross-ASR analysis.

- Does not change configs/cross_asr.yaml, transcribe.py or any primary output.
- Uses the same request code as transcribe.py (ClovaBackend, endpoint, diarization setting);
  only params["language"] is replaced.
- Allowed language values are the ones listed in the Ncloud API docs for local file recognition:
  ko-KR, en-US, enko, ja, zh-cn, zh-tw (only ko-KR / enko are meaningful here).
- Without --run it makes no API call and writes nothing (plan only).
- With --run it sends exactly one request (no retry) and writes
  data/cross_asr/diagnostics/clova_language/<language>/<sample_id>.json  (never overwritten)

Usage:
    python -m src.cross_asr.diag_clova_language --language ko-KR                # plan only
    python -m src.cross_asr.diag_clova_language --language ko-KR --run          # 1 paid request
    python -m src.cross_asr.diag_clova_language --language ko-KR --compare      # print comparison
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.cross_asr.common import load_cross_asr_config, sha256_file, git_commit, now_utc
from src.cross_asr.transcribe import (ClovaBackend, FatalError, TransientError, load_manifest,
                                      write_json_atomic, clova_url)

DOC_LANGUAGES = {"ko-KR", "en-US", "enko", "ja", "zh-cn", "zh-tw"}
DEFAULT_SAMPLE = "scenario_007_clinical_charting"


def diag_path(cfg: dict, language: str, sample_id: str) -> Path:
    return Path(cfg["paths"]["output_root"]) / "diagnostics" / "clova_language" / language / f"{sample_id}.json"


def script_profile(text: str) -> dict:
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    digits = len(re.findall(r"[0-9]", text))
    return {"hangul_chars": hangul, "latin_chars": latin, "digit_chars": digits,
            "hangul_share_of_letters": round(hangul / (hangul + latin), 3) if hangul + latin else None}


def compare(cfg: dict, language: str, sample_id: str) -> int:
    gold = json.load(open(Path(cfg["paths"]["generated_text_dir"]) / f"{sample_id}.json", encoding="utf-8"))["text"]
    rows = [("GOLD", gold)]
    enko = Path(cfg["paths"]["output_root"]) / "clova_enko" / "stt_transcripts" / f"{sample_id}.json"
    if enko.exists():
        rows.append(("clova enko (primary)", json.load(open(enko, encoding="utf-8"))["whisper_transcript"]))
    d = diag_path(cfg, language, sample_id)
    if not d.exists():
        print(f"STOP: {d} does not exist - run with --run first")
        return 1
    rows.append((f"clova {language} (diagnostic)", json.load(open(d, encoding="utf-8"))["whisper_transcript"]))
    for name, text in rows:
        print(f"\n[{name}]  {script_profile(text)}\n{text}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--language", required=True)
    ap.add_argument("--sample", default=DEFAULT_SAMPLE)
    ap.add_argument("--run", action="store_true", help="send exactly one request (paid)")
    ap.add_argument("--compare", action="store_true", help="print gold / enko / diagnostic side by side")
    args = ap.parse_args()

    load_dotenv()
    cfg = load_cross_asr_config()
    if args.language not in DOC_LANGUAGES:
        print(f"STOP: language {args.language!r} is not in the documented values {sorted(DOC_LANGUAGES)}")
        return 1
    if args.compare:
        return compare(cfg, args.language, args.sample)

    settings = dict(cfg["asr_systems"]["clova_enko"])
    params = dict(settings["params"])
    params["language"] = args.language
    settings["params"] = params
    manifest = load_manifest(cfg)
    if args.sample not in manifest:
        print(f"STOP: {args.sample} not in manifest")
        return 1
    out = diag_path(cfg, args.language, args.sample)
    env_ok = {k: bool(os.environ.get(k)) for k in ["CLOVA_SPEECH_INVOKE_URL", "CLOVA_SPEECH_SECRET_KEY"]}

    print("=== CLOVA language diagnostic (not part of primary analysis) ===")
    print(f"sample        : {args.sample}  ({float(manifest[args.sample]['duration_sec']) / 60:.2f} min)")
    print(f"params sent   : {params}   (only 'language' differs from clova_enko)")
    print(f"API requests  : 1 (no retry)")
    print(f"output file   : {out}")
    print(f"env vars      : {env_ok}  (values not shown)")
    if out.exists():
        print("STOP: output already exists (not overwritten) - use --compare")
        return 1
    if not all(env_ok.values()):
        print("STOP: CLOVA environment variables missing")
        return 1
    try:
        clova_url(os.environ["CLOVA_SPEECH_INVOKE_URL"], settings["endpoint"])
    except FatalError as e:
        print(f"STOP: {e}")
        return 1
    if not args.run:
        print("PLAN ONLY - no API call, no file written (add --run to send 1 request)")
        return 0

    audio = Path(manifest[args.sample]["audio_path"])
    audio_sha = sha256_file(audio)
    if audio_sha != manifest[args.sample]["sha256"]:
        print("STOP: audio SHA-256 differs from manifest - nothing sent")
        return 2
    t0 = time.time()
    try:
        text, raw = ClovaBackend(settings)(cfg, args.sample, audio)
    except (FatalError, TransientError) as e:
        print(f"REQUEST FAILED (not retried): {e}")
        return 2
    write_json_atomic(out, {
        "sample_id": args.sample,
        "whisper_transcript": text,
        "stt_metadata": {"asr_system": f"clova_{args.language}_diagnostic", "purpose": "diagnostic only",
                         "provider": "clova", "endpoint": settings["endpoint"], "params": params,
                         "audio_path": str(audio), "audio_sha256": audio_sha,
                         "transcribed_at": now_utc(), "request_seconds": round(time.time() - t0, 2),
                         "git_commit": git_commit(), "config_version": cfg["version"]},
        "raw_response": raw,
    })
    print(f"DONE: 1 request, written {out}")
    return compare(cfg, args.language, args.sample)


if __name__ == "__main__":
    sys.exit(main())
