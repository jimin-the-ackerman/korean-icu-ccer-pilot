# Korean ICU Nursing Documentation Style Transfer Pipeline

*[한국어 버전은 여기](README.ko.md)*

This project is a pilot study that generates ICU nursing documentation in
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

This project implements and validates, at pilot scale (5 clinical
scenarios × 3 Documentation Registers = 15 samples):

1. A style-controlled generation pipeline that renders the same clinical
   information (Content Scaffold) into three different Documentation
   Registers.
2. A process that converts the generated documentation into speech (TTS)
   and back into text (STT).
3. An evaluation framework that measures clinical information preservation
   in the transcribed output using Word Error Rate (WER), Entity-level
   Precision/Recall/F1, and Clinical Critical Error Rate (CCER).

The goal of this pilot is not a large-scale performance comparison, but a
demonstration that the full pipeline runs correctly end-to-end. The
validated code is parameterized so it can be scaled to 50 scenarios
(150 samples) with configuration changes only.

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
```

### 2.1 Content Scaffold Generation
Standard nursing documentation forms, SBAR examples, and clinical
abbreviation lists were reviewed to establish the JSON Schema for the
Content Scaffold (`docs/reference_analysis.md`,
`src/scaffold/scaffold_schema.py`). GPT-4o generates structured clinical
scenarios that conform to this schema
(`src/scaffold/generate_scenarios.py`).

### 2.2 Style-controlled Documentation Generation
The same Content Scaffold is rendered into three styles — Formal Template,
Clinical Charting, and Telegraphic ICU — by instructing GPT-4o. The rules
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
Clinical information is extracted from the transcripts in two tracks:

- **Closed-vocabulary entities** (Route, Frequency, Device, Dose, Vital
  Sign): extracted via dictionary/regex rules built from the standard
  abbreviation list identified in the reference analysis
  (`src/entity_extraction/closed_vocab_extractor.py`).
- **Open-vocabulary entities** (Symptom, Clinical Status, Intervention,
  Notification): extracted via Claude's structured output, since these
  expressions are too free-form for rule-based extraction
  (`src/entity_extraction/open_vocab_extractor.py`).

### 2.5 Entity Matching & Error Classification
Entities extracted from the Whisper transcript are compared against the
Gold Standard (the Content Scaffold) to determine whether each piece of
clinical information was preserved.

- Closed-vocabulary: matched via rule-based comparison of normalized
  values (`src/matching/entity_matcher.py`).
- Open-vocabulary: matched via Claude, which reviews the Gold and Whisper
  entity lists together and performs semantic matching
  (`src/matching/semantic_matcher.py`).

Match results are classified as Matched / Omission / Numeric Error /
Route Error / Frequency Error / Negation Flip / Severity Shift, etc.

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
  patient-safety philosophy of NCC MERP and was designed by the
  researcher into three tiers (high / medium / low).

---

## 3. Results (Pilot, n=15)

### 3.1 Word Error Rate (normalized)

| Documentation Register | Mean WER |
|---|---|
| Formal Template | 0.3439 |
| Clinical Charting | 0.4299 |
| Telegraphic ICU | 0.4735 |

### 3.2 Entity-level Evaluation

| Documentation Register | Precision | Recall | F1 |
|---|---|---|---|
| Formal Template | 0.5946 | 0.3385 | 0.4314 |
| Clinical Charting | 0.5893 | 0.5077 | 0.5455 |
| Telegraphic ICU | 0.6481 | 0.5385 | 0.5882 |

### 3.3 Clinical Critical Error Rate

| Documentation Register | CCER (lower is better) |
|---|---|
| Telegraphic ICU | 1.0154 |
| Clinical Charting | 1.1385 |
| Formal Template | 1.3538 |

### 3.4 Key Finding

By WER alone, Formal Template performs best and Telegraphic ICU performs
worst. By Entity-level F1 and CCER, the ranking is **reversed**:
Telegraphic ICU performs best and Formal Template performs worst.

This suggests that the fully grammatical sentences of Formal Template
improve raw transcription accuracy (WER), but because clinical
information is embedded within narrative sentences, Whisper tends to omit
entire pieces of clinical information more often. Telegraphic ICU, in
contrast, has a higher WER because its sentence structure breaks down
more easily, but its explicit, compressed listing of values means that
core clinical entities are relatively better preserved.

This result demonstrates, at pilot scale, that evaluating a medical
speech recognition system by transcription accuracy (WER) alone can lead
to clinically misleading conclusions.

---

## 4. Repository Structure

```
korean-icu-ccer-pilot/
├── configs/
│   └── config.yaml              # Experiment configuration
├── docs/
│   ├── reference_analysis.md    # Reference material analysis
│   ├── design_decisions.md      # Design changes during implementation
│   └── limitations.md           # Limitations of the pilot study
├── data/
│   ├── scenarios/                # Content Scaffold (GPT-4o generated)
│   ├── generated_text/           # Style-controlled Gold Transcripts
│   ├── audio/                    # TTS audio files
│   ├── stt_transcripts/          # Whisper transcription results
│   └── entities/                 # Entity extraction/matching results
├── src/
│   ├── scaffold/                 # Content Scaffold schema and generation
│   ├── style_controller/         # Documentation Register rules
│   ├── generation/                # GPT-4o documentation generation
│   ├── tts/                       # Speech synthesis
│   ├── stt/                       # Speech recognition
│   ├── entity_extraction/         # Closed/open-vocabulary extraction
│   ├── matching/                  # Entity matching, semantic matching
│   └── evaluation/                # WER, entity evaluation, CCER
├── results/
│   └── pilot_15/                  # Final evaluation results (CSV/JSON)
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

```bash
# 1. Generate Content Scaffolds (GPT-4o)
python3 -m src.scaffold.generate_scenarios

# 2. Generate style-controlled documentation (GPT-4o)
python3 -m src.generation.generate_notes

# 3. Speech synthesis (OpenAI TTS)
python3 -m src.tts.synthesize_speech

# 4. Speech recognition (OpenAI Whisper)
python3 -m src.stt.transcribe

# 5. WER evaluation
python3 -m src.evaluation.wer_eval

# 6. Entity extraction
python3 -m src.entity_extraction.run_closed_vocab_extraction
python3 -m src.entity_extraction.run_open_vocab_extraction

# 7. Entity matching
python3 -m src.matching.run_closed_vocab_matching
python3 -m src.matching.run_semantic_matching

# 8. Final evaluation (Entity-level P/R/F1, CCER)
python3 -m src.evaluation.entity_eval
python3 -m src.evaluation.ccer_eval
```

### 5.3 Scaling Up (5 → 50 scenarios)

Change `experiment.n_scenarios` in `configs/config.yaml` and extend the
`SCENARIOS` list in `src/scaffold/generate_scenarios.py` accordingly, then
re-run the same sequence above. The rest of the codebase is designed to be
agnostic to the number of scenarios.

---

## 6. Related Documents

- [`docs/reference_analysis.md`](docs/reference_analysis.md): analysis of
  reference material underlying the Content Scaffold Schema and Style
  Controller rules
- [`docs/design_decisions.md`](docs/design_decisions.md): design changes
  made during implementation relative to the original proposal
- [`docs/limitations.md`](docs/limitations.md): limitations of the current
  pilot study

---

## 7. Author

Jimin (jimin-the-ackerman)
Master's in AI/ML, Korea University