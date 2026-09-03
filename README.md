# Korean ICU Nursing Documentation Style Transfer Pipeline

*[한국어 버전은 여기](README.ko.md)*

This project is a study that generates ICU nursing documentation in
multiple Documentation Registers, passes it through speech synthesis (TTS)
and speech recognition (STT), and evaluates clinical information
preservation in the resulting transcripts.

> This is an independent research project developed to support a
> postdoctoral/research position application. It does not use real hospital
> EMR data; the Content Scaffold was designed based on publicly available
> reference material. The pipeline covers ICU nursing note generation,
> speech synthesis, speech recognition, entity-level evaluation, and a
> custom Clinical Critical Error Rate (CCER), implemented end-to-end using
> generative AI.

---

## 1. Research Overview

Korean ICU nursing documentation follows a distinct Documentation Register
that differs from ordinary Korean prose. The same clinical information can
be expressed as a fully grammatical narrative (Formal Template), a
compressed Korean-English mixed charting style (Clinical Charting), or an
extremely compressed real-time style (Telegraphic ICU). This difference in
expression can have different effects on speech recognition performance
and on how much clinical information is preserved.

This project implements and validates, at full scale (100 clinical
scenarios × 3 Documentation Registers = 300 samples):

1. A style-controlled generation pipeline that renders the same clinical
   information (Content Scaffold) into three different Documentation
   Registers.
2. A process that converts the generated documentation into speech (TTS)
   and back into text (STT).
3. An evaluation framework that measures clinical information preservation
   in the transcribed output using Word Error Rate (WER), Entity-level
   Precision/Recall/F1, and Clinical Critical Error Rate (CCER).
4. A pre-registered statistical analysis plan (Friedman/Wilcoxon/mixed-
   effects, WER-CCER association, within-scenario disagreement, and CCER
   weighting-scheme sensitivity).

The evaluation methodology went through four documented revisions
(`docs/design_decisions.md`, `docs/taxonomy_audit.md`,
`docs/v4_style_invariant_extraction_spec.md`) as structural evaluator
biases were discovered and independently audited/corrected -- most notably,
a **style-dependent extraction bias** in which the closed-vocabulary
extractor only recognized English abbreviations, systematically
under-scoring Formal Template (which frequently renders clinical labels
as full Korean words) regardless of actual transcription accuracy. All
results reported below are from the final, bias-corrected pipeline (v4).

---

## 2. Pipeline

```
Reference Analysis
-> Content Scaffold Schema
-> GPT-4o: Structured Clinical Scenario Generation
-> Style Controller
-> GPT-4o: Style-controlled Documentation Generation
-> OpenAI TTS: Speech Synthesis
-> OpenAI Whisper: Speech Recognition
-> Entity Extraction (Closed-vocabulary / Open-vocabulary)
-> Entity Matching & Error Type Classification
-> Evaluation (WER / Entity-level P,R,F1 / CCER)
-> Statistical Analysis (Friedman/Wilcoxon/Mixed-effects, WER-CCER
   association, within-scenario disagreement, weight sensitivity)
```

### 2.1 Content Scaffold Generation
Standard nursing documentation forms, SBAR examples, and clinical
abbreviation lists were reviewed to establish the JSON Schema for the
Content Scaffold (`docs/reference_analysis.md`,
`src/scaffold/scaffold_schema.py`). GPT-4o generates structured clinical
scenarios that conform to this schema
(`src/scaffold/generate_scenarios.py`). The Content Scaffold, not the
rendered text, is used as the Gold Standard for evaluation, so that
comparisons across Documentation Registers are not confounded by
extraction differences (`src/entity_extraction/scaffold_as_gold.py`; see
`docs/design_decisions.md` Sec 3).

### 2.2 Style-controlled Documentation Generation
The same Content Scaffold is rendered into three styles -- Formal Template,
Clinical Charting, and Telegraphic ICU -- by instructing GPT-4o. The rules
for each style (sentence compression, Korean-English code-switching,
charting-style verb endings, etc.) are grounded in the reference analysis
(`src/style_controller/style_controller.py`,
`src/generation/generate_notes.py`).

### 2.3 Speech Synthesis & Recognition
The generated nursing documentation text is synthesized into speech using
OpenAI TTS (`src/tts/synthesize_speech.py`) and transcribed back into text
using the OpenAI Whisper API (`src/stt/transcribe.py`). A single voice is
fixed across all samples to keep speaker identity as a controlled
variable.

### 2.4 Entity Extraction
Clinical information is extracted from the transcripts in two tracks,
covering 11 entity types confirmed independently of observed error
patterns (`docs/taxonomy_audit.md` Sec 5):

- **Closed-vocabulary entities** (Route, Frequency, Device, Dose, Vital
  Sign): extracted via dictionary/regex rules built from the standard
  abbreviation list identified in the reference analysis
  (`src/entity_extraction/closed_vocab_extractor.py`). As of v4, this
  extractor is **style-invariant**: each entity is recognized via a
  canonical `surface form -> concept/value -> comparison` pipeline
  covering English abbreviations, English full forms, Korean full forms,
  and a small set of conventional phonetic transliterations, rather than
  English abbreviations only. `medication_dose` extraction additionally
  applies an entity-ownership hierarchy (candidate detection ->
  exclusion by more specific ownership such as vital-sign or
  intake/output values -> medication-administration-context confirmation)
  to avoid mis-attributing unrelated numbers as drug doses. See
  `docs/v4_style_invariant_extraction_spec.md` for the full specification
  and audit trail.
- **Open-vocabulary entities** (Symptom, Clinical Status, Medication
  Identity, Intervention, Intake/Output, Notification): extracted via
  Claude's structured output, since these expressions are too free-form
  for rule-based extraction (`src/entity_extraction/open_vocab_extractor.py`).

### 2.5 Entity Matching & Error Classification
Entities extracted from the Whisper transcript are compared against the
Gold Standard (the Content Scaffold) to determine whether each piece of
clinical information was preserved.

- Closed-vocabulary: matched via rule-based comparison of normalized
  values (`src/matching/entity_matcher.py`).
- Open-vocabulary: matched via Claude, which reviews the Gold and Whisper
  entity lists together and performs semantic matching, including a
  stricter look-alike/sound-alike safeguard for medication identity
  grounded in the ISMP Confused Drug Names list
  (`src/matching/semantic_matcher.py`).

Match results are classified as Matched / Omission / Numeric Error /
Route Error / Frequency Error / Medication Identity Error / Negation Flip
/ Severity Shift / Hallucination, etc.

### 2.6 Evaluation
Three metrics are used to evaluate the pipeline output:

- **WER** (`src/evaluation/wer_eval.py`): transcription accuracy between
  the Gold Transcript and the Whisper Transcript. Both raw and
  normalized (case/punctuation-insensitive) values are reported.
- **Entity-level Precision/Recall/F1** (`src/evaluation/entity_eval.py`):
  clinical information preservation rate of the Whisper output relative
  to the Content Scaffold.
- **Clinical Critical Error Rate (CCER)** (`src/evaluation/ccer_eval.py`):
  a normalized score that weights each error type by its potential
  clinical risk. The weighting scheme conceptually references the
  patient-safety philosophy of NCC MERP (and, for medication identity
  specifically, the ISMP Confused Drug Names list) and was designed by
  the researcher into three tiers (high / medium / low); this weighting
  choice was stress-tested against 5 pre-registered alternative schemes
  (Sec 3.5 below).

### 2.7 Statistical Analysis
A pre-registered analysis plan (`docs/statistical_analysis_plan.md`,
frozen before running) covers: Friedman test with Kendall's W, Holm-
corrected Wilcoxon pairwise comparisons, a mixed-effects model
(`src/analysis/statistical_tests.py`); scenario-level cluster-bootstrap
WER-CCER Spearman correlation (`src/analysis/sap1_wer_ccer_spearman.py`);
within-scenario ranking disagreement (`src/analysis/sap2_within_scenario_disagreement.py`);
CCER weighting-scheme sensitivity across 5 pre-specified schemes
(`src/analysis/sap3_weight_sensitivity.py`); and entity-type error rates
(`src/analysis/sap4_error_profile_final.py`).

---

## 3. Results (Final, v4, n=100 scenarios / 300 samples)

Full results: [`results/full_100_v4/`](results/full_100_v4/).

### 3.1 Word Error Rate (normalized)

| Documentation Register | Mean WER |
|---|---|
| Formal Template | 0.3038 |
| Clinical Charting | 0.4517 |
| Telegraphic ICU | 0.5640 |

### 3.2 Entity-level Evaluation

| Documentation Register | Precision | Recall | F1 |
|---|---|---|---|
| Formal Template | 0.8432 | 0.6728 | 0.7484 |
| Clinical Charting | 0.7665 | 0.5406 | 0.6341 |
| Telegraphic ICU | 0.7995 | 0.4933 | 0.6101 |

### 3.3 Clinical Critical Error Rate

| Documentation Register | CCER (lower is better) |
|---|---|
| Formal Template | 0.8417 |
| Clinical Charting | 1.1682 |
| Telegraphic ICU | 1.2134 |

### 3.4 Statistical Significance

Friedman test: chi-squared = 78.12, Kendall's W = 0.391, p = 1.09 x 10^-17.
Holm-corrected Wilcoxon signed-rank: Formal Template differs significantly
from both other styles (p_holm ~= 1.3 x 10^-11 and 3.3 x 10^-12, respectively);
Clinical Charting and Telegraphic ICU are not significantly different from
each other (p_holm = 0.217). A mixed-effects model (`CCER ~ style +
(1|scenario)`) confirms both style coefficients are significant at
p < 0.0001. The finding that Formal Template is CCER-best held across all
5 pre-registered CCER weighting schemes (`docs/statistical_analysis_plan.md`
Sec 3).

### 3.5 Key Finding

By every metric -- WER, Entity-level F1, **and** CCER -- Formal Template now
performs **best**, and Telegraphic ICU performs worst. This is a striking
reversal from an earlier, methodologically confounded version of this
pipeline (v3), which had found the opposite: Formal Template ranked best
by WER but *worst* by CCER, suggesting that fully grammatical narrative
sentences improved raw transcription accuracy while causing Whisper to
lose more clinical information.

That earlier "reversal" finding did **not** survive a full evaluator
audit. Two independent structural biases inflated Formal Template's error
counts without reflecting any real loss of clinical information:

1. **Style-dependent extraction bias**: the closed-vocabulary extractor
   only recognized English abbreviations (`BP`, `HR`, `IV`, `q4h`, ...).
   Formal Template frequently renders the same clinical facts as full
   Korean words (`혈압`, `심박수`, `정맥으로`, `매 4시간마다`), which the
   original extractor could not recognize at all -- regardless of whether
   Whisper transcribed them correctly. This alone drove Formal Template's
   vital-sign recognition rate from 0% to 100% once fixed.
2. **Gold/Whisper value-format asymmetry**: even after fixing (1), the
   Content Scaffold's Gold values retained their original units (e.g.
   `"120 bpm"`) while the Whisper-side extractor only ever captured the
   bare number (`"120"`). This caused a false "numeric error" even when
   Whisper transcribed the number perfectly -- a bug present since the
   pipeline's earliest version, invisible until (1) was fixed and Formal
   Template's labels started matching for the first time.

Both were audited and corrected with real-data verification (recovery
rate, no-regression checks, and false-positive scans) rather than
patched to fit the desired outcome; see `docs/v4_style_invariant_extraction_spec.md`
for the full specification, grounding, and audit trail. The correct,
bias-free conclusion is that WER, Entity-level F1, and CCER are broadly
consistent for this pilot: more grammatical, fully-spelled-out
documentation is both easier for Whisper to transcribe accurately *and*
better at preserving clinical information -- the opposite of what a
naive, English-only evaluator would have concluded.

This project's methodological contribution is therefore less about the
specific ranking of the three styles, and more about demonstrating that
building a clinically-informed evaluation metric (CCER) does not by
itself guarantee freedom from evaluator bias -- the entity extraction
layer underneath it must be audited with the same rigor as the metric
itself.

---

## 4. Repository Structure

```
korean-icu-ccer-pilot/
├── configs/
│   └── config.yaml              # Experiment configuration (n_scenarios, results_dir, etc.)
├── docs/
│   ├── reference_analysis.md    # Reference material analysis
│   ├── design_decisions.md      # Design changes during implementation
│   ├── limitations.md           # Limitations of the study
│   ├── taxonomy_audit.md        # v3: independent CCER taxonomy audit & freeze
│   ├── v4_style_invariant_extraction_spec.md  # v4: style-bias audit, spec, freeze
│   ├── statistical_analysis_plan.md           # Pre-registered SAP (frozen)
│   └── full_run_execution_order.md            # Locked execution order for scale-ups
├── data/
│   ├── scenarios/                # Content Scaffold (GPT-4o generated)
│   ├── generated_text/           # Style-controlled Gold Transcripts
│   ├── audio/                    # TTS audio files (not tracked in git)
│   ├── stt_transcripts/          # Whisper transcription results
│   └── entities/                 # Entity extraction/matching results
├── src/
│   ├── pipeline_utils.py          # Skip-by-default safety mechanism (RunLog, --overwrite)
│   ├── scaffold/                  # Content Scaffold schema and generation
│   ├── style_controller/          # Documentation Register rules
│   ├── generation/                # GPT-4o documentation generation
│   ├── tts/                       # Speech synthesis
│   ├── stt/                       # Speech recognition
│   ├── entity_extraction/         # Closed/open-vocabulary extraction
│   ├── matching/                  # Entity matching, semantic matching
│   ├── evaluation/                # WER, entity evaluation, CCER
│   └── analysis/                  # Error profile, power analysis, statistical tests, SAP 1-4
├── results/
│   ├── pilot_15/                  # v1/v2/v3 checkpoints (15-sample pilot, preserved)
│   ├── full_50/                   # 50-scenario checkpoint (preserved)
│   ├── full_100/                  # v3 (pre-v4-fix) 100-scenario checkpoint (preserved)
│   └── full_100_v4/               # FINAL results (100 scenarios, bias-corrected)
└── tests/                          # Unit tests
```

---

## 5. Reproduction

### 5.1 Environment Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY, ANTHROPIC_API_KEY
```

### 5.2 Full Pipeline Execution Order

All generation/extraction/matching scripts are idempotent by default:
re-running any step skips samples whose output already exists, and only
processes what's missing (`src/pipeline_utils.py`). Pass `--overwrite` to
force regeneration of a step. This makes scale-ups (e.g. 5 -> 50 -> 100
scenarios) safe to run without risking already-computed results -- see
`docs/full_run_execution_order.md` for the full checklist used for this
project's own scale-ups.

```bash
# 1. Generate Content Scaffolds (GPT-4o)
python3 -m src.scaffold.generate_scenarios

# 2. Generate style-controlled documentation (GPT-4o)
python3 -m src.generation.generate_notes

# 3. Speech synthesis (OpenAI TTS)
python3 -m src.tts.synthesize_speech

# 4. Speech recognition (OpenAI Whisper)
python3 -m src.stt.transcribe

# 5. Entity extraction (no API calls: closed-vocab is regex-based;
#    open-vocab calls Claude)
python3 -m src.entity_extraction.run_closed_vocab_extraction
python3 -m src.entity_extraction.run_open_vocab_extraction

# 6. Entity matching (closed-vocab: rule-based, no API; open-vocab: Claude)
python3 -m src.matching.run_closed_vocab_matching
python3 -m src.matching.run_semantic_matching

# 7. Evaluation (WER, Entity-level P/R/F1, CCER, Error Profile) - no API calls
python3 -m src.evaluation.wer_eval
python3 -m src.evaluation.entity_eval
python3 -m src.evaluation.ccer_eval
python3 -m src.analysis.error_profile --output-dir results/full_100_v4

# 8. Statistical analysis (per docs/statistical_analysis_plan.md) - no API calls
python3 -m src.analysis.statistical_tests --results-dir results/full_100_v4
python3 -m src.analysis.sap1_wer_ccer_spearman --results-dir results/full_100_v4
python3 -m src.analysis.sap2_within_scenario_disagreement --results-dir results/full_100_v4
python3 -m src.analysis.sap3_weight_sensitivity --output-dir results/full_100_v4
python3 -m src.analysis.sap4_error_profile_final --output-dir results/full_100_v4
```

### 5.3 Scaling Up

Change `experiment.n_scenarios` in `configs/config.yaml` (and, if you want
results kept in a separate directory, `paths.results_dir`), then re-run
the same sequence above. Because every step defaults to skip-existing,
already-computed scenarios (e.g. the first 100) are left untouched and
only the newly-added ones are processed -- no separate code changes are
needed. See `docs/full_run_execution_order.md` for the exact checklist
(pre-flight checks, integrity verification, and non-goals) used when
this project scaled from 5 -> 50 -> 100 scenarios.

### 5.4 Tests

```bash
pytest tests/ -q
```

---

## 6. Related Documents

- [`docs/reference_analysis.md`](docs/reference_analysis.md): analysis of
  reference material underlying the Content Scaffold Schema and Style
  Controller rules
- [`docs/design_decisions.md`](docs/design_decisions.md): design changes
  made during implementation relative to the original proposal
- [`docs/limitations.md`](docs/limitations.md): limitations of the study,
  including residual (non-style-bias) parsing gaps left unresolved by
  design
- [`docs/taxonomy_audit.md`](docs/taxonomy_audit.md): v3 -- independent,
  results-blind audit and freeze of the 11-category CCER entity taxonomy
- [`docs/v4_style_invariant_extraction_spec.md`](docs/v4_style_invariant_extraction_spec.md):
  v4 -- audit, specification, and freeze of the style-invariant
  closed-vocabulary extraction fix described in Sec 3.5 above
- [`docs/statistical_analysis_plan.md`](docs/statistical_analysis_plan.md):
  pre-registered statistical analysis plan (frozen before execution)
- [`docs/full_run_execution_order.md`](docs/full_run_execution_order.md):
  locked execution checklist used for scaling the pilot from 5 to 100
  scenarios without risking already-computed results

---

## 7. Author

Jimin (jimin-the-ackerman)
