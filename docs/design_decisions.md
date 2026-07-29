# Design Decisions

*[한국어 버전은 여기](design_decisions.ko.md)*

This document records the design decisions that changed during pilot
implementation, relative to the original project proposal. Each entry
records the original design, the issue observed during implementation,
the decision made, the reasoning, and the impact on the evaluation
pipeline.

---

## 1. Text-to-Speech Provider

| Field | Content |
|---|---|
| **Original Design** | Google Cloud Text-to-Speech (Proposal §3.8, §4.6) |
| **Issue observed during implementation** | The existing GCP account was not eligible for new-account free credits, requiring separate billing setup |
| **Design Decision** | Replaced with OpenAI TTS (`tts-1`). The single-speaker (voice) principle was retained |
| **Reason** | Unifying API dependencies with the OpenAI API already used for GPT-4o generation, simplifying authentication and configuration management |
| **Impact on the evaluation pipeline** | None. The choice of TTS engine is not the core independent variable of this research (Documentation Register), so it does not affect the interpretation of the evaluation results |

---

## 2. Speech-to-Text Engine and Language Setting

| Field | Content |
|---|---|
| **Original Design** | Local Whisper model, with Auto Detect and fixed Korean (`language="ko"`) settings compared beforehand to select the more stable configuration (Proposal §3.9, §4.7) |
| **Issue observed during implementation** | Judged that API-based verification without local GPU/model download would be more efficient at pilot scale |
| **Design Decision** | Replaced with the OpenAI Whisper API (`whisper-1`). Proceeded directly with `language="ko"` fixed, and omitted the Auto Detect comparison |
| **Reason** | Unifying API dependencies. The comparison experiment was judged not essential to the pilot's core goal (validating the end-to-end pipeline) |
| **Impact on the evaluation pipeline** | No quantitative evidence was obtained on how Auto Detect would differ from fixed Korean in a code-switching environment (deferred to Future Work) |

---

## 3. Gold Standard for Entity Matching

| Field | Content |
|---|---|
| **Original Design** | Extract entities from both the Gold Transcript (generated nursing documentation text) and the Whisper Transcript, then compare them (Proposal §3.11) |
| **Issue observed during implementation** | Discovered that the number of entities extracted from the Gold Transcript varied systematically depending on the Documentation Register (sentence structure). For the same scenario, Formal Template Style yielded an average of 7-10 entities while Clinical Charting/Telegraphic ICU Style yielded 12-17, roughly a 2x difference. The root cause was that the regex-based extractor could not capture fully grammatical narrative expressions (e.g., "산소포화도는 88%로 확인되었으며" was not recognized by `VITAL_SIGN_PATTERN`) |
| **Design Decision** | Replaced the Gold Standard with the **Content Scaffold** (the structured JSON fixed at generation time) instead of the Gold Transcript. Added an adapter (`src/entity_extraction/scaffold_as_gold.py`) that converts the Content Scaffold into the same format as the existing entity extraction output, and updated the closed/open-vocabulary matching scripts to use it |
| **Reason** | The Content Scaffold is fixed prior to style rendering and is therefore independent of the Documentation Register, so it can serve as an identical Gold entity set across all three styles |
| **Impact on the evaluation pipeline** | After the redesign, the Gold entity count was confirmed to be identical across styles within the same scenario (e.g., all three styles of Scenario 001 yielded 13 entities). As the Recall denominator came to accurately reflect the true amount of clinical information, overall Entity-level F1 decreased (e.g., Clinical Charting Style: 0.657 → 0.546). This is interpreted as an improvement in evaluation rigor; the earlier, higher figures are considered to have been inflated by a methodological flaw. This change does not affect the WER calculation, which continues to compare the Gold Transcript against the Whisper Transcript directly |

---

## 4. Semantic Matcher: Phonetic-Transliteration Artifacts

| Field | Content |
|---|---|
| **Original Design** | The open-vocabulary semantic matcher (`src/matching/semantic_matcher.py`) classified every Gold/Whisper entity pair into `exact / normalized / semantic / omission` (plus `whisper_only` / `both_null` for single-value fields) |
| **Issue observed during implementation** | Documented as Limitation 5. Claude, when asked to find the "closest" match for a remaining Gold entity, sometimes classified a Whisper string that was merely a phonetic transliteration of the Gold term's English/loanword pronunciation (e.g. Gold "chest pain" vs. Whisper "체스파인") as a `semantic` match, even though the Whisper string carries no independent clinical meaning and would not be understood by a reader without access to the Gold text |
| **Design Decision** | Added a fourth match-basis value, `phonetic_artifact`, distinct from `semantic`, to the tool schema for `symptom_matches`, `intervention_matches`, `clinical_status_match`, and `notification_match`. Added an explicit rule and worked examples (including the "체스파인" case observed in the pilot) to `SYSTEM_PROMPT`, framed around the test "would a Korean-speaking reader understand the clinical concept from the Whisper string alone, without seeing Gold?" In evaluation (`src/evaluation/flatten_matches.py`), `phonetic_artifact` is treated identically to `omission` (`OMISSION_EQUIVALENT_BASES`), since the underlying clinical information was not intelligibly preserved either way |
| **Reason** | Keeping `phonetic_artifact` as a distinct category (rather than having Claude directly output `omission` for these cases) preserves an audit trail: the raw `*_matched.json` output still records *why* an item was scored as unpreserved, which supports reporting in the KOSMI writeup (e.g., "N of M pilot symptom matches were reclassified from semantic to phonetic_artifact") |
| **Impact on the evaluation pipeline** | This is a prompt-level mitigation only — no independent phonetic-similarity detector was added, so Claude's judgment at the boundary (e.g., partially-recognizable loanwords) remains the final arbiter and residual misclassification cannot be fully ruled out. Re-running the original 15-sample pilot (Week 2) will quantify how many symptom/intervention/status/notification matches are reclassified, and whether style-level CCER rankings are affected |

---

## 5. CCER Formula: Penalizing Whisper-only (Hallucinated) Insertions

| Field | Content |
|---|---|
| **Original Design** | `src/evaluation/ccer_eval.py` computed `CCER = sum(weight_i * count_i) / gold_entity_count` over records with a Gold counterpart; `whisper_only` records (entities present only in the Whisper transcript, with no Gold counterpart) had `error_type=None` and were silently excluded from the numerator |
| **Issue observed during implementation** | Documented as Limitation 6. A Whisper/extraction pipeline that hallucinates additional clinical content (fabricated symptoms, devices, doses, etc.) not present in Gold received no penalty at all, even though such insertions can actively mislead a reader of the resulting record |
| **Design Decision** | `src/evaluation/flatten_matches.py` now assigns `error_type="hallucination"` to every record with `match_status="whisper_only"` (across both closed-vocabulary and open-vocabulary paths). `src/evaluation/ccer_eval.py` adds `"hallucination": 3` to `ERROR_WEIGHTS`, the same tier as `numeric_error` / `negation_flip` / `severity_shift`. The denominator (`gold_entity_count`) is unchanged, since `whisper_only` records have `gold_value=None` and were never part of it |
| **Reason** | A hallucinated insertion is judged to carry a similar order of patient-safety risk as corrupting an existing value (numeric/negation/severity errors), since both can lead a reader to act on information that does not reflect the patient's actual state — one by altering a true fact, the other by inventing a false one. This is a researcher-assigned approximation, not a validated clinical severity scale (same caveat as the original `ERROR_WEIGHTS` design), and is a candidate for adjustment after clinical-expert review (Limitation 8) |
| **Impact on the evaluation pipeline** | CCER scores for any sample containing whisper_only insertions will now be strictly higher than under the v1 formula (all else equal), since the numerator can only increase while the denominator is unchanged. Whether this changes the WER-CCER "reversal" finding reported in the pilot (Telegraphic ICU best under CCER, worst under WER) depends on how hallucination insertions are distributed across styles — this is exactly what the Week 2 re-run of the 15-sample pilot is designed to check before scaling to 50 scenarios |