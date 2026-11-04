"""
CCER v4 evaluation of the Cross-ASR transcripts (docs/cross_asr_spec.md Sections 5 and 12).

The v4 evaluator is used unchanged - this file only supplies paths, the per-sample loop and logging:
    closed-vocab extraction  src.entity_extraction.closed_vocab_extractor.extract_closed_vocab_entities
    open-vocab extraction    src.entity_extraction.run_open_vocab_extraction.extract_with_retry
                             (v4 prompt, JSON repair, structure check, 3 attempts)
    gold (content scaffold)  src.entity_extraction.scaffold_as_gold.scaffold_to_closed_vocab / _open_vocab
    closed-vocab matching    src.matching.entity_matcher.match_closed_vocab
    semantic matching        src.matching.run_semantic_matching.match_with_retry
                             (v4 prompt, structure check, 3 attempts)
    CCER                     src.evaluation.ccer_eval.run_ccer_evaluation (v4 weights and formula)
The v4 runner loops (run_extraction / run_matching) are not called because they always process every
sample and continue past failed samples. Calls per sample are the same as in v4: gold-text
extraction, transcript extraction, semantic matching (3 Claude calls; the gold-text extraction is
not used by matching, which uses the scaffold - kept as in v4, spec Section 5). The model is
`entity_extraction.claude_model` in configs/config.yaml; call settings are not changed
(no temperature set, Anthropic SDK default retries).

Input   data/cross_asr/<asr>/stt_transcripts/<sample_id>.json  (300 primary samples)
Output  data/cross_asr/<asr>/entities/<sample_id>_closed.json / _open.json / _matched.json
        (same structure as data/entities); results/cross_asr/<asr>/ccer_results.csv, ccer_summary.json
        (written only when all 300 matched files exist)
Logs    data/cross_asr/<asr>/logs/evaluate_<UTC timestamp>.json  (per call: model reported by the
        API, input/output tokens, seconds; never the API key)

Empty response rule (spec 12.2): a sample listed in EMPTY_RESPONSE_RULE has no transcript file; it
is evaluated as an empty transcript without any API call (closed-vocab extraction of "" and every
gold open-vocab entity recorded as an omission). Any other missing transcript stops the run.

Safety
    --plan       no API call, no file written: counts, calls and token estimate, checks
    --limit N    process at most N samples that still need Claude calls (e.g. --limit 3 trial)
    Resume       finished stages are kept and skipped; re-running continues where it stopped
    Stop         the whole run stops at the first failed sample (after the v4 3 attempts), on
                 authentication / permission / model-not-found / bad-request errors (no retry) and on
                 any unexpected error; the sample_id, stage and cause are written to the run log
    Model guard  every response must report the same model ID as earlier evaluate runs (any
                 condition) or, in the first run, as the first response; otherwise the run stops
    Lock         data/cross_asr/<asr>/logs/.evaluate.lock prevents two runs of the same condition
    Writes       atomic (temporary file + rename); existing outputs are never overwritten
    Checks       --plan: whisper1 closed-vocab matches vs saved v4; empty-response rule output vs the
                 saved v4 gold entities of the same sample

Usage
    python -m src.cross_asr.evaluate --asr whisper1 --plan
    python -m src.cross_asr.evaluate --asr whisper1 --limit 3
    python -m src.cross_asr.evaluate --asr whisper1
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from src.cross_asr.common import (load_cross_asr_config, load_base_config, primary_samples,
                                  git_commit, git_dirty_paths, now_utc)

EMPTY_RESPONSE_RULE = {"chirp3_auto": {"scenario_063_telegraphic_icu"}}   # spec 12.2
EMPTY_OPEN = {"symptoms": [], "clinical_status": None, "medication_identity": None,
              "interventions": [], "intake_output": None, "notification": None}
# rough per-sample token estimate (3 calls) from v4 prompt sizes; replaced by measured values
# after a --limit trial (see the log summary)
EST_TOKENS_IN, EST_TOKENS_OUT = 7200, 1100


class FatalAPIError(BaseException):
    """Not an Exception subclass on purpose: passes through the v4 retry loops (`except Exception`)
    so that authentication / model / request errors stop the run at once instead of being retried."""


class LoggingClient:
    """Wraps anthropic.Anthropic; records every messages.create call. Arguments are passed unchanged.

    Model guard: every response must report the same model ID as the reference (the model recorded
    by earlier evaluate runs of any condition, else the first response of this run). A different ID
    stops the run before that response is used (spec Section 5: all systems with the same model)."""

    def __init__(self, real, reference_model=None):
        self._real = real
        self.calls = []
        self.current = None
        self.reference_model = reference_model
        self.messages = self

    def create(self, **kwargs):
        import anthropic
        t0 = time.time()
        rec = {"sample_id": self.current, "requested_model": kwargs.get("model"),
               "tool": (kwargs.get("tool_choice") or {}).get("name")}
        try:
            resp = self._real.messages.create(**kwargs)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                anthropic.NotFoundError, anthropic.BadRequestError) as e:
            rec.update(ok=False, error=type(e).__name__, seconds=round(time.time() - t0, 2))
            self.calls.append(rec)
            raise FatalAPIError(f"{type(e).__name__} (HTTP {getattr(e, 'status_code', '?')})") from None
        except Exception as e:
            rec.update(ok=False, error=type(e).__name__, seconds=round(time.time() - t0, 2))
            self.calls.append(rec)
            raise
        usage = getattr(resp, "usage", None)
        got = getattr(resp, "model", None)
        rec.update(ok=True, response_model=got,
                   input_tokens=getattr(usage, "input_tokens", None),
                   output_tokens=getattr(usage, "output_tokens", None),
                   seconds=round(time.time() - t0, 2))
        if self.reference_model is None:
            self.reference_model = got
        if got != self.reference_model:
            rec.update(ok=False, error="ModelChanged")
            self.calls.append(rec)
            raise FatalAPIError(f"response model {got!r} differs from reference {self.reference_model!r} "
                                f"(response not used)")
        self.calls.append(rec)
        return resp


# ---------- helpers ----------

def write_json_atomic(path: Path, obj: dict) -> None:
    """Same JSON format as the v4 runners (ensure_ascii=False, indent=2); never overwrites."""
    if path.exists():
        raise SystemExit(f"STOP: {path} already exists (not overwritten)")
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


def load_json(path: Path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def stage_status(ent_dir: Path, sid: str) -> dict:
    """Which stages are already finished and valid for this sample."""
    from src.entity_extraction.run_open_vocab_extraction import is_valid_extraction
    from src.matching.semantic_matcher import is_valid_match_result
    out = {}
    c = load_json(ent_dir / f"{sid}_closed.json")
    out["closed"] = bool(c and c.get("sample_id") == sid and isinstance(c.get("whisper_entities"), dict))
    o = load_json(ent_dir / f"{sid}_open.json")
    out["open"] = bool(o and o.get("sample_id") == sid and is_valid_extraction(o.get("whisper_entities")))
    m = load_json(ent_dir / f"{sid}_matched.json")
    out["matched"] = bool(m and m.get("sample_id") == sid and isinstance(m.get("closed_vocab_matches"), list)
                          and is_valid_match_result(m.get("open_vocab_matches")))
    for stage, ok in out.items():
        if not ok and (ent_dir / f"{sid}_{stage}.json").exists():
            out[stage] = "invalid"
    return out


def empty_open_matches(gold_open: dict) -> dict:
    """Spec 12.2: every gold open-vocab entity is an omission (what matching gives for an empty list)."""
    def single(v):
        return ({"gold_value": v, "whisper_value": None, "match_basis": "omission"} if v
                else {"gold_value": None, "whisper_value": None, "match_basis": "both_null"})
    return {
        "symptom_matches": [{"gold_value": s["name"], "whisper_value": None, "match_basis": "omission",
                             "negation_match": None, "severity_match": None} for s in gold_open["symptoms"]],
        "whisper_only_symptoms": [],
        "clinical_status_match": single(gold_open["clinical_status"]),
        "medication_identity_match": single(gold_open["medication_identity"]),
        "intervention_matches": [{"gold_value": i, "whisper_value": None, "match_basis": "omission"}
                                 for i in gold_open["interventions"]],
        "whisper_only_interventions": [],
        "intake_output_match": single(gold_open["intake_output"]),
        "notification_match": single(gold_open["notification"]),
    }


def closed_check_vs_v4(cfg, samples, stt_dir, scaffolds) -> tuple[int, list]:
    """whisper1 only: closed-vocab extraction + matching through this file vs saved v4 matches."""
    from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities
    from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab
    from src.matching.entity_matcher import match_closed_vocab
    same, diff = 0, []
    for s in samples:
        sid = s["sample_id"]
        text = json.load(open(stt_dir / f"{sid}.json", encoding="utf-8"))["whisper_transcript"]
        ours = match_closed_vocab(scaffold_to_closed_vocab(scaffolds[s["scenario_id"]]),
                                  extract_closed_vocab_entities(text))
        v4 = load_json(Path(cfg["paths"]["original_entities_dir"]) / f"{sid}_matched.json") or {}
        if ours == v4.get("closed_vocab_matches"):
            same += 1
        else:
            diff.append(sid)
    return same, diff


def calls_needed(status: dict, paid: list) -> int:
    """Claude calls still needed: 2 extraction calls unless _open.json is done, plus 1 matching call."""
    return sum((0 if status[s["sample_id"]]["open"] is True else 2) + 1 for s in paid)


def prior_response_models(cfg: dict) -> set:
    """Model IDs reported by the API in earlier evaluate runs of any condition."""
    models = set()
    for p in Path(cfg["paths"]["output_root"]).glob("*/logs/evaluate_*.json"):
        rec = load_json(p) or {}
        models |= {m for m in (rec.get("summary") or {}).get("response_models", {}) if m}
    return models


def empty_rule_check(cfg: dict, sid: str, scaffold: dict) -> str:
    """No API: the empty-response record must flatten to exactly the gold entities of the saved v4
    record of the same sample, every one an omission (v4 structure, flatten_matches, compute_ccer)."""
    from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities
    from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab, scaffold_to_open_vocab
    from src.matching.entity_matcher import match_closed_vocab
    from src.matching.semantic_matcher import is_valid_match_result
    from src.evaluation.flatten_matches import flatten_all_matches
    from src.evaluation.ccer_eval import compute_ccer
    om = empty_open_matches(scaffold_to_open_vocab(scaffold))
    if not is_valid_match_result(om):
        return "FAIL: invalid open-vocab match structure"
    ours = flatten_all_matches({"sample_id": sid, "open_vocab_matches": om,
                                "closed_vocab_matches": match_closed_vocab(scaffold_to_closed_vocab(scaffold),
                                                                           extract_closed_vocab_entities(""))})
    v4 = load_json(Path(cfg["paths"]["original_entities_dir"]) / f"{sid}_matched.json")
    if v4 is None:
        return "FAIL: saved v4 record missing"
    gold = lambda recs: Counter((r["entity_type"], str(r["gold_value"]).lower()) for r in recs if r["gold_value"] is not None)
    v4_gold, our_gold = gold(flatten_all_matches(v4)), gold(ours)
    if our_gold != v4_gold:
        return f"FAIL: gold entities differ from v4 ({sum(our_gold.values())} vs {sum(v4_gold.values())})"
    if any(r["gold_value"] is None for r in ours):
        return "FAIL: whisper-only records present"
    bad = [r for r in ours if r["match_status"] != "omission" or r["error_type"] != "omission"]
    if bad:
        return f"FAIL: {len(bad)} gold entities not recorded as omission"
    res = compute_ccer(ours)
    return (f"OK - {res['gold_entity_count']} gold entities (same as v4), all omission; "
            f"sample CCER {res['ccer_score']} = 2 x {res['gold_entity_count']} / {res['gold_entity_count']}")


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asr", required=True)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    load_dotenv(".env")
    cfg = load_cross_asr_config()
    base = load_base_config(cfg)
    if args.asr not in cfg["asr_systems"]:
        print(f"STOP: unknown condition {args.asr!r}; config keys: {sorted(cfg['asr_systems'])}")
        return 1
    model = base["entity_extraction"]["claude_model"]
    if model != cfg["evaluator"]["claude_model"]:
        print(f"STOP: evaluator model differs: config.yaml {model!r} vs cross_asr.yaml "
              f"{cfg['evaluator']['claude_model']!r}")
        return 1

    root = Path(cfg["paths"]["output_root"]) / args.asr
    stt_dir, ent_dir, log_dir = root / "stt_transcripts", root / "entities", root / "logs"
    res_dir = Path(cfg["paths"]["results_root"]) / args.asr
    gold_dir, scen_dir = Path(cfg["paths"]["generated_text_dir"]), Path(cfg["paths"]["scenarios_dir"])

    samples = primary_samples(cfg)
    if len(samples) != 300:
        print(f"STOP: {len(samples)} primary samples (expected 300)")
        return 1
    scaffolds = {}
    for s in samples:
        p = scen_dir / f"{s['scenario_id']}.json"
        if s["scenario_id"] not in scaffolds:
            if not p.exists():
                print(f"STOP: scaffold missing {p}")
                return 1
            scaffolds[s["scenario_id"]] = json.load(open(p, encoding="utf-8"))

    rule = EMPTY_RESPONSE_RULE.get(args.asr, set())
    missing = [s["sample_id"] for s in samples if not (stt_dir / f"{s['sample_id']}.json").exists()]
    unexpected = [m for m in missing if m not in rule]
    rule_present = [r for r in rule if r not in missing]
    bad_transcripts = []                 # present but unreadable, not a JSON object, wrong id or empty
    for s in samples:
        if s["sample_id"] in missing:
            continue
        rec = load_json(stt_dir / f"{s['sample_id']}.json")
        if (not isinstance(rec, dict) or rec.get("sample_id") != s["sample_id"]
                or not isinstance(rec.get("whisper_transcript"), str)
                or not rec["whisper_transcript"].strip()):
            bad_transcripts.append(s["sample_id"])

    status = {s["sample_id"]: stage_status(ent_dir, s["sample_id"]) for s in samples}
    invalid = [(sid, st) for sid, sv in status.items() for st, v in sv.items() if v == "invalid"]
    done = [sid for sid, sv in status.items() if sv["matched"] is True]
    todo = [s for s in samples if status[s["sample_id"]]["matched"] is not True]
    paid = [s for s in todo if s["sample_id"] not in rule]
    if args.limit is not None:
        paid = paid[:args.limit]
        todo = [s for s in todo if s["sample_id"] in rule or s in paid]
    stage_counts = Counter((status[s["sample_id"]]["closed"] is True, status[s["sample_id"]]["open"] is True)
                           for s in paid)
    n_calls = calls_needed(status, paid)
    ref_models = prior_response_models(cfg)
    lock = log_dir / ".evaluate.lock"

    print(f"=== evaluate plan: {args.asr} ===")
    print(f"evaluator model    : {model}  (configs/config.yaml; no temperature set, as in v4)")
    print(f"reference model    : {sorted(ref_models) or 'none yet (set by the first response of this run)'}"
          "  (earlier evaluate runs, all conditions)")
    print(f"transcripts        : {300 - len(missing)}/300 in {stt_dir}")
    print(f"empty-response rule: {sorted(rule) or 'none'}  (spec 12.2; evaluated without API call)")
    print(f"already evaluated  : {len(done)}/300 (kept, not re-sent)")
    print(f"invalid existing   : {len(invalid)}")
    print(f"to process now     : {len(todo)}" + (" (limited by --limit)" if args.limit is not None else "")
          + f"  [needing Claude: {len(paid)} = fresh {stage_counts[(False, False)] + stage_counts[(True, False)]}"
            f" (3 calls), open done {stage_counts[(True, True)] + stage_counts[(False, True)]} (1 call)]")
    print(f"Claude calls       : {n_calls} planned (minimum; the v4 retry loop may repeat a call up to 3 "
          f"times, the SDK retries 429/5xx internally)")
    print(f"token estimate     : ~{len(paid) * EST_TOKENS_IN / 1e6:.2f} M input, "
          f"~{len(paid) * EST_TOKENS_OUT / 1e6:.2f} M output (rough; measured after a --limit trial)")
    print(f"outputs            : {ent_dir}/<sample_id>_closed|_open|_matched.json")
    print(f"results            : {res_dir}/ccer_results.csv, ccer_summary.json (only when 300/300)")
    print(f"run log            : {log_dir}/evaluate_<UTC timestamp>.json")
    print(f"env vars present   : {{'ANTHROPIC_API_KEY': {bool(os.environ.get('ANTHROPIC_API_KEY'))}}}  (values not shown)")
    print(f"transcript check   : {len(bad_transcripts)} unreadable / not JSON / wrong sample_id / empty")
    if unexpected:
        print(f"STOP: transcripts missing outside the empty-response rule: {unexpected[:5]}")
        return 1
    if rule_present:
        print(f"STOP: {rule_present} has a transcript but is listed in the empty-response rule")
        return 1
    if bad_transcripts:
        print(f"STOP: transcripts unreadable, not a JSON object, with a wrong sample_id or empty: "
              f"{bad_transcripts[:5]}")
        return 1
    if args.asr == "whisper1":
        same, diff = closed_check_vs_v4(cfg, samples, stt_dir, scaffolds)
        print(f"v4 equivalence     : closed-vocab matches identical to saved v4 for {same}/300 samples"
              + (f"; differ: {diff[:5]}" if diff else ""))
        if diff:
            print("STOP: closed-vocab results differ from v4 - check before evaluating")
            return 1
    if rule:
        for sid in sorted(rule):
            chk = empty_rule_check(cfg, sid, scaffolds["_".join(sid.split("_")[:2])])
            print(f"empty-rule check   : {sid}: {chk}")
            if not chk.startswith("OK"):
                print("STOP: empty-response rule output is not consistent with v4")
                return 1
    if len(ref_models) > 1:
        print(f"STOP: earlier evaluate runs used more than one model: {sorted(ref_models)}")
        return 1
    if invalid:
        print(f"STOP: invalid existing outputs (nothing is overwritten): {invalid[:5]}")
        return 1
    if lock.exists():
        print(f"STOP: {lock} exists - another evaluate run for {args.asr} may be running. If not "
              f"(e.g. after a crash), delete the lock file and re-run.")
        return 1
    if paid and not os.environ.get("ANTHROPIC_API_KEY"):
        print("STOP: ANTHROPIC_API_KEY missing")
        return 1
    if args.plan:
        print("PLAN ONLY - no API call, no file written")
        return 0

    from anthropic import Anthropic
    from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities
    from src.entity_extraction.run_open_vocab_extraction import extract_with_retry
    from src.entity_extraction.scaffold_as_gold import scaffold_to_closed_vocab, scaffold_to_open_vocab
    from src.matching.entity_matcher import match_closed_vocab
    from src.matching.run_semantic_matching import match_with_retry
    from src.matching.semantic_matcher import is_valid_match_result

    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pid {os.getpid()} started {now_utc()}\n".encode())
        os.close(fd)
    except FileExistsError:
        print(f"STOP: {lock} exists - another evaluate run may be running")
        return 1

    client = LoggingClient(Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")),
                           reference_model=next(iter(ref_models)) if ref_models else None)
    log = {"asr": args.asr, "limit": args.limit, "started_at": now_utc(), "git_commit": git_commit(),
           "git_dirty_tracked": git_dirty_paths(), "config_version": cfg["version"],
           "evaluator_model": model, "reference_model_at_start": client.reference_model,
           "entries": [], "calls": client.calls}
    log_path = log_dir / f"evaluate_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{os.getpid()}.json"
    abort = None
    try:
        for i, s in enumerate(todo, 1):
            sid, st = s["sample_id"], status[s["sample_id"]]
            client.current = sid
            t0, n0, stage = time.time(), len(client.calls), "load"
            empty = sid in rule
            entry = {"sample_id": sid, "empty_response_rule": empty}
            try:
                gold_text = json.load(open(gold_dir / f"{sid}.json", encoding="utf-8"))["text"]
                text = "" if empty else json.load(open(stt_dir / f"{sid}.json", encoding="utf-8"))["whisper_transcript"]
                entry["transcript_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
                stage = "closed"
                if st["closed"] is not True:
                    write_json_atomic(ent_dir / f"{sid}_closed.json", {
                        "sample_id": sid,
                        "gold_entities": extract_closed_vocab_entities(gold_text),
                        "whisper_entities": extract_closed_vocab_entities(text)})
                stage = "open"
                if st["open"] is not True:
                    if empty:
                        rec = {"sample_id": sid, "gold_entities": None, "whisper_entities": dict(EMPTY_OPEN),
                               "empty_response_rule": "docs/cross_asr_spec.md 12.2 (no API call)"}
                    else:
                        rec = {"sample_id": sid,
                               "gold_entities": extract_with_retry(client, model, gold_text, "gold"),
                               "whisper_entities": extract_with_retry(client, model, text, "whisper")}
                    write_json_atomic(ent_dir / f"{sid}_open.json", rec)
                stage = "matching"
                closed = json.load(open(ent_dir / f"{sid}_closed.json", encoding="utf-8"))
                opened = json.load(open(ent_dir / f"{sid}_open.json", encoding="utf-8"))
                scaffold = scaffolds[s["scenario_id"]]
                gold_open = scaffold_to_open_vocab(scaffold)
                matched = {"sample_id": sid,
                           "closed_vocab_matches": match_closed_vocab(scaffold_to_closed_vocab(scaffold),
                                                                      closed["whisper_entities"])}
                if empty:
                    om = empty_open_matches(gold_open)
                    if not is_valid_match_result(om):
                        raise RuntimeError("empty-response rule produced an invalid match structure")
                    matched["open_vocab_matches"] = om
                    matched["empty_response_rule"] = "docs/cross_asr_spec.md 12.2 (no API call)"
                else:
                    matched["open_vocab_matches"] = match_with_retry(client, model, gold_open,
                                                                     opened["whisper_entities"], sid)
                write_json_atomic(ent_dir / f"{sid}_matched.json", matched)
            except KeyboardInterrupt:
                abort = f"{sid}: interrupted by user (stage {stage})"
            except FatalAPIError as e:
                abort = f"{sid}: {e} (stage {stage})"
            except SystemExit as e:            # write_json_atomic refusing to overwrite
                abort = f"{sid}: {e} (stage {stage})"
            except Exception as e:             # v4 retry loops exhausted (RuntimeError) or anything unexpected
                abort = f"{sid}: {type(e).__name__}: {e} (stage {stage})"
                entry["traceback"] = traceback.format_exc(limit=6)
            new = client.calls[n0:]
            entry.update(status="failed" if abort else "processed", calls=len(new),
                         seconds=round(time.time() - t0, 2))
            if abort:
                entry["error"] = abort
            log["entries"].append(entry)
            if abort:
                print(f"[{i}/{len(todo)}] {sid} FAILED: {abort}")
                break
            tin = sum(c.get("input_tokens") or 0 for c in new)
            tout = sum(c.get("output_tokens") or 0 for c in new)
            print(f"[{i}/{len(todo)}] {sid} ok ({len(new)} calls, {tin}/{tout} tokens, {time.time() - t0:.1f}s)"
                  + ("  [empty-response rule]" if empty else ""))
    except KeyboardInterrupt:
        abort = abort or "interrupted by user (between samples)"
    finally:
        ok_calls = [c for c in client.calls if c.get("ok")]
        n_proc = sum(1 for e in log["entries"] if e["status"] == "processed" and not e["empty_response_rule"])
        log["finished_at"] = now_utc()
        log["summary"] = {
            "processed": sum(1 for e in log["entries"] if e["status"] == "processed"),
            "calls": len(client.calls), "failed_calls": len(client.calls) - len(ok_calls),
            "response_models": dict(Counter(c.get("response_model") for c in ok_calls)),
            "input_tokens": sum(c.get("input_tokens") or 0 for c in ok_calls),
            "output_tokens": sum(c.get("output_tokens") or 0 for c in ok_calls),
            "abort": abort,
        }
        if n_proc:
            log["summary"]["per_sample_tokens"] = {"input": round(log["summary"]["input_tokens"] / n_proc),
                                                   "output": round(log["summary"]["output_tokens"] / n_proc)}
        try:
            write_json_atomic(log_path, log)
        except BaseException as e:
            print(f"WARNING: run log could not be written ({type(e).__name__}: {e})")
        try:
            lock.unlink()
        except FileNotFoundError:
            pass

    sm = log["summary"]
    print(f"\n=== processed={sm['processed']} calls={sm['calls']} failed_calls={sm['failed_calls']} "
          f"tokens in/out={sm['input_tokens']}/{sm['output_tokens']} -> log {log_path}")
    print(f"response models    : {sm['response_models']}")
    if "per_sample_tokens" in sm:
        print(f"per sample (mean)  : {sm['per_sample_tokens']['input']} input / "
              f"{sm['per_sample_tokens']['output']} output tokens")
    complete = sum(1 for s in samples if stage_status(ent_dir, s["sample_id"])["matched"] is True)
    print(f"evaluated now      : {complete}/300")
    if abort:
        print(f"RUN STOPPED: {abort}")
        return 2
    if complete < 300:
        print("EVALUATE PARTIAL - samples not yet evaluated remain (e.g. because of --limit)")
        return 0
    if (res_dir / "ccer_results.csv").exists() or (res_dir / "ccer_summary.json").exists():
        print(f"results already exist in {res_dir} - not overwritten")
        return 0
    from src.evaluation.ccer_eval import run_ccer_evaluation
    run_ccer_evaluation(str(ent_dir), str(gold_dir), str(res_dir))
    print("EVALUATE COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
