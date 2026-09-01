"""
파이프라인 스크립트 공통 유틸리티.

[배경]
5→50 시나리오 확장 시, 기존 scenario_001~005(및 그 하위 산출물 - 생성 텍스트,
오디오, STT 전사, entity, 매칭 결과)를 절대 덮어써서는 안 된다. v1/v2/v3
전체가 이 5개 시나리오의 실제 내용(Ceftriaxone/Foley/Hydralazine 등)을
기준으로 검증되어 왔기 때문에, 재생성 시 완전히 다른 내용으로 바뀌면
재현성이 깨진다.

이 모듈은 두 가지 공통 안전장치를 파이프라인 스크립트 전체(생성/추출/매칭
8개)에 일관되게 제공한다:
1. 기본값은 "이미 존재하는 output은 건너뛴다". `--overwrite`(`--force`도 동일
   의미의 별칭) 플래그를 명시해야만 재생성한다.
2. 각 단계는 sample_id 단위로 processed/skipped/failed를 기록한 실행 로그를
   남긴다. 이를 통해 50개 확장 후 "어떤 시나리오가 어느 단계에서 빠졌는지"를
   바로 확인할 수 있고, 중간에 중단된 경우 그 단계부터 이어서 실행할 수 있다
   (스킵 로직 덕분에 재실행 자체가 곧 "이어서 실행하기"가 된다).
"""

import argparse
import json
from pathlib import Path


def add_overwrite_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """--overwrite/--force 플래그를 추가한다. 기본값은 False(=건너뛰기)."""
    parser.add_argument(
        "--overwrite", "--force", dest="overwrite", action="store_true",
        help="이미 존재하는 output 파일도 다시 생성한다 (기본값: 존재하면 건너뜀)"
    )
    return parser


class RunLog:
    """단계별 processed/skipped/failed를 sample_id 단위로 기록하는 실행 로그.

    사용 예:
        run_log = RunLog()
        run_log.record("scenario_001", "skipped")
        run_log.record("scenario_006", "processed", model="gpt-4o")
        run_log.record("scenario_007", "failed", error="...")
        run_log.save(output_dir, "generation_log.json")
        run_log.print_summary()
    """

    VALID_STATUSES = ("processed", "skipped", "failed")

    def __init__(self):
        self.entries = []

    def record(self, sample_id: str, status: str, **extra):
        if status not in self.VALID_STATUSES:
            raise ValueError(f"status는 {self.VALID_STATUSES} 중 하나여야 함, 받은 값: {status!r}")
        self.entries.append({"sample_id": sample_id, "status": status, **extra})

    def summary(self) -> dict:
        """{"processed": [...], "skipped": [...], "failed": [...]} 형태로 sample_id 목록 반환."""
        out = {status: [] for status in self.VALID_STATUSES}
        for e in self.entries:
            out[e["status"]].append(e["sample_id"])
        return out

    def save(self, output_dir, filename: str = "generation_log.json") -> Path:
        """entries 전체와 summary를 함께 JSON으로 저장."""
        path = Path(output_dir) / filename
        payload = {"entries": self.entries, "summary": self.summary()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def print_summary(self):
        s = self.summary()
        print(
            f"\n=== 실행 요약: processed={len(s['processed'])}, "
            f"skipped={len(s['skipped'])}, failed={len(s['failed'])} ==="
        )
        if s["failed"]:
            print(f"실패 목록 ({len(s['failed'])}개): {s['failed']}")


def should_skip(output_path, overwrite: bool) -> bool:
    """output_path가 이미 존재하고 overwrite가 False면 건너뛰어야 함(True 반환)."""
    return Path(output_path).exists() and not overwrite
