"""
Hybrid Manipulation Check (docs/hybrid_followup_spec.md Sec 5)

GPT-4o가 생성한 hybrid "generated reference note"(TTS 이전, Content
Scaffold의 Gold entity와는 다른 대상 — 용어 구분 명시)가 실제로 block
mapping(vital_sign 등은 Formal 표현, medication event/device는 Clinical
Charting 표현)을 따르고 있는지 결정론적으로 확인한다.

기존 closed_vocab_extractor.py를 그대로 재사용하며 신규 API 호출은 없다.
이 검사 결과를 보고 prompt나 block mapping을 재조정하지 않는다 — 위반율
자체를 있는 그대로 기록한다.

사용법 (data/generated_text/scenario_*_hybrid.json 생성 직후, TTS 이전):
    python -m src.analysis.hybrid_manipulation_check
"""

import json
import glob
import random
import re

from src.entity_extraction.closed_vocab_extractor import (
    extract_route,
    extract_frequency,
    extract_device,
    extract_vital_sign,
)

HANGUL_PATTERN = re.compile(r"[\uac00-\ud7a3]")

# Clinical Charting 표현이 기대되는 entity_type (medication event + device)
CLINICAL_BLOCK_ENTITY_TYPES = ["route", "frequency", "device"]
# Formal 표현이 기대되는 entity_type (이 스크립트가 결정론적으로 검사 가능한 것)
FORMAL_BLOCK_ENTITY_TYPES = ["vital_sign"]

RANDOM_SUBSAMPLE_SEED = 42
RANDOM_SUBSAMPLE_SIZE = 12


def is_korean_form(raw_text: str) -> bool:
    return bool(HANGUL_PATTERN.search(raw_text))


def check_sample(text: str) -> dict:
    result = {}

    clinical_matches = []
    for extractor, et in [(extract_route, "route"), (extract_frequency, "frequency"),
                           (extract_device, "device")]:
        for m in extractor(text):
            clinical_matches.append((et, m["raw"]))
    result["clinical_block_total"] = len(clinical_matches)
    result["clinical_block_english_form"] = sum(
        1 for _, raw in clinical_matches if not is_korean_form(raw)
    )

    formal_matches = [(vs["label"], vs["raw"]) for vs in extract_vital_sign(text)]
    result["formal_block_total"] = len(formal_matches)
    result["formal_block_korean_form"] = sum(
        1 for _, raw in formal_matches if is_korean_form(raw)
    )

    return result


def main():
    files = sorted(glob.glob("data/generated_text/scenario_*_hybrid.json"))
    if not files:
        print("data/generated_text/scenario_*_hybrid.json 파일을 찾을 수 없습니다. "
              "먼저 python -m src.generation.generate_notes 를 실행하세요.")
        return

    totals = {"clinical_block_total": 0, "clinical_block_english_form": 0,
              "formal_block_total": 0, "formal_block_korean_form": 0}
    per_sample = []

    for path in files:
        d = json.load(open(path, encoding="utf-8"))
        text = d["text"]
        r = check_sample(text)
        r["sample_id"] = d["sample_id"]
        per_sample.append(r)
        for k in totals:
            totals[k] += r[k]

    print(f"=== Hybrid Manipulation Check (결정론적, n={len(files)}) ===\n")

    clinical_rate = (totals["clinical_block_english_form"] / totals["clinical_block_total"]
                      if totals["clinical_block_total"] else float("nan"))
    formal_rate = (totals["formal_block_korean_form"] / totals["formal_block_total"]
                   if totals["formal_block_total"] else float("nan"))

    print(f"Clinical 표현 대상(route/frequency/device) 총 {totals['clinical_block_total']}건 중 "
          f"영어 약어 형태: {totals['clinical_block_english_form']}건 ({clinical_rate:.1%})")
    print(f"Formal 표현 대상(vital_sign) 총 {totals['formal_block_total']}건 중 "
          f"한국어 전체 표기 형태: {totals['formal_block_korean_form']}건 ({formal_rate:.1%})")

    # 위반이 심한 샘플(각 block의 준수율이 낮은 순) 상위 5개를 참고용으로 출력
    def sample_clinical_rate(r):
        return (r["clinical_block_english_form"] / r["clinical_block_total"]
                if r["clinical_block_total"] else 1.0)

    def sample_formal_rate(r):
        return (r["formal_block_korean_form"] / r["formal_block_total"]
                if r["formal_block_total"] else 1.0)

    worst_clinical = sorted(per_sample, key=sample_clinical_rate)[:5]
    worst_formal = sorted(per_sample, key=sample_formal_rate)[:5]

    print("\n=== 참고: Clinical 표현 위반이 가장 심한 샘플 상위 5개 ===")
    for r in worst_clinical:
        print(f"  {r['sample_id']}: {r['clinical_block_english_form']}/{r['clinical_block_total']}")

    print("\n=== 참고: Formal 표현 위반이 가장 심한 샘플 상위 5개 ===")
    for r in worst_formal:
        print(f"  {r['sample_id']}: {r['formal_block_korean_form']}/{r['formal_block_total']}")

    # 사람 검토용 무작위 부분표본 (고정 시드)
    rng = random.Random(RANDOM_SUBSAMPLE_SEED)
    sample_ids = [json.load(open(f, encoding="utf-8"))["sample_id"] for f in files]
    subsample = rng.sample(sample_ids, min(RANDOM_SUBSAMPLE_SIZE, len(sample_ids)))
    print(f"\n=== 사람 검토용 무작위 부분표본 (seed={RANDOM_SUBSAMPLE_SEED}, n={len(subsample)}) ===")
    for sid in subsample:
        print(f"  {sid}")
    print("\n각 샘플에 대해 다음을 정성 확인: (a) 정보 순서가 원본 scaffold 순서와 "
          "일치하는지, (b) 자연스러운 노트로 읽히는지.")

    with open("results/hybrid_followup_manipulation_check.json", "w", encoding="utf-8") as f:
        json.dump({
            "totals": totals,
            "clinical_block_english_form_rate": clinical_rate,
            "formal_block_korean_form_rate": formal_rate,
            "per_sample": per_sample,
            "human_review_subsample": subsample,
        }, f, ensure_ascii=False, indent=2)
    print("\n저장 완료: results/hybrid_followup_manipulation_check.json")


if __name__ == "__main__":
    import os
    os.makedirs("results", exist_ok=True)
    main()
