"""
v4 실데이터 전수 스캔 (docs/v4_style_invariant_extraction_spec.md §10.5)

100개 시나리오의 Gold(data/generated_text) + Whisper(data/stt_transcripts)
텍스트 전체에 새 closed_vocab_extractor.py를 실행해:
1. 의도치 않은 entity_type 오매칭이 있는지(§5.2 위험 패턴 재확인)
2. Formal Template의 vital_sign/route/frequency/device가 실제로 얼마나
   개선되는지(기존 100%/87%/92%/88% 미인식률 대비)
를 확인한다. 순수 정규식이라 API 호출 없음.

사용법:
    python -m src.analysis.v4_crosscheck
"""

import json
import glob

from src.entity_extraction.closed_vocab_extractor import extract_closed_vocab_entities

RISK_KEYWORDS = {
    "vital_sign": ["호흡곤란", "정맥류"],  # symptom 오염 감시용 참고 키워드
}


def scan_style_recognition_rate():
    """스타일별로 각 entity_type이 최소 1건이라도 인식되는 텍스트 비율."""
    counts = {
        style: {et: {"has_match": 0, "total": 0} for et in
                ["vital_sign", "route", "frequency", "device"]}
        for style in ["formal_template", "clinical_charting", "telegraphic_icu"]
    }

    for path in sorted(glob.glob("data/stt_transcripts/scenario_*.json")):
        d = json.load(open(path, encoding="utf-8"))
        sample_id = d["sample_id"]
        style = "_".join(sample_id.split("_")[2:])
        if style not in counts:
            continue
        text = d["whisper_transcript"]
        result = extract_closed_vocab_entities(text)

        for et in ["vital_sign", "route", "frequency", "device"]:
            counts[style][et]["total"] += 1
            if result[et]:
                counts[style][et]["has_match"] += 1

    print("=== 스타일별 entity_type 인식률 (v4 적용 후) ===")
    for style, ets in counts.items():
        print(f"\n{style}:")
        for et, c in ets.items():
            rate = c["has_match"] / c["total"] if c["total"] else 0
            print(f"  {et:12s}: {c['has_match']:3d}/{c['total']:3d} ({rate:.0%})")


def scan_false_positive_risk():
    """§5.2 위험 패턴이 실제로 오매칭되지 않는지 100개 데이터 전체에서 재확인.
    위치(position)가 실제로 겹치는 경우만 진짜 오매칭으로 카운트한다
    (같은 문서에 위험 키워드가 있다는 것만으로는 오매칭이 아님)."""
    import re
    true_issues = []
    all_files = sorted(glob.glob("data/generated_text/scenario_*.json")) + \
        sorted(glob.glob("data/stt_transcripts/scenario_*.json"))

    danger_spans_patterns = {
        "호흡곤란(symptom)": re.compile(r"호흡곤란"),
        "정맥류(symptom)": re.compile(r"정맥류"),
        "정맥관(device)": re.compile(r"정맥관"),
    }

    for path in all_files:
        d = json.load(open(path, encoding="utf-8"))
        text = d.get("text") or d.get("whisper_transcript", "")
        result = extract_closed_vocab_entities(text)

        danger_spans = []
        for label, pat in danger_spans_patterns.items():
            for m in pat.finditer(text):
                danger_spans.append((label, m.start(), m.end()))

        if not danger_spans:
            continue

        for vs in result["vital_sign"]:
            vs_start, vs_end = vs["position"], vs["position"] + len(vs["raw"])
            for label, ds, de in danger_spans:
                if vs_start < de and ds < vs_end:  # 실제 위치 겹침
                    true_issues.append((path, f"vital_sign({vs['label']}) vs {label}", text[max(0,ds-5):de+5]))

        for r in result["route"]:
            r_start, r_end = r["position"], r["position"] + len(r["raw"])
            for label, ds, de in danger_spans:
                if r_start < de and ds < r_end:
                    true_issues.append((path, f"route({r['normalized']}) vs {label}", text[max(0,ds-5):de+5]))

    print(f"\n=== False Positive 위험 패턴 재확인 (위치 겹침 기준, 100개 데이터 전체) ===")
    if not true_issues:
        print("실제 위치가 겹치는 오매칭 없음 - §5.2 위험 패턴 전부 정상적으로 회피됨")
    else:
        print(f"{len(true_issues)}건 실제 오매칭 발견:")
        for path, issue, context in true_issues[:20]:
            print(f"  [{path.split('/')[-1]}] {issue}: ...{context}...")


def main():
    scan_style_recognition_rate()
    scan_false_positive_risk()


if __name__ == "__main__":
    main()
