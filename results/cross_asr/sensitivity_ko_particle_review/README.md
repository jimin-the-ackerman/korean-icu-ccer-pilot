# Manual review of the S1 sensitivity analysis - Condition A (2026-11-06)

Post hoc evaluator sensitivity analysis S1 (docs/cross_asr_spec.md Section 13; v4 remains the
primary analysis). This folder records the manual review of S1 outputs; it does not change any v4
or S1 result file.

## Scope

- Condition A only (`whisper1`, `gpt4o_transcribe`, `chirp3_ko`); September v4 and Condition B rows
  of the same files were not reviewed.
- Sources (read only; SHA-256 checked at installation):
  - `results/cross_asr/sensitivity_ko_particle/side_effect_audit.csv`
    (7bc93222815c905c35df08bbe949cc3e8d2538cc1a4cd5df5538d0f2a3f52c7d) - 40 Condition A rows
    (all changed records not ending as "matched")
  - `results/cross_asr/sensitivity_ko_particle/omission_to_matched_stratified_sample.csv`
    (4418bea74bf230888fbfbfe612165f804575b0b9ed5ee8028913d9d2c002a204) - 30 Condition A rows
    (stratified sample, 2 per condition x style x entity type, seed 20261103)
- Method: transcript context (`context_s1`, full transcript) compared with the gold scaffold; labels
  proposed by Claude, reviewed and adopted by the researcher (2026-11-06). No audio was listened to.

## Labels (`review_labels_condA.csv`)

| Label | Meaning |
|---|---|
| `valid_match` | omission -> matched: the gold value is present in the transcript (attached particle) and S1 matches it correctly |
| `evaluator_artifact` | a new S1 error / hallucination produced by unchanged v4 rules, not by the transcript; `artifact_subtype` gives the cause |
| `gold_transcript_mismatch` | the transcript differs from the gold value; whether the ASR or the TTS audio is the source is not determined |
| `needs_audio_review` | the same gold value is wrong in two or more Condition A systems; the source (ASR or TTS audio) cannot be decided without listening. This label does NOT mean that a TTS error is established |
| `evaluator_correction` | S1 replaces a v4 judgement by a more accurate one |

`secondary_note` records additional causes (S12: compound cause).

## Counts

- Omission -> matched (30): `valid_match` 30. This is the result for a stratified sample; it does not
  estimate the accuracy (or false-match rate) of all 992 omission -> matched changes across conditions.
- Side effects (40): `evaluator_artifact` 24, `gold_transcript_mismatch` 10, `needs_audio_review` 5,
  `evaluator_correction` 1.
  - `evaluator_artifact` subtypes: duplicate IV mention 14, duplicate device mention 2, fluid volume
    read as dose 3, oxygen flow read as dose 3, mg/kg unit representation 2.
  - S12 (`whisper1`, scenario_099_formal_template): main label `gold_transcript_mismatch` (oxygen flow
    "40 L/min" transcribed as "40mg"); secondary note: a correct transcript would also be scored as a
    dose hallucination under v4 (oxygen flow read as dose), so the cause is compound.
  - S11 and S28 (`whisper1` / `gpt4o_transcribe`, scenario_088_formal_template): main label
    `evaluator_artifact` (mg/kg unit representation); secondary note: the transcripts also lack the
    gold "/kg" ("300mg을"), so a real gold-transcript mismatch is present as well (compound cases).

## Limitations

- Labels are judgements from transcript text and scaffold only; audio was not reviewed.
- The S1 CCER values contain residual evaluator artifacts (the 24 `evaluator_artifact` records in
  Condition A). Their effect on CCER was not recomputed or validated, and no corrected value is reported.
- Not reviewed: September v4 and Condition B rows; side effects of other conditions.
