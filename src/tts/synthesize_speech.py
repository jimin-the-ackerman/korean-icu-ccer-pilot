"""
OpenAI TTS Speech Generation

[Design Principle]
단일 화자(voice)를 모든 샘플에 고정하여 speaker를 통제변수로 유지한다
Pipeline:
data/generated_text/{sample_id}.json
    -> OpenAI TTS
    -> data/audio/{sample_id}.mp3
"""

import json
import os
import time
from pathlib import Path

import yaml
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MAX_RETRIES = 3


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_generated_notes(generated_text_dir: str) -> list[dict]:
    """generation_log.json은 제외하고 실제 샘플 파일만 로드."""
    notes = []
    for f in sorted(Path(generated_text_dir).glob("*.json")):
        if f.name == "generation_log.json":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            notes.append(json.load(fh))
    return notes


def synthesize_one(client, model, voice, text, output_path):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                input=text
            )
            response.stream_to_file(output_path)
            return True
        except Exception as e:
            print(f"  재시도 {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(1)

    return False


def synthesize_all(generated_text_dir, audio_dir, model, voice, output_format):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    out_path = Path(audio_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    notes = load_generated_notes(generated_text_dir)
    generation_log = []

    for i, note in enumerate(notes, start=1):
        sample_id = note["sample_id"]
        text = note["text"]
        file_path = out_path / f"{sample_id}.{output_format}"

        print(f"[{i}/{len(notes)}] {sample_id} 음성 생성 중... ({len(text)}자)")

        success = synthesize_one(client, model, voice, text, str(file_path))

        if success:
            generation_log.append({
                "sample_id": sample_id,
                "status": "success",
                "model": model,
                "voice": voice,
                "text_length": len(text)
            })
            print(f"  생성됨: {file_path}")
        else:
            generation_log.append({"sample_id": sample_id, "status": "failed"})
            print(f"  실패, 건너뜀: {sample_id}")

    log_path = out_path / "generation_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(generation_log, f, ensure_ascii=False, indent=2)

    success_count = sum(1 for r in generation_log if r["status"] == "success")
    print(f"\n총 {success_count}/{len(notes)}개 음성 생성 완료 -> {audio_dir}")


if __name__ == "__main__":
    config = load_config()
    generated_text_dir = config["paths"]["generated_text_dir"]
    audio_dir = config["paths"]["audio_dir"]
    model = config["tts"]["model"]
    voice = config["tts"]["voice"]
    output_format = config["tts"]["output_format"]

    synthesize_all(generated_text_dir, audio_dir, model, voice, output_format)