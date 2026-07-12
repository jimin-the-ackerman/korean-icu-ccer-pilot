"""
GPT-4o Style-controlled Documentation Generation 

Pipeline:
Content Scaffold (data/scenarios/*.json)
    -> Style Controller (system/user prompt construction)
    -> GPT-4o (free-text generation)
    -> data/generated_text/{scenario_id}_{style}.json

[Design Principle]
Documentation Generation 단계의 정보 보존은 Prompt Constraint를 통해
보장하는 것으로 가정하며, 별도의 정량적 평가는 수행하지 않는다.
Entity-level 평가는 이후 Whisper STT Transcript를 대상으로 수행한다.
"""

import json
import os
import time
from pathlib import Path

import yaml
from openai import OpenAI
from dotenv import load_dotenv

from src.style_controller.style_controller import build_generation_prompt, get_all_style_keys

load_dotenv()

MAX_RETRIES = 3
MIN_TEXT_LENGTH = 10  # sanity check: 너무 짧으면 생성 실패로 간주


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scaffolds(scenarios_dir: str) -> list[dict]:
    scaffolds = []
    for f in sorted(Path(scenarios_dir).glob("scenario_*.json")):
        with open(f, "r", encoding="utf-8") as fh:
            scaffolds.append(json.load(fh))
    return scaffolds


def generate_one_note(client, model, temperature, scaffold, style_key):
    system_prompt, user_prompt = build_generation_prompt(scaffold, style_key)

    for attempt in range(1, MAX_RETRIES + 1):
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        text = response.choices[0].message.content.strip()

        if len(text) >= MIN_TEXT_LENGTH:
            return text

        print(f"  재시도 {attempt}/{MAX_RETRIES}: 텍스트가 너무 짧음 ({len(text)}자)")
        time.sleep(1)

    raise RuntimeError("MAX_RETRIES 초과, 텍스트 생성 실패")


def generate_all_notes(scenarios_dir, output_dir, model, temperature):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    scaffolds = load_scaffolds(scenarios_dir)
    style_keys = get_all_style_keys()

    generation_log = []
    total = len(scaffolds) * len(style_keys)
    count = 0

    for scaffold in scaffolds:
        scenario_id = scaffold["scenario_id"]
        for style_key in style_keys:
            count += 1
            sample_id = f"{scenario_id}_{style_key}"
            print(f"[{count}/{total}] {sample_id} 생성 중...")

            try:
                text = generate_one_note(client, model, temperature, scaffold, style_key)
            except RuntimeError as e:
                print(f"  실패, 건너뜀: {e}")
                generation_log.append({"sample_id": sample_id, "status": "failed", "error": str(e)})
                continue

            record = {
                "sample_id": sample_id,
                "scenario_id": scenario_id,
                "document_type": "ICU_observation",
                "style_condition": style_key,
                "text": text,
                "generation_metadata": {
                    "model": model,
                    "temperature": temperature
                }
            }

            file_path = out_path / f"{sample_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            generation_log.append({"sample_id": sample_id, "status": "success"})
            print(f"  생성됨: {file_path}")

    log_path = out_path / "generation_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(generation_log, f, ensure_ascii=False, indent=2)

    success_count = sum(1 for r in generation_log if r["status"] == "success")
    print(f"\n총 {success_count}/{total}개 생성 완료 -> {output_dir}")


if __name__ == "__main__":
    config = load_config()
    scenarios_dir = config["paths"]["scenarios_dir"]
    output_dir = config["paths"]["generated_text_dir"]
    model = config["generation"]["model"]
    temperature = config["generation"]["temperature"]

    generate_all_notes(scenarios_dir, output_dir, model, temperature)