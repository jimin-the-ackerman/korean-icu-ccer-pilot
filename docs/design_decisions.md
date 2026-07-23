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