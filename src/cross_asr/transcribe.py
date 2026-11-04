"""
ASR transcription for the Cross-ASR experiment (docs/cross_asr_spec.md, Section 4).

Conditions (settings fixed in configs/cross_asr.yaml; see docs/cross_asr_spec.md Section 11):
    whisper1               reuse existing data/stt_transcripts (no API call)        Condition A
    gpt4o_transcribe       OpenAI gpt-4o-transcribe, language "ko"                  Condition A
    chirp3_ko              Google Speech-to-Text V2 chirp_3, language_codes [ko-KR] Condition A
    whisper1_auto          OpenAI whisper-1, language parameter omitted             Condition B (pilot only)
    gpt4o_transcribe_auto  OpenAI gpt-4o-transcribe, language parameter omitted     Condition B (pilot only)
    chirp3_auto            chirp_3, language_codes [auto]                           Condition B (pilot only)
    clova_enko             CLOVA Speech (excluded from main analysis; code kept)
    All paid conditions: no prompt, no vocabulary/phrase adaptation.

Input  : the 300 primary audio files listed in data/cross_asr/audio_manifest.csv
         (the manifest outputs must be complete and consistent; each audio file's SHA-256 is
         re-checked against the manifest before it is sent or copied)
Output : data/cross_asr/<asr>/stt_transcripts/<sample_id>.json
         {"sample_id", "whisper_transcript", "stt_metadata", "raw_response"}
         ("whisper_transcript" is kept as the key so the existing v4 evaluation code can read it)
Logs   : data/cross_asr/<asr>/logs/transcribe_<UTC timestamp>.json
         (kept outside stt_transcripts/ because the existing loaders read every *.json there)

Request control:
    - At most MAX_ATTEMPTS (3) requests per sample. Client-library retries are disabled
      (OpenAI max_retries=0; Google retry=None), so every request is one counted by this script.
    - Retried only on transient errors: HTTP 429, HTTP 5xx, connection errors and timeouts.
    - Stopped immediately (whole run) on configuration/authentication errors: other HTTP 4xx
      (400/401/403/404 ...), an unexpected CLOVA result, or an empty transcript.
    - If a sample still fails after MAX_ATTEMPTS transient errors, the whole run stops.
    - An audio hash mismatch against the manifest stops the whole run before anything is sent.

Safety:
    --plan       no API call, no file written: prints targets, counts, audio minutes, files to create
    --pilot      only the 30 pilot samples (data/cross_asr/pilot_samples.json)
    --limit N    process at most N samples that still need transcription (e.g. --limit 1 access check)
    --samples    comma-separated sample_ids, restricted to the selected targets (e.g. pilot samples)
    Scope        a condition with `scope: pilot` in the config refuses to run without --pilot
    Chirp limit  synchronous Recognize accepts local audio up to 60 s / 10 MB; longer files are
                 refused before sending
    Resume       an existing output is reused only if sample_id, audio SHA-256, ASR system, provider,
                 model/language (or CLOVA endpoint/params) and config version all match; otherwise
                 the run stops before any API call (nothing is overwritten)
    Atomic write each output is written to a temporary file and moved into place
    Secrets      API keys are read from .env and are never printed or logged

Usage:
    python -m src.cross_asr.transcribe --asr gpt4o_transcribe --pilot --plan
    python -m src.cross_asr.transcribe --asr gpt4o_transcribe --pilot --limit 1
    python -m src.cross_asr.transcribe --asr gpt4o_transcribe --pilot
    python -m src.cross_asr.transcribe --asr gpt4o_transcribe
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.cross_asr.common import load_cross_asr_config, sha256_file, git_commit, now_utc

MANIFEST, PILOT, SUMMARY = "audio_manifest.csv", "pilot_samples.json", "manifest_summary.json"
MAX_ATTEMPTS = 3                 # total requests per sample, including the first
BACKOFF_SECONDS = [5, 20]        # wait before attempt 2 and 3 (or Retry-After, capped at 60 s)
REQUIRED_ENV = {                 # by provider
    "reuse_existing": [],
    "openai": ["OPENAI_API_KEY"],
    "clova": ["CLOVA_SPEECH_INVOKE_URL", "CLOVA_SPEECH_SECRET_KEY"],
    "google": ["GOOGLE_CLOUD_PROJECT"],      # credentials via gcloud Application Default Credentials
}
GOOGLE_SYNC_MAX_SECONDS, GOOGLE_SYNC_MAX_BYTES = 60.0, 10_000_000


class FatalError(Exception):
    """Configuration, authentication or data problem: stop the whole run, do not retry."""


class TransientError(Exception):
    """429 / 5xx / network: may be retried up to MAX_ATTEMPTS."""
    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after


# ---------- inputs ----------

def load_manifest(cfg: dict) -> dict:
    """Return {sample_id: row}; stop unless all three manifest outputs exist and are consistent."""
    out = Path(cfg["paths"]["output_root"])
    for name in (MANIFEST, PILOT, SUMMARY):
        if not (out / name).exists():
            raise SystemExit(f"STOP: {out / name} missing - run python -m src.cross_asr.manifest first")
    summary = json.load(open(out / SUMMARY, encoding="utf-8"))
    for name in (MANIFEST, PILOT):
        if sha256_file(out / name) != summary.get("files_sha256", {}).get(name):
            raise SystemExit(f"STOP: {name} does not match {SUMMARY} - run the manifest verification")
    rows = {r["sample_id"]: r for r in csv.DictReader(open(out / MANIFEST, encoding="utf-8"))}
    if len(rows) != 300:
        raise SystemExit(f"STOP: manifest has {len(rows)} samples (expected 300)")
    return rows


def select_samples(cfg: dict, manifest: dict, pilot: bool) -> list[str]:
    if not pilot:
        return sorted(manifest)
    p = json.load(open(Path(cfg["paths"]["output_root"]) / PILOT, encoding="utf-8"))
    ids = sorted(p["sample_ids"])
    missing = [s for s in ids if s not in manifest]
    if missing or len(ids) != 30:
        raise SystemExit(f"STOP: pilot list invalid (n={len(ids)}, not in manifest={missing[:3]})")
    return ids


def output_paths(cfg: dict, asr: str) -> tuple[Path, Path]:
    base = Path(cfg["paths"]["output_root"]) / asr
    return base / "stt_transcripts", base / "logs"


def public_settings(settings: dict) -> dict:
    return {k: v for k, v in settings.items() if k != "note"}


def expected_metadata(asr: str, settings: dict, cfg: dict) -> dict:
    """Fields an existing output must carry to be reused."""
    exp = {"asr_system": asr, "provider": settings["provider"], "config_version": cfg["version"]}
    if settings["provider"] in ("openai", "reuse_existing"):
        exp.update({"model": settings["model"], "language": settings["language"]})
    if settings["provider"] == "google":
        exp.update({"model": settings["model"], "location": settings["location"],
                    "language_codes": settings["language_codes"]})
    if settings["provider"] == "clova":
        exp.update({"endpoint": settings["endpoint"], "params": settings["params"]})
    return exp


def existing_status(path: Path, sample_id: str, audio_sha: str, expected: dict) -> str:
    """'missing' | 'valid' | 'invalid:<reason>'"""
    if not path.exists():
        return "missing"
    try:
        rec = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return f"invalid:unreadable ({type(e).__name__})"
    if rec.get("sample_id") != sample_id:
        return "invalid:sample_id mismatch"
    if not isinstance(rec.get("whisper_transcript"), str) or not rec["whisper_transcript"].strip():
        return "invalid:empty transcript"
    meta = rec.get("stt_metadata", {})
    if meta.get("audio_sha256") != audio_sha:
        return "invalid:audio_sha256 differs from manifest"
    for k, v in expected.items():
        if meta.get(k) != v:
            return f"invalid:{k}={meta.get(k)!r} (expected {v!r})"
    return "valid"


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _retry_after(headers):
    try:
        v = headers.get("retry-after") if headers is not None else None
        return min(float(v), 60.0) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------- ASR backends: each returns (transcript_text, raw_response_dict) ----------

def transcribe_whisper1_reuse(cfg: dict, sample_id: str, audio_path: Path):
    src = Path(cfg["paths"]["original_stt_dir"]) / f"{sample_id}.json"
    rec = json.load(open(src, encoding="utf-8"))
    if rec.get("sample_id") != sample_id:
        raise FatalError(f"source sample_id mismatch in {src}")
    raw = {"source_file": str(src), "source_sha256": sha256_file(src),
           "source_stt_metadata": rec.get("stt_metadata")}
    return rec["whisper_transcript"], raw


class OpenAIBackend:
    def __init__(self, settings: dict):
        import openai
        self.openai = openai
        # max_retries=0: the SDK does not retry on its own; this script counts every request.
        self.client = openai.OpenAI(max_retries=0, timeout=600)   # key from OPENAI_API_KEY
        self.model = settings["model"]
        self.language = settings["language"]      # None = parameter omitted (Condition B)

    def __call__(self, cfg, sample_id, audio_path: Path):
        o = self.openai
        kwargs = {"model": self.model}
        if self.language is not None:
            kwargs["language"] = self.language
        try:
            with open(audio_path, "rb") as f:
                resp = self.client.audio.transcriptions.create(file=f, **kwargs)
        except o.APIStatusError as e:
            msg = f"HTTP {e.status_code}: {str(e)[:300]}"
            if e.status_code == 429 or e.status_code >= 500:
                raise TransientError(msg, _retry_after(getattr(e.response, "headers", None)))
            raise FatalError(msg)
        except o.APIConnectionError as e:          # includes APITimeoutError
            raise TransientError(f"{type(e).__name__}: {str(e)[:300]}")
        raw = resp.model_dump() if hasattr(resp, "model_dump") else {"text": getattr(resp, "text", None)}
        return resp.text, raw


def clova_url(invoke_url: str, endpoint: str) -> str:
    """Invoke URL + endpoint without duplicating the endpoint.

    The Invoke URL from the CLOVA Speech console normally ends with the domain path
    (e.g. .../external/v1/<id>/<hash>). If it already ends with the endpoint it is used as is;
    if it ends with a different /recognizer/... path it is treated as a configuration error.
    """
    base = invoke_url.strip().rstrip("/")
    if base.endswith(endpoint):
        return base
    if "/recognizer/" in base:
        raise FatalError("CLOVA_SPEECH_INVOKE_URL ends with a different /recognizer/... path; "
                         "use the Invoke URL shown in the console (without an endpoint)")
    return base + endpoint


class ClovaBackend:
    """Local file recognition: POST {Invoke URL}/recognizer/upload, multipart/form-data with
    fields media (file), params (JSON string) and type ("application/json"), header
    X-CLOVASPEECH-API-KEY (Ncloud API docs, CLOVA Speech 'local file recognition')."""

    def __init__(self, settings: dict):
        import httpx
        self.httpx = httpx
        self.url = clova_url(os.environ["CLOVA_SPEECH_INVOKE_URL"], settings["endpoint"])
        self.key = os.environ["CLOVA_SPEECH_SECRET_KEY"]
        self.params = dict(settings["params"])

    def __call__(self, cfg, sample_id, audio_path: Path):
        try:
            with open(audio_path, "rb") as f:
                r = self.httpx.post(
                    self.url,
                    headers={"X-CLOVASPEECH-API-KEY": self.key},
                    files={"media": (audio_path.name, f, "audio/mpeg")},
                    data={"params": json.dumps(self.params), "type": "application/json"},
                    timeout=600,
                )
        except self.httpx.TransportError as e:     # connection errors, timeouts
            raise TransientError(f"{type(e).__name__}: {str(e)[:300]}")
        if r.status_code == 429 or r.status_code >= 500:
            raise TransientError(f"HTTP {r.status_code}: {r.text[:300]}", _retry_after(r.headers))
        if r.status_code != 200:
            raise FatalError(f"HTTP {r.status_code}: {r.text[:300]}")
        try:
            raw = r.json()
        except ValueError:
            raise FatalError(f"non-JSON response: {r.text[:300]}")
        if raw.get("result") != "COMPLETED":
            raise FatalError(f"CLOVA result={raw.get('result')} message={raw.get('message')}")
        return raw.get("text", ""), raw


class GoogleChirpBackend:
    """Speech-to-Text V2 synchronous Recognize with chirp_3 (inline MP3, auto decoding).
    Credentials: Application Default Credentials (gcloud auth application-default login)."""

    def __init__(self, settings: dict):
        from google.api_core import exceptions as gexc
        from google.api_core.client_options import ClientOptions
        from google.cloud.speech_v2 import SpeechClient
        from google.cloud.speech_v2.types import cloud_speech
        self.gexc, self.cs = gexc, cloud_speech
        loc = settings["location"]
        self.client = SpeechClient(client_options=ClientOptions(api_endpoint=f"{loc}-speech.googleapis.com"))
        self.recognizer = f"projects/{os.environ['GOOGLE_CLOUD_PROJECT']}/locations/{loc}/recognizers/_"
        self.config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=list(settings["language_codes"]),
            model=settings["model"],
        )

    def __call__(self, cfg, sample_id, audio_path: Path):
        g = self.gexc
        content = audio_path.read_bytes()
        req = self.cs.RecognizeRequest(recognizer=self.recognizer, config=self.config, content=content)
        try:
            resp = self.client.recognize(request=req, retry=None, timeout=600)
        except (g.TooManyRequests, g.ResourceExhausted, g.ServiceUnavailable,
                g.InternalServerError, g.DeadlineExceeded, g.GatewayTimeout) as e:
            raise TransientError(f"{type(e).__name__}: {str(e)[:300]}")
        except g.GoogleAPICallError as e:          # 400/401/403/404 ... configuration or access
            raise FatalError(f"{type(e).__name__}: {str(e)[:300]}")
        except Exception as e:                     # e.g. credentials not found
            raise FatalError(f"{type(e).__name__}: {str(e)[:300]}")
        raw = type(resp).to_dict(resp)
        parts = [r.alternatives[0].transcript.strip() for r in resp.results if r.alternatives]
        raw["detected_language_codes"] = [r.language_code for r in resp.results]
        return " ".join(p for p in parts if p), raw


def make_backend(settings: dict):
    if settings["provider"] == "reuse_existing":
        return transcribe_whisper1_reuse
    if settings["provider"] == "openai":
        return OpenAIBackend(settings)
    if settings["provider"] == "clova":
        return ClovaBackend(settings)
    if settings["provider"] == "google":
        return GoogleChirpBackend(settings)
    raise SystemExit(f"STOP: unknown provider {settings['provider']}")


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asr", required=True, help="condition key in configs/cross_asr.yaml asr_systems")
    ap.add_argument("--pilot", action="store_true", help="only the 30 pilot samples")
    ap.add_argument("--plan", action="store_true", help="no API call, no file written")
    ap.add_argument("--limit", type=int, default=None, help="process at most N samples needing work")
    ap.add_argument("--samples", default=None,
                    help="comma-separated sample_ids; must be a subset of the selected targets "
                         "(with --pilot: of the 30 pilot samples)")
    args = ap.parse_args()

    load_dotenv()
    cfg = load_cross_asr_config()
    if args.asr not in cfg["asr_systems"]:
        print(f"STOP: unknown condition {args.asr!r}; available: {sorted(cfg['asr_systems'])}")
        return 1
    settings = cfg["asr_systems"][args.asr]
    if settings.get("scope") == "pilot" and not args.pilot:
        print(f"STOP: {args.asr} is limited to the pilot by protocol (scope: pilot) - add --pilot")
        return 1
    manifest = load_manifest(cfg)
    targets = select_samples(cfg, manifest, args.pilot)
    if args.samples:
        requested = [x.strip() for x in args.samples.split(",") if x.strip()]
        outside = [x for x in requested if x not in targets]
        if outside or len(set(requested)) != len(requested):
            print(f"STOP: --samples must be distinct members of the selected targets; "
                  f"not allowed: {outside[:5]}")
            return 1
        targets = requested
    stt_dir, log_dir = output_paths(cfg, args.asr)
    expected = expected_metadata(args.asr, settings, cfg)

    status = {sid: existing_status(stt_dir / f"{sid}.json", sid, manifest[sid]["sha256"], expected)
              for sid in targets}
    valid = [s for s in targets if status[s] == "valid"]
    invalid = [(s, status[s]) for s in targets if status[s].startswith("invalid")]
    todo = [s for s in targets if status[s] == "missing"]
    if args.limit is not None:
        todo = todo[:args.limit]
    leftovers = sorted(p.name for p in stt_dir.glob(".*.tmp-*")) if stt_dir.exists() else []
    env_ok = {k: bool(os.environ.get(k)) for k in REQUIRED_ENV[settings["provider"]]}
    paid = settings["provider"] != "reuse_existing"
    minutes = sum(float(manifest[s]["duration_sec"]) for s in todo) / 60

    url_note = ""
    too_long = []
    if settings["provider"] == "google":
        too_long = [s for s in todo if float(manifest[s]["duration_sec"]) > GOOGLE_SYNC_MAX_SECONDS
                    or int(manifest[s]["bytes"]) > GOOGLE_SYNC_MAX_BYTES]
    if settings["provider"] == "clova" and env_ok.get("CLOVA_SPEECH_INVOKE_URL"):
        try:
            u = clova_url(os.environ["CLOVA_SPEECH_INVOKE_URL"], settings["endpoint"])
            url_note = f"request path ends with '{settings['endpoint']}' once: {u.endswith(settings['endpoint']) and u.count('/recognizer/') == 1}"
        except FatalError as e:
            url_note = f"INVALID: {e}"

    scope = ('pilot' if args.pilot else 'all 300') + (f", --samples {len(targets)}" if args.samples else "")
    print(f"=== transcribe plan: {args.asr} ({scope}) ===")
    print(f"settings           : {public_settings(settings)}")
    print(f"targets            : {len(targets)}")
    print(f"already valid      : {len(valid)} (reused, not re-sent)")
    print(f"invalid existing   : {len(invalid)}")
    print(f"to process now     : {len(todo)}{' (limited by --limit)' if args.limit is not None else ''}")
    if paid:
        print(f"audio to send      : {minutes:.2f} min")
        print(f"API requests       : {len(todo)} minimum, {len(todo) * MAX_ATTEMPTS} maximum "
              f"(<= {MAX_ATTEMPTS} per sample, transient errors only; client-library retries disabled)")
    else:
        print("API requests       : 0 (no API call)")
    if url_note:
        print(f"CLOVA URL check    : {url_note}")
    if settings["provider"] == "google":
        longest = max((float(manifest[s]["duration_sec"]) for s in todo), default=0.0)
        print(f"sync limit check   : longest {longest:.1f} s; over 60 s / 10 MB: {len(too_long)}")
        adc = "not checked"
        try:
            import google.auth
            google.auth.default()
            adc = "available"
        except Exception as e:
            adc = f"NOT AVAILABLE ({type(e).__name__})"
        print(f"Google ADC         : {adc}  (no credential details shown)")
    print(f"output dir         : {stt_dir}")
    if todo:
        print(f"files to create    : {len(todo)} x {stt_dir}/<sample_id>.json  (first: {todo[0]}.json)")
    print(f"run log            : {log_dir}/transcribe_<UTC timestamp>.json")
    print(f"env vars present   : {env_ok if env_ok else 'none needed'}  (values not shown)")

    if invalid:
        print("STOP: existing outputs do not match (not overwritten; move them out to retry):")
        for s, why in invalid[:10]:
            print(f"  - {s}: {why}")
        return 1
    if leftovers:
        print(f"STOP: leftover temporary files in {stt_dir}: {leftovers[:5]} (move them out first)")
        return 1
    if not all(env_ok.values()):
        print("STOP: required environment variables missing in .env")
        return 1
    if url_note.startswith("INVALID"):
        print("STOP: CLOVA Invoke URL is not usable")
        return 1
    if too_long:
        print(f"STOP: {len(too_long)} file(s) exceed the synchronous Recognize limit: {too_long[:3]}")
        return 1
    if settings["provider"] == "google" and adc != "available":
        print("STOP: Google Application Default Credentials not available")
        return 1
    if args.plan:
        print("PLAN ONLY - no API call, no file written")
        return 0
    if not todo:
        print(f"NOTHING TO DO - all {len(targets)} targets already valid")
        return 0

    backend = make_backend(settings)
    commit = git_commit()
    log = {"asr": args.asr, "settings": public_settings(settings), "pilot": args.pilot,
           "limit": args.limit, "started_at": now_utc(), "git_commit": commit,
           "config_version": cfg["version"], "max_attempts": MAX_ATTEMPTS, "entries": []}
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    log_path = log_dir / f"transcribe_{stamp}.json"
    n = 1
    while log_path.exists():            # never overwrite an earlier run log
        n += 1
        log_path = log_dir / f"transcribe_{stamp}_{n}.json"

    n_ok, n_requests, abort = 0, 0, None
    try:
        for i, sid in enumerate(todo, 1):
            audio = Path(manifest[sid]["audio_path"])
            audio_sha = sha256_file(audio)
            if audio_sha != manifest[sid]["sha256"]:
                abort = f"{sid}: audio SHA-256 differs from manifest (nothing sent)"
                log["entries"].append({"sample_id": sid, "status": "failed", "error": abort})
                break
            t0, text, raw, last_err = time.time(), None, None, None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                if paid:
                    n_requests += 1
                try:
                    text, raw = backend(cfg, sid, audio)
                    if not isinstance(text, str) or not text.strip():
                        raise FatalError("empty transcript")
                    break
                except FatalError as e:
                    abort = f"{sid}: {e}"
                    print(f"[{i}/{len(todo)}] {sid} attempt {attempt}: FATAL {e}")
                    break
                except TransientError as e:
                    last_err = str(e)
                    print(f"[{i}/{len(todo)}] {sid} attempt {attempt}/{MAX_ATTEMPTS}: transient {e}")
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(e.retry_after or BACKOFF_SECONDS[attempt - 1])
                    else:
                        abort = f"{sid}: transient errors persisted after {MAX_ATTEMPTS} attempts ({last_err})"
            if abort:
                log["entries"].append({"sample_id": sid, "status": "failed", "error": abort,
                                       "attempts": attempt})
                break
            record = {
                "sample_id": sid,
                "whisper_transcript": text,
                "stt_metadata": {
                    "asr_system": args.asr,
                    **public_settings(settings),
                    "audio_path": str(audio),
                    "audio_sha256": audio_sha,
                    # for whisper1 the transcript is reused; the original transcription time is
                    # not recorded in the source file, so only the copy time is stored
                    ("copied_at" if settings["provider"] == "reuse_existing" else "transcribed_at"): now_utc(),
                    "request_seconds": round(time.time() - t0, 2),
                    "attempts": attempt,
                    "git_commit": commit,
                    "config_version": cfg["version"],
                },
                "raw_response": raw,
            }
            write_json_atomic(stt_dir / f"{sid}.json", record)
            log["entries"].append({"sample_id": sid, "status": "processed",
                                   "request_seconds": record["stt_metadata"]["request_seconds"],
                                   "attempts": attempt})
            n_ok += 1
            print(f"[{i}/{len(todo)}] {sid} ok ({record['stt_metadata']['request_seconds']}s) "
                  f"{text[:40]!r}")
    finally:
        log["finished_at"] = now_utc()
        log["summary"] = {"processed": n_ok, "api_requests": n_requests, "aborted": abort,
                          "skipped_valid": len(valid), "targets": len(targets)}
        write_json_atomic(log_path, log)

    total_valid = sum(1 for s in targets if existing_status(
        stt_dir / f"{s}.json", s, manifest[s]["sha256"], expected) == "valid")
    print(f"\n=== processed={n_ok} api_requests={n_requests} skipped_valid={len(valid)} -> log {log_path}")
    print(f"valid outputs now  : {total_valid}/{len(targets)}")
    if abort:
        print(f"RUN STOPPED: {abort}")
        return 2
    print("TRANSCRIBE COMPLETE" if total_valid == len(targets) else
          "TRANSCRIBE PARTIAL - targets not yet processed remain (e.g. because of --limit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
