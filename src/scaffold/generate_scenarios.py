"""
GPT-4o Structured Clinical Scenario Generation 

[Data Generation Principle]
Claude는 이 스크립트의 구조/로직만 작성한다.
실제 Clinical Scenario 값(임상 내용)은 전부 GPT-4o가 생성한다.

Pipeline:
Reference Analysis (docs/reference_analysis.md)
    -> Researcher-defined Content Scaffold Schema (src/scaffold/scaffold_schema.py)
    -> GPT-4o Structured Generation (this file)
    -> data/scenarios/scenario_NNN.json
"""

import json
import os
import time
from pathlib import Path

import yaml
import jsonschema
from openai import OpenAI
from dotenv import load_dotenv

from src.scaffold.scaffold_schema import get_schema

load_dotenv()

MAX_RETRIES = 3

# OpenAI Structured Outputs 전용 스키마 (scenario_id는 스크립트가 부여하므로 제외)
GENERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "patient_context", "vital_signs", "symptom", "medication",
        "oxygen_support", "intervention", "device", "io",
        "clinical_status", "notification"
    ],
    "properties": {
        "patient_context": {"type": "string"},
        "vital_signs": {
            "type": "object",
            "additionalProperties": False,
            "required": ["BP", "HR", "RR", "BT", "SpO2"],
            "properties": {
                "BP": {"type": "string"},
                "HR": {"type": "string"},
                "RR": {"type": "string"},
                "BT": {"type": "string"},
                "SpO2": {"type": "string"}
            }
        },
        "symptom": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "negation", "severity"],
            "properties": {
                "name": {"type": "string"},
                "negation": {"type": "boolean"},
                "severity": {"type": ["string", "null"], "enum": ["mild", "moderate", "severe", None]}
            }
        },
        "medication": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["name", "dose", "route", "frequency"],
            "properties": {
                "name": {"type": "string"},
                "dose": {"type": "string"},
                "route": {"type": "string", "enum": ["IV", "PO", "IM", "SC", "SL", "PR"]},
                "frequency": {"type": ["string", "null"], "enum": ["BID", "TID", "QID", "PRN", "STAT", "q4h", "q6h", "q8h", "q12h", None]}
            }
        },
        "oxygen_support": {"type": ["string", "null"]},
        "intervention": {"type": ["string", "null"]},
        "device": {"type": ["string", "null"], "enum": ["Foley", "C-line", "ventilator", "NG tube", None]},
        "io": {"type": ["string", "null"]},
        "clinical_status": {"type": "string", "enum": ["alert", "drowsy", "stuporous", "unresponsive"]},
        "notification": {"type": ["string", "null"]}
    }
}

SYSTEM_PROMPT = """You are generating a single Content Scaffold for a Korean ICU nursing documentation research pilot.

A Content Scaffold is a structured set of clinical facts (NOT the nursing note text itself) that will later be
rendered into nursing documentation in three different styles by a separate generation step.

Follow these constraints, derived from Reference Analysis of public ICU documentation standards:
- vital_signs must be clinically plausible and internally consistent with the patient_context
  (e.g. if the patient has respiratory distress, SpO2 should be reduced accordingly)
- medication.route must be one of: IV, PO, IM, SC, SL, PR
- medication.frequency must be one of: BID, TID, QID, PRN, STAT, q4h, q6h, q8h, q12h, or null
- device must be one of: Foley, C-line, ventilator, NG tube, or null
- clinical_status must be one of: alert, drowsy, stuporous, unresponsive
- Do not include any explanation, only the structured clinical facts.
"""


def build_user_prompt(previous_contexts):
    """이전에 생성된 시나리오와 겹치지 않도록 명시적으로 요청."""
    if not previous_contexts:
        avoid_note = "This is the first scenario; no prior scenarios to avoid overlapping with."
    else:
        joined = "; ".join(previous_contexts)
        avoid_note = (
            f"Avoid repeating the same diagnosis, symptom, or medication as these "
            f"previously generated scenarios: {joined}"
        )
    return (
        "Generate one realistic ICU Content Scaffold representing a distinct clinical situation.\n"
        f"{avoid_note}\n"
        "The scenario should be clinically plausible for a general ICU setting."
    )


def load_config(config_path: str = "configs/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_one_scenario(client, model, temperature, previous_contexts):
    """GPT-4o 호출 1회 + jsonschema 이중 검증. 실패 시 MAX_RETRIES까지 재시도."""
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(previous_contexts)}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "content_scaffold",
                    "schema": GENERATION_SCHEMA,
                    "strict": True
                }
            }
        )

        raw_json = response.choices[0].message.content
        candidate = json.loads(raw_json)

        try:
            temp_with_id = {**candidate, "scenario_id": "scenario_000"}
            jsonschema.validate(instance=temp_with_id, schema=get_schema())
            return candidate
        except jsonschema.exceptions.ValidationError as e:
            last_error = str(e.message)
            print(f"  재시도 {attempt}/{MAX_RETRIES}: 검증 실패 ({last_error})")
            time.sleep(1)

    raise RuntimeError(f"MAX_RETRIES 초과, 생성 실패. 마지막 오류: {last_error}")


def generate_scaffold_files(n_scenarios, output_dir, model, temperature):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    generation_log = []
    previous_contexts = []

    for i in range(1, n_scenarios + 1):
        scenario_id = f"scenario_{i:03d}"
        print(f"[{i}/{n_scenarios}] {scenario_id} 생성 중...")

        try:
            scaffold = generate_one_scenario(client, model, temperature, previous_contexts)
        except RuntimeError as e:
            print(f"  실패, 건너뜀: {e}")
            generation_log.append({"scenario_id": scenario_id, "status": "failed", "error": str(e)})
            continue

        scaffold["scenario_id"] = scenario_id
        previous_contexts.append(scaffold["patient_context"])

        file_path = out_path / f"{scenario_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(scaffold, f, ensure_ascii=False, indent=2)

        generation_log.append({
            "scenario_id": scenario_id, "status": "success",
            "model": model, "temperature": temperature
        })
        print(f"  생성됨: {file_path}")

    log_path = out_path / "generation_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(generation_log, f, ensure_ascii=False, indent=2)
    print(f"\n생성 로그 저장: {log_path}")


if __name__ == "__main__":
    config = load_config()
    n_scenarios = config["experiment"]["n_scenarios"]
    output_dir = config["paths"]["scenarios_dir"]
    model = config["generation"]["model"]
    temperature = config["generation"]["temperature"]

    generate_scaffold_files(n_scenarios, output_dir, model, temperature)