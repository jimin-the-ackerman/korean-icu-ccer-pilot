"""
semantic_matcher.py의 MATCH_TOOL 스키마 검증.

limitations.md #5 대응으로 추가된 "phonetic_artifact" match_basis가
symptom_matches / intervention_matches / clinical_status_match /
notification_match 네 곳 모두의 enum에 반영되었는지 확인한다.
실제 Claude API 호출 없이 스키마 정의만 정적으로 검사한다.
"""

from src.matching.semantic_matcher import MATCH_TOOL, SYSTEM_PROMPT

PROPS = MATCH_TOOL["input_schema"]["properties"]


def _enum_for(*path):
    node = PROPS
    for key in path:
        node = node[key]
    return node["enum"]


def test_symptom_matches_enum_includes_phonetic_artifact():
    enum = _enum_for("symptom_matches", "items", "properties", "match_basis")
    assert "phonetic_artifact" in enum
    assert "semantic" in enum  # 기존 카테고리 보존 확인


def test_intervention_matches_enum_includes_phonetic_artifact():
    enum = _enum_for("intervention_matches", "items", "properties", "match_basis")
    assert "phonetic_artifact" in enum


def test_clinical_status_match_enum_includes_phonetic_artifact():
    enum = _enum_for("clinical_status_match", "properties", "match_basis")
    assert "phonetic_artifact" in enum
    assert "whisper_only" in enum  # 기존 카테고리 보존 확인


def test_notification_match_enum_includes_phonetic_artifact():
    enum = _enum_for("notification_match", "properties", "match_basis")
    assert "phonetic_artifact" in enum


def test_system_prompt_mentions_phonetic_artifact_rule():
    assert "phonetic_artifact" in SYSTEM_PROMPT
    assert "체스파인" in SYSTEM_PROMPT  # limitations.md #5의 실제 사례가 예시로 남아있는지


if __name__ == "__main__":
    test_symptom_matches_enum_includes_phonetic_artifact()
    test_intervention_matches_enum_includes_phonetic_artifact()
    test_clinical_status_match_enum_includes_phonetic_artifact()
    test_notification_match_enum_includes_phonetic_artifact()
    test_system_prompt_mentions_phonetic_artifact_rule()
    print("All semantic_matcher schema tests passed.")
