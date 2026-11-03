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
| `clova_enko` | new | CLOVA Speech `/recognizer/upload`, language `enko`, completion `sync`, other params API default; no boostings/forbiddens/domain boosting |

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

## 10. Change log

| Date | Change | Reason |
|---|---|---|
| 2026-11-03 | Protocol frozen (Version 1.0) | — |
