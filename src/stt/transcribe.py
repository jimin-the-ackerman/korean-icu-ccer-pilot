"""
OpenAI Whisper API Speech Recognition

Pipeline:
data/audio/{sample_id}.mp3
    -> OpenAI Whisper API (whisper-1, language="ko")
    -> data/stt_transcripts/{sample_id}.json
"""

import argparse
import json
import os
import time
from pathlib import Path

import yaml
from openai import OpenAI
from dotenv import load_dotenv

from src.pipeline_utils import RunLog, add_overwrite_arg, should_skip

load_dotenv()

MAX_RETRIES = 3


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_audio_files(audio_dir: str, output_format: str) -> list[Path]:
    return sorted(Path(audio_dir).glob(f"*.{output_format}"))


def transcribe_one(client, model, language, audio_path):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=model,
                    language=language,
                    file=audio_file
                )
            return response.text
        except Exception as e:
            print(f"  재시도 {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(1)

    return None


def transcribe_all(audio_dir, stt_dir, model, language, output_format, overwrite=False):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    out_path = Path(stt_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    audio_files = get_audio_files(audio_dir, output_format)
    run_log = RunLog()

    for i, audio_path in enumerate(audio_files, start=1):
        sample_id = audio_path.stem
        file_path = out_path / f"{sample_id}.json"

        if should_skip(file_path, overwrite):
            print(f"[{i}/{len(audio_files)}] {sample_id} 이미 존재, 건너뜀 (--overwrite로 재생성 가능)")
            run_log.record(sample_id, "skipped")
            continue

        print(f"[{i}/{len(audio_files)}] {sample_id} 전사 중...")

        transcript = transcribe_one(client, model, language, audio_path)

        if transcript is not None:
            record = {
                "sample_id": sample_id,
                "whisper_transcript": transcript,
                "stt_metadata": {
                    "model": model,
                    "language": language
                }
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            run_log.record(sample_id, "processed")
            print(f"  생성됨: {file_path}")
        else:
            run_log.record(sample_id, "failed")
            print(f"  실패, 건너뜀: {sample_id}")

    log_path = run_log.save(out_path, "generation_log.json")
    run_log.print_summary()

    s = run_log.summary()
    print(f"\n총 {len(s['processed'])}개 신규 전사, {len(s['skipped'])}개 건너뜀 (총 {len(audio_files)}개 중) -> {stt_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    add_overwrite_arg(parser)
    args = parser.parse_args()

    config = load_config()
    audio_dir = config["paths"]["audio_dir"]
    stt_dir = config["paths"]["stt_transcripts_dir"]
    model = config["stt"]["model"]
    language = config["stt"]["language"]
    output_format = config["tts"]["output_format"]

    transcribe_all(audio_dir, stt_dir, model, language, output_format, overwrite=args.overwrite)