# Cross-ASR Robustness Experiment — Protocol (Version 1.0)

Frozen: 2026-11-03 · Branch: `cross-asr` · Baseline tag: `v4-kosmi-baseline` · Config: `configs/cross_asr.yaml`

This is an extension of the completed CCER v4 study, prepared for the KOSMI Fall 2026 e-poster
(submission 2026-11-09). It does not redesign the study. It asks whether the documentation-style
effect observed with `whisper-1` is also observed with other ASR systems, using the same audio and
the same frozen evaluator. Until submission, the research questions, evaluator, ASR set and
analysis below are not changed; if a condition proves infeasible, the change and its reason are
recorded in Section 10.

## 1. Research questions

| RQ | Question | Role |
|---|---|---|
| RQ1 Cross-ASR consistency | Does Formal's lower CCER relative to Clinical and Telegraphic hold for other ASR systems? | Primary |
| RQ2 Effect magnitude | Do the Formal−Clinical and Formal−Telegraphic CCER differences vary across ASR systems? | Primary |
| RQ3 Evaluation validity | How might ASR-specific output notation and evaluation run time affect interpretation of CCER? | Supporting |

Expectations (H1: Formal remains lowest; H2: the size of the gap differs by system) are targets
for testing, not conclusions to be confirmed. Results in either direction are reported.

## 2. Baseline and preservation

- Tag `v4-kosmi-baseline` → `2f33d88` (HEAD of `main` on 2026-11-03).
- CCER v4 evaluator code last changed in `f1d3932`; v4 SAP results produced in `0978723`.
  No evaluator code changed between `f1d3932` and `2f33d88`.
- Reproduction (2026-11-03, no LLM calls): recomputing CCER from saved
  `data/entities/*_matched.json` reproduced all 300 sample-level scores in
  `results/full_100_v4/ccer_results.csv` and the pooled values in `ccer_summary.json`
  (Formal 0.8417, Clinical 1.1682, Telegraphic 1.2134; gold entities 1,415 per style).
- The tag points to a commit only. It does **not** include:
  - an uncommitted change in `results/full_100_v4/sap3_weight_sensitivity_summary.csv`
    (C_Narrow Formal mean 0.470872 → 0.470871; file modified ~10 min after commit `0978723`;
    cause not established — presumed floating-point rounding from a re-run of SAP3);
  - untracked files, including 385 of the 400 audio files.
- Both are preserved in a hash-verified external backup (`~/ccer_backup_20261103_203614`;
  tracked, untracked and audio files SHA-256 verified; `.env` and other git-ignored files copied
  but not hash-verified; `venv/` excluded).
- Existing code, audio, transcripts and results are read-only. The SAP3 change is neither
  reverted nor committed. On this branch only new experiment files are added to commits,
  each by explicit path.

## 3. Data

| Item | Setting |
|---|---|
| Scenarios | 100 existing scaffolds (`data/scenarios/`) |
| Styles | formal_template, clinical_charting, telegraphic_icu |
| Audio | 300 existing files (`data/audio/`), unchanged; Hybrid (100) excluded |
| Gold | existing scaffold (matching) and gold text (WER) |
| New data / training | none |

`src/cross_asr/manifest.py` records size, SHA-256, duration and decode check for the 300 files
and fixes the pilot set (10 scenarios × 3 styles, seed 20261103).

## 4. ASR systems

| System | Transcription | Settings |
|---|---|---|
| `whisper1` | existing transcripts reused (no new call) | `whisper-1`, language `ko`, no prompt |
| `gpt4o_transcribe` | new | `gpt-4o-transcribe`, language `ko`, no prompt |
| `clova_enko` | new | CLOVA Speech `/recognizer/upload`, language `enko`, completion `sync`, `diarization.enable=false` (added 2026-11-04, Section 10), other params API default; no boostings/forbiddens/domain boosting |

Settings were fixed from documentation before any pilot output was seen. Because language
options differ in meaning across systems, the comparison is between ASR *systems* as configured,
not between architectures. No system receives prompts, vocabulary boosting or term lists.
The pilot judges only feasibility (runs without error, output saved, cost and time); settings are
not tuned on pilot results.

## 5. Evaluation

- Evaluator: CCER v4 unchanged — entity definitions, weights, extraction and matching prompts,
  gold scaffold, error rules. New code calls existing functions with per-ASR paths; no evaluator
  code is copied or modified.
- All three systems are evaluated in the same current run (2026-11), including re-evaluation of the
  existing `whisper-1` transcripts (open-vocab extraction and semantic matching are re-run).
- Evaluation LLM: `claude-sonnet-5` (from `configs/config.yaml`). If unavailable, all three
  systems use the same substitute and the change is recorded in Section 10.
- Existing call settings are kept as they are. Note: the extraction and matching calls do not set
  `temperature`, so the API default applies and outputs are not deterministic.
- Per sample: 3 LLM calls (gold-text extraction, transcript extraction, matching; the gold-text
  extraction result is not used by matching, which uses the scaffold). ≈900 calls per system,
  ≈2,700 in total, plus 600 new transcriptions.
- Logged per run: API-reported model ID, token usage, timestamps, git commit, config version.
- Observed cross-run evaluation discrepancy: September 2026 `whisper-1` evaluation vs November
  2026 re-evaluation of the same transcripts. This is a single observation between two runs, not
  an estimate of the evaluator's general variability.

## 6. Outcomes

- Primary: pooled micro-CCER per system × style, computed with the v4 formula
  (Σ weighted errors / Σ gold entities).
- Primary contrasts per system: Δ_FC = CCER_Formal − CCER_Clinical,
  Δ_FT = CCER_Formal − CCER_Telegraphic (negative = Formal lower). Because the three styles of a
  scenario share the same scaffold, Δ equals the gold-count-weighted mean of per-scenario differences.
- Sample-level mean CCER (used by the Friedman/Wilcoxon tests and SAP3) differs from pooled
  micro-CCER and is labelled separately in all tables.
- Secondary: WER (normalized), Entity F1, ASR × style differences of Δ, WER–CCER Spearman.

## 7. Statistical analysis

| Analysis | Method |
|---|---|
| Micro-CCER per style | pooled aggregation |
| Δ_FC, Δ_FT | 95% percentile CI, scenario-level bootstrap (≥2,000 resamples, seed 20261103); the same resample indices are applied to all systems and styles, and pooled values are recomputed in each resample |
| Style test | Friedman + Kendall's W on sample-level CCER (as in v4) |
| Pairwise | Wilcoxon signed-rank + Holm (as in v4) |
| System × style | differences of Δ between systems (joint bootstrap) — secondary |
| WER–CCER | Spearman — secondary |

## 8. Notation diagnostics (no new normalization rules)

- Full count over each system's 300 transcripts: Korean numerals, "퍼센트", Korean
  transliterations of clinical abbreviations, and related patterns.
- Case review per system, entity-level, with fixed seed:

| Stratum | Size | Unit |
|---|---|---|
| Random transcripts | 10 | all entity records in those transcripts |
| Random error records | 5 | entity record |
| Notation-suspect records | 5 | entity record |

Labels: ASR error / evaluator miss due to notation / correct / undetermined. Strata are
reported separately and not pooled into an overall rate; the sample is diagnostic and is not
used to estimate a population error rate.

Interpretation rule: if Formal's advantage weakens for a system whose output contains many
notations the v4 evaluator does not recognise, the ASR effect and evaluator notation bias are
reported as not separable.

## 9. Scope of claims

Can claim: how consistently the style effect appears across ASR systems on the same synthetic
ICU audio; how its size differs by system; limits on interpretation from notation and run time.

Cannot claim: generalisation to real ICU nurse speech; causal superiority of an ASR architecture;
that CCER measures patient harm; general evaluator stability from two runs.

Evaluation-procedure differences from the September v4 run (Sections 12.5 and 12.6) are reported
as methodological limitations.

## 10. Change log

| Date | Change | Reason |
|---|---|---|
| 2026-11-03 | Protocol frozen (Version 1.0) | — |
| 2026-11-04 | CLOVA params: added `diarization: {enable: false}` (before: not specified, i.e. API default `enable: true`) | See note 10.1 |
| 2026-11-04 | Protocol revision 1.1: CLOVA excluded from main analysis; Google Chirp 3 added; language-configuration conditions A/B; scope, TTS and analysis priorities fixed | See Section 11 |
| 2026-11-04 | Protocol revision 1.2: Condition B extended from pilot 30 to all 300 (deviation from 11.2) | See Section 11.5 |
| 2026-11-04 | Transcription completed; one empty response (chirp3_auto); suspected TTS defects and their handling recorded | See Section 12 |
| 2026-11-05 | Gold-text extraction exception rule (unused field; API errors still stop the run) | See Section 12.5 |
| 2026-11-05 | Completed nested-JSON repair for open-vocab extraction (parsing only; prompts and settings unchanged) | See Section 12.6 |

### 10.1 CLOVA diarization setting (2026-11-04)

- What happened: the access check (`--pilot --limit 1`, sample `scenario_007_clinical_charting`, 1 request)
  returned HTTP 400 `{"result":"ERROR_REQUEST_PARAMETER","message":"speaker detect is off"}`.
  No transcript was produced and no output file was written.
- Presumed cause (not confirmed): the request did not set `diarization`, so the API default
  `diarization.enable = true` (speaker diarization) applied, while speaker detection appears to be
  off for the CLOVA Speech domain used. The error code is not listed on the local-file recognition
  page; the cause is inferred from the message and the documented default.
- Parameter check: Ncloud API docs, CLOVA Speech local file recognition — `params.diarization`
  (Object, optional) and `params.diarization.enable` (Boolean, optional, default `true`;
  `true` = speaker diarization, `false` = no speaker diarization).
- Change: `diarization: {enable: false}` added to `asr_systems.clova_enko.params` in
  `configs/cross_asr.yaml`. All other CLOVA params remain API defaults; language `enko` and
  completion `sync` unchanged. `version` stays "1.0" so that existing whisper1/gpt4o outputs remain
  valid; CLOVA outputs record the full `params` in `stt_metadata`, so the setting is traceable.
- Rationale: the audio is single-speaker TTS and diarization only assigns speaker labels; it is not
  a transcription-text setting. The decision was made before any valid CLOVA transcript existed,
  so it was not informed by CLOVA output.
- Whether this resolves the error is verified by one further request (`--limit 1`).

## 11. Protocol revision 1.1 (2026-11-04)

Sections 1–10 remain the record of Version 1.0. Where this section differs, it takes precedence.
The config key `version` stays "1.0" because the settings of the existing conditions (`whisper1`,
`gpt4o_transcribe`) are unchanged and their outputs remain valid; revision 1.1 only adds conditions.

### 11.1 ASR systems

- **CLOVA Speech excluded from the main analysis.** After the diarization fix (note 10.1), one
  CLOVA `enko` transcript (`scenario_007_clinical_charting`) rendered most Korean segments in
  Latin-script romanization (e.g. "aquaro eonam" for "악화로 입원함") and lost most vital-sign values.
  The exclusion was decided after viewing this single transcript and a 6-sample whisper-1 vs
  gpt-4o-transcribe comparison; it is therefore a results-informed change and is reported as such.
  The CLOVA code, the CLOVA transcript, the `ko-KR` diagnostic and all run logs are kept.
- **Google Speech-to-Text V2 `chirp_3` added** as the third system. Settings fixed before any Chirp
  output existed: location `us` (multi-region), synchronous `Recognize` with inline MP3 and
  `AutoDetectDecodingConfig`, no adaptation/phrase hints, no denoiser; credentials via Application
  Default Credentials. All 300 files are within the synchronous limit (60 s / 10 MB; longest 59.4 s,
  largest 0.95 MB). **Inclusion criterion: feasibility only** (runs without error, outputs saved,
  cost and time); transcription quality is a result and is not a reason for exclusion.
- Note: the OpenAI API reference (accessed 2026-11-04) lists `whisper-1` and `gpt-4o-transcribe` as
  deprecated with shutdown on 2027-02-26; this affects later reproduction, not this study.

### 11.2 Language-configuration conditions

| Condition | whisper-1 | gpt-4o-transcribe | chirp_3 | Scope |
|---|---|---|---|---|
| A (Korean specified) | `language="ko"` (existing) | `language="ko"` | `language_codes=["ko-KR"]` | all 300, **primary** |
| B (not specified / auto) | `language` omitted | `language` omitted | `language_codes=["auto"]` | pilot 30 only, **exploratory** |

- The scope (A: 300; B: pilot 30) was decided on 2026-11-04 for schedule reasons, **before any
  Condition B output existed**. B is not extended or dropped on the basis of its results.
- The two conditions are **not equivalent mechanisms across systems**: the OpenAI reference marks
  `language` as optional and says supplying it improves accuracy and latency, but does not document
  behaviour when it is omitted; Chirp 3 `auto` is documented as inferring the most prevalent language.
  Neither documents intra-sentence code-switching. Language-configuration differences are therefore
  interpreted per system, not as one common "auto-detection effect".
- Condition labels: A = `whisper1`, `gpt4o_transcribe`, `chirp3_ko`;
  B = `whisper1_auto`, `gpt4o_transcribe_auto`, `chirp3_auto` (config keys enforce `scope: pilot`).
- The existing whisper-1 + `ko` result is the reference condition for comparison with the
  completed CCER v4 study.

### 11.3 Other scope decisions

- **TTS:** the existing single TTS engine/voice only; cross-TTS is deferred to the journal extension.
- **whisper-1 repeatability diagnostic (planned, low priority):** one representative file per style
  (`scenario_007_clinical_charting`, `scenario_012_formal_template`, `scenario_018_telegraphic_icu`),
  3 repeated `language="ko"` transcriptions each, stored under `data/cross_asr/diagnostics/`.
  Differences from the September transcripts cannot separate a change over time from run-to-run
  stochasticity; repeated runs only indicate the size of the latter.
- **Evaluation reuse:** whether the September CCER v4 evaluation of the whisper-1 transcripts can be
  reused instead of re-evaluation (Section 5) will be decided after a same-condition check; until
  then the Version 1.0 rule (re-evaluate all conditions in the same run) applies. Evaluation rules
  are not changed.
- **Notation diagnostics (Section 8) additionally record** Hangul transliteration or translation of
  English clinical terms, English spelled-out numbers/units ("percent", "milligram") and
  romanized Korean, and classify CCER v4 misses of semantically preserved expressions separately.
  Primary evaluation rules are not modified.

### 11.4 Analysis priorities

1. Primary (Condition A): per-system pooled micro-CCER by style, paired Δ_FC and Δ_FT with joint
   scenario-level bootstrap CIs; Friedman / Wilcoxon-Holm as in v4.
2. Condition B: exploratory descriptive statistics and error-case analysis only.
3. Mixed-effects models (style × system, style × language configuration): only if time allows.
4. Limitation stated in all outputs: language configuration does not mean the same thing across
   systems (11.2).

### 11.5 Revision 1.2 (2026-11-04): Condition B extended to all 300

- Decision: Condition B (`whisper1_auto`, `gpt4o_transcribe_auto`, `chirp3_auto`) is extended from
  the pilot 30 to all 300 samples, so that A and B can be compared on the same sample set.
- Timing: decided on 2026-11-04 after Condition A was complete and after the 30 `whisper1_auto`
  pilot transcripts had been generated; at that point `gpt4o_transcribe_auto` had no output and
  `chirp3_auto` had 1 test output. No Condition B transcript had been evaluated or compared with
  Gold; only the run progress lines (first ~40 characters of each transcript) had been displayed.
  The reason was the low additional cost and time (about USD 3.7 at list prices), not Condition B results.
- This is a deviation from the 11.2 statement that B would not be extended, and is reported as such.
- Analysis: Condition A remains the primary analysis and Condition B remains exploratory. The
  pre-specified pilot 30 subset of B is reported as originally specified (descriptive); the
  300-sample B analysis is reported as an additional exploratory analysis, labelled as an extension.
- Implementation: `scope: pilot` removed from the three Condition B keys in
  `configs/cross_asr.yaml`. Scope is not part of the reuse metadata, so outputs already generated
  remain valid and are not re-sent; `version` stays "1.0".

## 12. Transcription run notes (2026-11-04)

### 12.1 Completion

| Condition | Valid outputs | How produced |
|---|---|---|
| `whisper1` (A) | 300 | existing v4 transcripts reused (0 requests) |
| `gpt4o_transcribe` (A) | 300 | 6 diagnostic + 294 (294 requests) |
| `chirp3_ko` (A) | 300 | 1 access test + 299 (299 requests) |
| `whisper1_auto` (B) | 300 | 30 pilot + 270 after revision 1.2 |
| `gpt4o_transcribe_auto` (B) | 300 | 300 |
| `chirp3_auto` (B) | 299 | 1 access test + 187 + 111; 1 empty response (12.2) |

In the run summaries of the main runs (after revision 1.1) the number of API requests equals the
number of outputs written, except for the stopped `chirp3_auto` run (188 requests, 187 outputs; the
extra request is the empty response in 12.2), so no retry occurred. Run logs in
`data/cross_asr/<condition>/logs/` are kept locally.

### 12.2 Empty response: `chirp3_auto` / `scenario_063_telegraphic_icu`

- One request for this sample returned without error but with no transcript text. By design an
  empty transcript stops the run (to catch configuration faults), so the run stopped and no file was
  written for this sample. The raw response is not retained; the sample was not re-requested.
- The remaining 111 samples were transcribed with `--samples` listing all other samples (no code change).
- Handling rule, fixed before any evaluation: in the CCER evaluation this sample is scored for
  `chirp3_auto` as an empty transcript (no entity extracted, so every gold entity counts as an
  omission). The rule is applied in the evaluation step, not by writing a file into
  `stt_transcripts/`. Reported as 1 empty response out of 300.

### 12.3 Suspected TTS defects

- `scenario_007_clinical_charting`: on listening (2026-11-04), some vital-sign numbers appear to be
  spoken differently from the Gold text (BP 130/85, HR 95, BT 37.2); all ASR systems mis-transcribe
  this span.
- `scenario_063_telegraphic_icu`: on listening (2026-11-04), the first part (age to vital signs) is
  unintelligible. All five other ASR outputs fail on this span (Condition A CER 0.73-0.94;
  gpt-4o-transcribe produced Irish-like text), while the English span that follows is mostly recognized.
- Audio and Gold texts are not modified. Both samples are also part of the completed v4 baseline,
  whose results are not changed.
- Screening: a fixed criterion (CER >= 0.5, as computed by `compare_transcripts.py`, in all three
  Condition A systems) flagged only `scenario_063_telegraphic_icu`. The criterion detects whole-span
  failures, not number-level mispronunciations such as in `scenario_007`; further cases may be
  checked by limited listening and will be added here.
- Analysis: the primary analysis includes both samples. A sensitivity analysis excludes scenarios
  007 and 063 (all three styles, so that paired style comparisons stay balanced). Errors in these
  spans are not interpreted as ASR errors alone.

### 12.4 Chirp 3 language detection (descriptive)

- `chirp3_ko`: `detected_language_codes` = `ko-KR` for all 300.
- `chirp3_auto`: `ko` 245, `en` 52, `gn` 1, `und` 1, plus the empty response (12.2).
  Reported descriptively within Condition B.

### 12.5 Gold-text extraction exception (2026-11-05)

- Background: per sample, the v4 procedure makes one open-vocab extraction call on the gold text.
  Its result is not used by matching or CCER (matching uses the content scaffold; Section 5).
  For `whisper1` / `scenario_075_clinical_charting` this call returned a successful API response
  containing only `symptoms` (5 of the 6 required fields missing) in 3 of 3 v4 attempts, and again in
  3 of 3 attempts in a resumed run (output 134-156 tokens, far below `max_tokens` 1024; response
  model `claude-sonnet-5`). The run stopped both times.
- Rule (decided 2026-11-05): if the gold-text extraction fails the v4 structure check
  (`is_valid_extraction`) in all 3 v4 attempts and every attempt was a successful API response,
  `gold_entities` is stored as null; the rule, cause, number of attempts and output tokens are
  written to `_open.json` and the run log. Transcript extraction and semantic matching then proceed
  unchanged.
- Not covered (the run stops as before): any API error in any attempt (authentication, connection,
  rate limit, server error, model change), and any failure of transcript extraction or semantic
  matching.
- Effect: none on matching or CCER (the field is not used). Prompts, scaffold, CCER formula and the
  September v4 results are unchanged.
- Occurrences: listed per condition when the evaluation is complete. Known so far:
  `whisper1` / `scenario_075_clinical_charting`.

### 12.6 Completed nested-JSON repair for open-vocab extraction (2026-11-05)

- Diagnosis (2 diagnostic calls with the unchanged v4 extraction call; raw responses in
  `data/cross_asr/diagnostics/eval_extraction/`): the failures in 12.5 (`whisper1` /
  `scenario_075_clinical_charting`, gold text) and in `whisper1` / `scenario_083_telegraphic_icu`
  (transcript extraction; the run stopped after 3 of 3 attempts) were single tool_use responses in
  which the model returned the complete extraction as a JSON string inside the `symptoms` field.
  The v4 function `repair_nested_json_string` (added for this case in `926f938`) restores only
  `symptoms` and drops the other five fields, so the v4 check fails. In the diagnostic call the 083
  transcript extraction came back normally (intermittent); the 075 gold-text response was nested again.
- Rule (in `src/cross_asr/evaluate.py`; v4 code unchanged): an extraction response is used as the
  parsed object only if all hold: (1) the first extraction tool_use block has exactly one key,
  `symptoms`; (2) its value is a string that parses to a JSON object; (3) the parsed object passes
  the v4 check `is_valid_extraction`. Nothing is generated, modified or filled with defaults. Any
  other failure follows the v4 retry and stop policy (and 12.5 for the unused gold-text field).
  Matching responses are never modified.
- Scope: gold-text and transcript extraction of all conditions evaluated after this change. The 248
  `whisper1` samples evaluated before it are not changed or re-evaluated; a nested response fails the
  v4 check, so none of them used one.
- Logged: each repaired call has `nested_json_repaired: true` with sample_id and stage
  (gold / transcript) in the run log, and each run summary lists them. Counts per condition and
  stage are reported here when the evaluation is complete.
- Method difference from v4 (stated as a limitation): in the September run such responses were
  discarded and the call retried by the v4 loop; here they are used. Both are complete extractions
  by the same model, so no systematic score difference is expected, but the two runs are not
  procedurally identical.
