# Limitations

*[한국어 버전은 여기](limitations.ko.md)*

This document records the methodological limitations of the current pilot
study (5 scenarios × 3 styles = 15 samples). These are the result of
deliberate design decisions made under pilot-scale and resource
constraints, and are noted here to identify points requiring further
work in follow-up research.

---

## 1. Pilot Scale

The study was conducted with 5 clinical scenarios and 15 samples. This
scale is sufficient to validate the end-to-end operation of the pipeline,
but too small to support statistically significant conclusions. The
figures reported here (WER, F1, CCER) should be interpreted as indicative
trends rather than definitive results.

## 2. TTS/STT Tool Substitution

The proposal specified Google Cloud TTS and a local Whisper model; the
pilot substituted OpenAI TTS and the OpenAI Whisper API (see
`docs/design_decisions.md` for details). The substitution itself is
judged to have limited impact on the research conclusions, but the
possibility of performance differences between TTS/STT engines cannot be
ruled out.

## 3. Language Setting Comparison Not Conducted

The proposal called for comparing Whisper's Auto Detect and fixed-Korean
settings beforehand; the pilot proceeded directly with fixed Korean
(`language="ko"`). No quantitative evidence was obtained regarding the
difference between the two settings.

## 4. Hallucination Risk in Claude-based Entity Extraction

During open-vocabulary entity extraction, Claude was observed to
"clinically embellish" garbled text resulting from speech recognition
errors, generating entities not actually present in the source text
(e.g., inferring a "hypoxia" symptom purely from a low vital-sign value).
This was mitigated through explicit verbatim-extraction instructions and
counter-examples in the prompt, but this is a mitigation rather than a
fundamental fix, and it cannot be guaranteed that a similar pattern does
not occur in samples where it was not observed.

## 5. Semantic Matching Misjudging Phonetic Similarity as Semantic Equivalence

> **Status: Mitigated in v2** (see `docs/design_decisions.md` §4). Retained
> below in its original form as a record of the issue as first observed
> in the pilot.

The semantic match stage of open-vocabulary entity matching is designed
so that Claude judges clinical-meaning equivalence between Gold and
Whisper entities. However, during verification, cases were observed where
Claude judged a string that Whisper had phonetically transliterated due
to an STT error (e.g., "chest pain" transcribed as "체스파인") as
meaning-preserved. Such a transliteration carries no clinical meaning,
yet was classified as a semantic match, risking an overestimate of
information preservation in cases of substantial information loss. This
pilot documents this issue as a methodological limitation, without
introducing a new error type or modifying the evaluation logic.

v2 introduces a dedicated `phonetic_artifact` match category (distinct
from `semantic`) with explicit prompt instructions and counter-examples,
and treats it as equivalent to `omission` during evaluation. This is a
prompt-level mitigation, not a structural fix (no phonetic-similarity
detector was added independent of Claude's own judgment), so residual
misclassification at the boundary (e.g., partially-recognizable
loanwords) may still occur. Re-running the original 15-sample pilot
under v2 (Week 2 of the current plan) is intended to quantify how many
cases this reclassifies.

## 6. CCER Does Not Penalize Whisper-only (Hallucinated) Insertions

> **Status: Resolved in v2** (see `docs/design_decisions.md` §5). Retained
> below in its original form as a record of the issue as first observed
> in the pilot.

Entities that exist only in the Whisper Transcript with no corresponding
Gold entity (`whisper_only`) are currently assigned a weight of 0 in the
CCER calculation and excluded from aggregation. That is, the current
formula does not penalize cases where Whisper inserts information that
does not actually exist (hallucination).

v2 assigns these entities `error_type="hallucination"` with weight 3 (the
same tier as `numeric_error` / `negation_flip` / `severity_shift`) in the
CCER formula. See `src/evaluation/ccer_eval.py` for the full rationale
behind the weight choice.

## 7. Simplicity of the Substitution Heuristic

In closed-vocabulary entity matching, when one omission and one
whisper-only item of the same entity type exist simultaneously, they are
reinterpreted as a single substitution error. This heuristic is valid at
pilot scale (few entities per sentence), but may misjudge cases when
scaled to 50+ scenarios where multiple entities of the same type occur
within a single sentence; a more sophisticated alignment algorithm may be
required.

## 8. No Clinical Expert Validation

Neither the reference analysis (based on publicly available material) nor
the CCER weighting scheme (conceptually referencing NCC MERP, designed
directly by the researcher) was validated by a practicing nurse or
clinical expert. Whether the generated Content Scaffolds and Documentation
Register expressions precisely match the conventions of actual Korean ICU
clinical practice has not been verified.

## 9. No Real Hospital Data Used

Due to privacy protection and data accessibility constraints, this study
did not use real hospital EMR data; the entire pipeline was conducted on
synthetic data (generated by GPT-4o). We do not claim that results based
on synthetic data generalize directly to real clinical environments.

---

## Future Work

- [Done in v2, prompt-level only] Introduce entity normalization based on
  standard medical terminology ontologies (SNOMED CT, UMLS) or Korean
  medical named-entity recognition (NER) models remains open as a more
  structural alternative to the `phonetic_artifact` prompt fix (addresses
  Limitation 5)
- [Done in v2] Incorporate a penalty for Whisper-only (hallucinated)
  insertions into the CCER formula (addresses Limitation 6)
- Improve the entity matching alignment algorithm for scale-ups beyond
  50 scenarios (addresses Limitation 7)
- Validate Content Scaffolds and CCER weights with clinical experts
  (nurses) (addresses Limitation 8)
- Compare results based on synthetic data against real hospital data, once
  available (addresses Limitation 9)
- Conduct a comparison experiment between Whisper's Auto Detect and fixed
  Korean settings (addresses Limitation 3)