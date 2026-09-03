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

## 10. Closed-vocab Regex Cross-Category Contamination (Dose vs. Vital Sign / Intake-Output)

**[Resolved in v4]** This limitation was fixed as part of the v4
style-invariant extraction work; see
`docs/v4_style_invariant_extraction_spec.md` Sec 3.5 for the full
entity-ownership-hierarchy fix and `docs/design_decisions.md` Sec 7 for the
design rationale. The description below is preserved as a historical
record of the original problem.

Discovered during the v3 pipeline sanity audit (`docs/taxonomy_audit.md`),
pre-existing since before v2/v3 (confirmed identical counts in v1/v2 data —
not introduced by the v3 taxonomy changes). The `dose` regex pattern in
`closed_vocab_extractor.py` matches any "number + unit" combination (e.g.
`\d+\s*(mg|mL|cc|g|mcg|L/min)`) without checking surrounding context. This
causes two kinds of false positives observed in the pilot: (1) a
blood-pressure reading garbled by STT into a number-plus-"mg" pattern (e.g.
"90/60 mmHg" transcribed as "90-60mg") gets misclassified as a medication
dose; (2) an intake/output volume (e.g. "urine output 200 mL") is likewise
misclassified as a dose. Both inflate `dose`-category hallucination counts
with values that have no relationship to medication administration.

## 11. Duplicate Literal Mentions of the Same Device Within One Note

Also discovered during the v3 sanity audit, also pre-existing (identical
count in v1/v2). The LLM-generated note text occasionally states the same
real-world device fact twice in different phrasings within a single note
(e.g. "SpO2 95% on 2L NC." followed later by "NC 사용 중."). Because Gold's
closed-vocab device list is derived from the Content Scaffold (one physical
fact = one entity, regardless of how many times the generated text restates
it), while the regex-based extractor counts every literal textual
occurrence independently, a note that mentions the same device twice
produces two Whisper-side device entities against only one Gold-side
entity, and the extra occurrence is scored as a hallucination even though
no real information was fabricated. A fix would need to deduplicate
identical closed-vocab values within a single text before matching, or
constrain note generation to state each device fact once. Left as Future
Work; affects a small minority of samples (1 of 15 in the pilot).

## 12. Symptom Category Boundary Leakage (patient_context and clinical_status)

Also discovered during the v3 sanity audit. Two related sub-issues, both
pre-existing (v2 had a higher raw count of the same phenomenon — 6 vs. 3
after the v3 prompt tightening — suggesting the v3 SYSTEM_PROMPT changes
partially, but not fully, mitigated this):
- The Content Scaffold's `patient_context` field (explicitly out of CCER
  scope per `docs/taxonomy_audit.md` §5.5) is sometimes rendered by the
  note-generation step into a sentence that reads like a documented symptom
  (e.g. patient_context "...presenting with respiratory distress..."
  becomes a note sentence "...respiratory distress 호소함..."). Since this
  content is never captured in the Gold symptom entity (Gold's only
  symptom entity comes from the Scaffold's separate, singular `symptom`
  field), any correct transcription of it by Whisper is misclassified as a
  hallucinated symptom.
- Whisper-side extraction of `clinical_status`-type descriptions (e.g. "약간의
  기면 상태를 보이고 있다" / "mild lethargy") is sometimes independently
  re-reported as a `symptom` ("lethargy") in addition to (or instead of)
  `clinical_status`, echoing the same category-duplication pattern already
  fixed for device/oxygen_support vs. intervention (`docs/taxonomy_audit.md`
  §3.3), but for a pair of categories not covered by that fix.

Both are left as Future Work for a subsequent taxonomy revision (potential
"v4"), rather than expanding the v3 taxonomy scope reactively, per the
project's stated principle of not re-tuning the taxonomy in response to
observed results (`docs/taxonomy_audit.md` §6.4).

**Variant observed during the 50-scenario full-run final sanity audit**: the
same `patient_context` leakage mechanism was also observed producing a
hallucinated `intervention` rather than a hallucinated `symptom`
(`scenario_029`: patient_context "...requiring close respiratory
monitoring..." rendered into the note as "호흡 상태 밀착 모니터링 필요.",
which Whisper correctly transcribes but which has no Gold `intervention`
entity to match against). This confirms Limitation 12 is not
symptom-specific — `patient_context` leakage can surface as a false
hallucination in whichever entity type the leaked phrase happens to
resemble.

## 13. Residual Semantic Boundary Leakage into the `intervention` Category

Discovered during the final pipeline sanity audit of the 50-scenario full
run (`data/entities/`, `results/full_50/`). Of 14 `intervention`-category
hallucinations observed in the 50-scenario results, 13 trace to the same
underlying pattern: the `intervention` open-vocab category's Whisper-side
extraction (`open_vocab_extractor.py`) absorbs action-like or
activity-like phrasing from adjacent categories that were not explicitly
excluded when `intervention`'s scope was narrowed in v3
(`docs/taxonomy_audit.md` §5.2, #8; §8.2 excluded medication, device/
oxygen_support, and intake/output *values* — see the two sub-gaps below).
None of these 13 cases involve Whisper inventing information that is not
present in the Gold text; all trace to real Gold content being
double-counted through a category-boundary gap.

**Sub-case A — `notification` (specialist consult requests) vs.
`intervention`** (5 of 14 cases): text describing a request for a
specialist consult (e.g. Gold notification "Consult gastroenterology for
ongoing management of pancreatitis." / "orthopedic consultation
requested") is independently re-extracted as an `intervention` (e.g.
"Gastroenterology Consult 요청함", "ORTHOPEDIC CONSULT"). The v3
`intervention` exclusion list explicitly covers medication, device/
oxygen-support, and intake/output, but does **not** mention `notification`
— this category pair was simply not covered by the fix.

**Sub-case B — `intake_output` *monitoring activity* phrasing vs.
`intervention`** (6 of 14 cases): the v3 exclusion rule and worked example
for intake/output covers stated *values* (e.g. "urine output 200 mL"),
but text describing the *act of monitoring* intake/output (e.g. Gold io
"strict monitoring of intake and output", "strict fluid balance
monitoring") is still independently re-extracted as an `intervention`
(e.g. "스트릭트 모니터링 of intake and output", "strict fluid balance
monitoring"). The exclusion rule's phrasing was value-oriented and did not
anticipate activity-oriented phrasing of the same underlying fact.

**Sub-case C — Scaffold `io` field populated with intervention-like
wording** (2 of 14 cases): in a small number of scenarios (e.g.
`scenario_027`), the Content Scaffold's `io` field itself was populated
during scaffold generation with a phrase that reads like an intervention
rather than an intake/output observation ("IV fluids initiated") rather
than a fluid-balance measurement. Whisper's `intervention` extraction of
this phrase is not unreasonable given the wording — the ambiguity
originates further upstream, in scaffold-generation phrasing, rather than
in the Gold/Whisper taxonomy alignment itself.

Per the project's principle of not re-tuning the taxonomy in response to
observed results (`docs/taxonomy_audit.md` §6.4), this is logged as a
residual limitation rather than folded into v3. A future fix (candidate
"v4") would extend the `intervention` exclusion list to explicitly cover
notification/consult phrasing and intake-output *monitoring activity*
phrasing (not just stated values), and would add a scaffold-generation
constraint or post-hoc validation step to keep `io` field content
semantically restricted to observations rather than actions.

## 14. Residual Gaps Left Deliberately Unresolved by v4 (Style-Invariant Extraction)

Discovered and documented during the v4 style-invariant extraction audit
(`docs/v4_style_invariant_extraction_spec.md`) and its real-data
verification. These are intentional scope boundaries, not oversights —
each was evaluated against real 100-scenario data and found to be either
genuinely unrecoverable via a generalizable grammar, or a residual
STT-noise effect unrelated to the style bias v4 was designed to fix.

- **Bare "정맥" (route) form**: only the suffixed forms (정맥으로/정맥주사/
  정맥 내/정맥 수액) are recognized as the `iv` route, per the empirical
  finding that 29% of bare "정맥" occurrences in the corpus referred to a
  different concept (device or symptom). No bare-form occurrence was
  observed in the 100-scenario corpus, so this is currently untested
  rather than confirmed missed; revisit if future data shows genuine
  bare-form route usage.
- **SpO2 label-value grammar residual cases**: 6 of the original 55
  SpO2 insertion-gap omissions remain unmatched after the v4 grammar fix,
  all confirmed to be severe STT corruption of the value itself (e.g.
  "SpO2 간지 5%", "산소포화도는 상실기 공기에서 95%로") rather than a
  recoverable structural pattern. One additional case
  ("...이 O2를 비강케귤라로 공급받으면서...") has an extra token between
  the particle and the oxygen-context qualifier that the closed grammar
  does not cover; left unmatched rather than special-cased for a single
  observed instance.
- **Formal Template's residual device/dose/route error rate**: even after
  the v4 fix, Formal Template's error rate for `device` (77%), `dose`
  (86%), and `route` (73%) remains substantially higher than its now-best
  `vital_sign` rate (4.6%). This is attributed to ordinary STT
  transcription noise affecting Korean multi-syllable clinical phrases
  (as opposed to short English abbreviations), not to a residual
  extraction bias — Architecture A (`docs/v4_style_invariant_extraction_spec.md`
  Sec 6.2) was explicitly scoped to remove label-recognition bias, not to
  guarantee uniform STT robustness across styles. Confirming this
  attribution with certainty (as opposed to a remaining, undetected
  extraction gap) is left as Future Work.

## Future Work

- Deduplicate identical closed-vocab values within a single text before
  matching, so a device mentioned twice in one note is not double-counted
  (addresses Limitation 11)
- Extend category-boundary exclusion rules (already applied to
  device/oxygen_support vs. intervention) to symptom vs. clinical_status,
  and reconsider whether patient_context-derived phrasing needs a narrow
  carve-out even under the current scope exclusion (addresses Limitation 12)
- Extend the `intervention` exclusion list to explicitly cover notification/
  consult-request phrasing and intake-output *monitoring activity* phrasing
  (not just stated values); add a scaffold-generation constraint or
  validation step to keep the `io` field semantically restricted to
  observations rather than action-like wording (addresses Limitation 13)

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