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
| 2026-11-05 | Evaluation of all six conditions completed; run notes recorded | See Section 12.7 |
| 2026-11-05 | Notation diagnostics results and manual check of notation-suspect records | See Section 12.8 |
| 2026-11-05 | Post hoc evaluator sensitivity analysis S1 (Korean particle attachment) designed; v4 stays primary | See Section 13 |
| 2026-11-06 | S1 results and manual review of Condition A (70 records) | See Section 13.1 |
| 2026-11-17 | Post hoc recomputations for the KOSMI 2026 poster | See Section 13.2 |

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

### 12.7 Evaluation run notes (2026-11-05)

| Condition | Claude calls | Failed calls | 12.6 repairs (transcript / gold) | 12.5 gold-text null | Gold count differing from scaffold |
|---|---|---|---|---|---|
| `whisper1` | 916 (incl. 9 in the 3-sample trial and calls of stopped runs) | 0 | 3 / 0 | 1 (`075_clinical_charting`) | `063_clinical_charting` 15 -> 16 |
| `gpt4o_transcribe` | 900 | 0 | 3 / 3 | 0 | none |
| `chirp3_ko` | 902 | 0 | 0 / 0 | 0 | none |
| `whisper1_auto` | 901 | 0 | 0 / 0 | 0 | none |
| `gpt4o_transcribe_auto` | 903 | 0 | 1 / 0 | 0 | `063_clinical_charting` 15 -> 16 |
| `chirp3_auto` | 900 (299 samples; `063_telegraphic_icu` by the 12.2 rule, no call) | 0 | 0 / 0 | 0 | none |

- Every call reported the model `claude-sonnet-5`; there was no API error. Calls above 3 per sample
  are v4 structure-check retries.
- 12.6 repairs: `whisper1` 083_telegraphic, 091_telegraphic, 095_clinical (transcript);
  `gpt4o_transcribe` 030_formal, 048_clinical, 076_clinical (transcript), 034_clinical, 056_clinical,
  075_clinical (gold); `gpt4o_transcribe_auto` 006_telegraphic (transcript).
- Gold count (recorded only, not corrected; decided 2026-11-05): the scaffold of `scenario_063` has
  no intervention, but in 2 of 6 conditions the LLM matcher listed a gold intervention "none" for
  `scenario_063_clinical_charting`, so the Clinical gold total is 1,416 instead of 1,415 there. v4
  counts gold entities from the matcher output; the rule is unchanged. Effect on pooled Clinical
  CCER < 0.001.
- Cross-run (same `whisper1` transcripts, September v4 vs November): 244/300 identical sample CCER,
  max absolute sample change 0.4; pooled Formal / Clinical / Telegraphic 0.8417 / 1.1682 / 1.2134
  (September) vs 0.8367 / 1.1801 / 1.1943 (November).
- Analysis output: `results/cross_asr/analysis_prelim_condA/` (`src/cross_asr/analysis.py`). Although
  named "prelim", it was produced after all six conditions were complete and includes Condition B; the
  analysis is deterministic, so it is the final analysis output.

### 12.8 Notation diagnostics results (2026-11-05)

Output: `results/cross_asr/notation_diagnostics/` (`src/cross_asr/notation_diagnostics.py`, Section 8).
Primary CCER values and evaluation rules are unchanged; the figures below are diagnostic.

- Finding: the v4 closed-vocab extractor uses `\b` word boundaries, so an ASCII token followed
  directly by a Hangul particle ("2g을", "IV로", "C-line을") is not read, and correctly transcribed
  route, dose, frequency and device information is scored as an omission. Formal Template has about 6
  such forms per transcript (Clinical about 2.4, Telegraphic about 1), in every condition.
- Lenient closed-vocab rewrite (particle spacing, device aliases, Korean unit words; open-vocab
  unchanged), Formal Template: closed records changed 143 (`whisper1`), 167 (`gpt4o_transcribe`),
  204 (`chirp3_ko`), of which 96-99% change from omission to matched; Formal CCER 0.837 -> 0.652,
  0.636 -> 0.429, 0.672 -> 0.415. Clinical and Telegraphic change by 0.01 or less.
- Condition A contrasts, v4 vs lenient (95% joint bootstrap CI): Delta_FT `whisper1` -0.358
  [-0.431, -0.282] vs -0.539 [-0.615, -0.460]; `gpt4o_transcribe` -0.160 [-0.251, -0.070] vs -0.364
  [-0.451, -0.279]; `chirp3_ko` -0.113 [-0.209, -0.028] vs -0.367 [-0.464, -0.279]. Delta_CT is
  essentially unchanged (`gpt4o_transcribe` 0.129 vs 0.124).
- Manual check (2026-11-05, user): the 15 notation-suspect records of the case-review sheets
  (5 per Condition A system, fixed seed) were all labelled "evaluator miss due to notation" (15/15):
  dose or route written correctly with an attached particle, or a device written as a
  transliteration ("폴리 캐테터", "네이잘 캐뉼라"). This stratum is diagnostic and does not estimate a
  population rate; the random-transcript and random-error strata are not yet labelled.
- Interpretation (Section 8 rule): the Formal advantage is present in every system under both
  scorings, but its attenuation in `gpt4o_transcribe` and `chirp3_ko` relative to `whisper1` is
  partly due to this evaluator notation bias, which is larger for those systems; the ASR effect on the
  size of the Formal advantage and the evaluator bias are therefore not fully separable. The
  September v4 Formal value (0.8417) is affected by the same bias, which is reported as a v4
  limitation.
- Known issue: in the case-review sheets the reviewer column is named `label`, which overwrites the
  vital-sign `label` field of flattened records; to be renamed before the remaining strata are labelled.

## 13. Post hoc evaluator sensitivity analysis S1: Korean particle attachment (2026-11-05)

**Status.** This analysis was designed after the notation diagnostics (12.8), i.e. after the results
were seen. The v4 evaluation (Sections 5-7, 12) remains the primary analysis; S1 is reported only as
an evaluator sensitivity analysis. No v4 code, gold scaffold, ASR transcript or earlier result is
changed or overwritten.

**Where the error arises.** Only in closed-vocab extraction (`closed_vocab_extractor.py`). 41 v4
patterns for ASCII tokens end with the word boundary `\b` (route 12, frequency 12, device 6,
vital-sign labels 10, dose 1). Python `re` treats Hangul as word characters, so in "IV로" or "2g을"
there is no boundary after the token and the token is not extracted; the matcher then records an
omission (or, with one omission and one extra value, a substitution). Matching, flattening, weights,
the scaffold gold and the open-vocab (LLM) steps are not involved.

**Rule S1 (only change).** In those 41 patterns the final `\b` becomes
`(?:\b|(?=(?:PARTICLE)(?:\s|[PUNCT]|\Z)))`: every v4 match is kept, and an ASCII token followed
directly by one of 27 particles is also accepted only when the particle is followed by whitespace,
punctuation `.,;:!?)]}"'/·…` or the end of the text. Particles: 으로써 으로 에서 에게 까지 부터 이며 이고 이다
이나 이라 라고 마다 와 과 을 를 이 가 은 는 의 에 로 도 만 씩. Pattern flags (case-insensitivity) are kept.
Implemented in `src/cross_asr/ko_particle_extractor.py` by re-binding the v4 function code to a copy of
the v4 namespace in which only these 41 pattern objects are replaced; the v4 module is not edited.

**Not changed / not covered.** Leading boundaries; Korean patterns; value, unit and canonical forms;
the dose ownership hierarchy; matching (including duplicate mentions); flattening; weights; gold;
open-vocab results (reused unchanged). Not handled by S1: transliterations ("캐테터", "네이잘",
"C라인"), Korean unit words ("밀리그램", "퍼센트"), Sino-Korean numerals, non-particle Hangul suffixes
("IV주사", "IV투여"), ASR misspellings ("IB로" is not corrected).

**False-positive boundaries (unit tests, `tests/test_ko_particle_extractor.py`).** Not accepted:
IVIG, IVF로, IB로, PR간격, IV주사, IV투여, IV로ABC, IV로123, IV로써먹, IV로-1, BPM, NCT, Foleyx를, 2gram을,
40mg을test, Q8H로ABC, STATUS로; 40mg씩 without administration context (v4 dose rule). Tests also check
the 41-pattern count, that v4 itself is unchanged, every particle (including prefix pairs such as
이/이며/이다 and 로/으로/으로써), case-insensitivity, identical output on texts without attached
particles, and that every span matched by a v4 pattern is matched by its S1 pattern.

**Expected side effects (kept, audited, not corrected).** Because S1 reads more tokens, unchanged v4
rules can act on them: a repeated mention can become an extra value scored as hallucination
(e.g. "IV로" for the drug and "IV 플루이드" for fluids); a fluid volume can be read as a dose when the
fluid word is not in the v4 denylist ("플루이드"); a newly read vital-sign label can take a number that
v4 had scored as a dose hallucination ("BP는 60mg"). S1 extraction is therefore not a strict superset
of v4 at the sample level.

**Re-evaluation.** `src/cross_asr/sensitivity_ko_particle.py`; no Claude or ASR call. For the
September v4 run and the six conditions, closed-vocab matches are recomputed from the saved
transcripts and the scaffold (the v4 matches are re-derived first; any mismatch stops the run);
open-vocab matches are reused from the saved match files. A read-only mode (`--verify-v4`) runs the
v4 re-derivation check on the real data and writes nothing. `--run` writes into a temporary folder
and moves it to the output folder only after every output file exists; on any failure the temporary
folder is removed. Record pairing for the transition table is by (entity_type, label, gold_value);
when a key occurs more than once in a sample and the judgements differ, the key is reported once as
an `ambiguous_group` (v4 judgements -> S1 judgements) and not as individual transitions; aggregate
counts do not depend on pairing (`tests/test_sensitivity_ko_particle_align.py`). Statistics use the functions of
`src/cross_asr/analysis.py` with the same seed (20261103, 2,000 resamples), for all 100 scenarios and
for n = 98 (scenarios 007 and 063 excluded). Outputs in `results/cross_asr/sensitivity_ko_particle/`:
pooled CCER, ranks, Delta with CIs and between-system differences (v4 vs S1), Friedman and
Wilcoxon-Holm (S1), error-type counts, the full v4 -> S1 transition table, every changed record,
a side-effect audit of every changed record not ending as matched (automatic flag: duplicate
mention / possible fluid volume / other insertion / new error on a gold entity / removed; manual
review column), a stratified review sample of omission -> matched changes (2 per condition x style
x entity type, seed 20261103; written with its full column structure even when there is no such
change), the 15 manually reviewed notation-suspect records (extraction and final matching reported
separately; for each, the number of gold records with that value, the number matched under v4 and
S1, and the match level all / partial / none; improvement is not required; a code-checkable fact
is recorded - whether an ASCII form of the value occurs in the transcript and whether it is followed
by a listed particle - and every case that is not fully extracted and matched is marked for human
review rather than given an automatic cause; helper tests in
`tests/test_sensitivity_ko_particle_helpers.py`), meta.json (code
hashes, particles, regexes, seeds, pairing rule) and inputs_sha256.csv (configuration files, pilot
list, case-review sheets, the 300 generated-text files, all 100 scaffold files, and every match file
and transcript read).

**Limitations.** Post hoc rule; incomplete particle list; closed-vocab only; other v4 limitations
(duplicate mentions, dose ownership) can add or remove errors; the September v4 result has the same
notation bias. Results of the run are recorded in 13.1.

### 13.1 S1 results and manual review (2026-11-06)

- Run: `python -m src.cross_asr.sensitivity_ko_particle --run` at commit `7f89ca0`; outputs in
  `results/cross_asr/sensitivity_ko_particle/` (20 files); `--verify-v4` reproduced the saved v4
  closed-vocab matches of all 7 conditions (300/300 each). No API call.
- Main results (S1 is a post hoc sensitivity analysis; v4 remains primary): S1 lowers Formal pooled
  CCER (`whisper1` 0.837 -> 0.670, `gpt4o_transcribe` 0.636 -> 0.466, `chirp3_ko` 0.672 -> 0.455);
  Clinical and Telegraphic change by 0.005 or less; style ranks are unchanged in all 7 conditions.
  Delta_FT (95% CI) v4 -> S1: `whisper1` -0.358 [-0.431, -0.282] -> -0.523 [-0.600, -0.441];
  `gpt4o_transcribe` -0.160 [-0.251, -0.070] -> -0.331 [-0.422, -0.244]; `chirp3_ko` -0.113
  [-0.209, -0.028] -> -0.330 [-0.425, -0.246]. Between-system difference of Delta_FT: whisper1 -
  gpt4o -0.198 -> -0.192, whisper1 - chirp3_ko -0.245 -> -0.193 (CIs exclude 0 under both); gpt4o -
  chirp3_ko Delta_FC -0.117 (CI excludes 0) -> -0.072 (CI includes 0). Delta_CT and the n = 98
  analysis lead to the same conclusions under both scorers. The 15 notation-suspect records: 13
  extracted and fully matched under S1, 2 (device transliterations) not extracted (outside S1 scope).
- Manual review (Condition A only; files and label definitions in
  `results/cross_asr/sensitivity_ko_particle_review/`): based on transcript text and scaffold, no
  audio; labels proposed by Claude and adopted by the researcher.
  - Omission -> matched stratified sample (30 records): `valid_match` 30. This is a stratified-sample
    result; it does not estimate the accuracy or false-match rate of all 992 omission -> matched changes.
  - Side-effect audit (40 records): `evaluator_artifact` 24 (duplicate IV mention 14, duplicate device
    mention 2, fluid volume read as dose 3, oxygen flow read as dose 3, mg/kg unit representation 2),
    `gold_transcript_mismatch` 10 (source ASR or TTS not determined), `needs_audio_review` 5 (same gold
    value wrong in two or more systems; audio not yet checked - not an established TTS error),
    `evaluator_correction` 1. One `gold_transcript_mismatch` (S12) has a compound cause: a correct
    transcript would also be scored as a hallucination under v4 (oxygen flow read as dose). Two
    `evaluator_artifact` records (S11, S28; mg/kg) are also compound: the transcripts lack the gold
    "/kg" as well.
- v4 limitations made visible (not corrected; also present in the primary v4 scoring for forms
  without attached particles): an IV route mention for fluids is matched like a drug route; oxygen flow
  ("L/min") is a v4 dose unit and is not excluded by the ownership rule; a gold dose "mg/kg" is
  canonicalised to unit "mgkg", which the extractor never produces, so it is always a unit error.
- Limitation: the S1 CCER values contain residual evaluator artifacts. Their size was not recomputed
  or validated; no corrected value is reported. For KOSMI 2026 only the existence of residual
  evaluator artifacts is stated. Further verification (remaining strata, other conditions, audio
  review of the 5 records) is deferred to the journal paper; no further evaluator change is made.

### 13.2 Post hoc recomputations for KOSMI 2026 (2026-11-16 to 2026-11-17)

- Purpose: poster tables. No API call; no evaluator change; v4 remains primary; S1 as defined in
  Section 13. Script: `src/cross_asr/kosmi2026_tables.py`; outputs in
  `results/cross_asr/kosmi2026_tables/`. Saved v4 closed-vocab matches were re-derived from the
  transcripts and reproduced for all samples before S1 was applied.
- Beyond the scope of Section 13: (a) Hybrid (September run) under S1; (b) nWER, Entity F1 and
  Macro-CCER (SAP5 definition) for Condition A; (c) Macro-CCER under S1.
- Hybrid: Micro-CCER 0.666 (v4) -> 0.674 (S1), Formal 0.842 -> 0.675; Macro-CCER 0.634 -> 0.645,
  Formal 0.802 -> 0.598. The Hybrid advantage over Formal under v4 is not present under S1
  (pooled values; not tested).
- Macro-CCER under v4: Formal is lowest for `whisper1` but highest for `gpt4o_transcribe`
  (F 0.671, C 0.643, T 0.559) and `chirp3_ko` (F 0.685, C 0.560, T 0.582). Under S1 Formal is lowest
  for all three (0.581, 0.455, 0.419); Clinical and Telegraphic change by 0.005 or less. The
  statement in 13.1 that style ranks are unchanged refers to Micro-CCER. Macro comparisons are
  pooled values only; no test.
- The September S1 Friedman and Wilcoxon-Holm values in 13.1 outputs were cross-checked by an
  independent recomputation and matched.
