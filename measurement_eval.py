"""Evaluate DeepSeek garment-measurement extraction against manually labelled images.

This tool does not import watcher.py, touch SQLite, or modify the wardrobe.
Python 3.10+. Install requirements.txt and configure DEEPSEEK_API_KEY in .env.
"""
import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
TYPES = {
    "pit_to_pit", "shoulder_width", "sleeve_length", "body_length",
    "waist_flat", "hip_flat", "thigh_flat", "inseam", "outseam",
    "front_rise", "back_rise", "leg_opening", "neck", "unknown"
}
INPUT_FIELDS = ["case_id", "image_url", "garment_type", "expected_has_tape",
                "expected_type", "expected_value", "expected_unit"]
OUTPUT_FIELDS = INPUT_FIELDS + [
    "predicted_has_tape", "predicted_type", "predicted_value",
    "predicted_unit", "evidence", "confidence", "needs_review",
    "tape_correct", "type_correct", "value_error_cm",
    "model", "finish_reason", "prompt_tokens", "completion_tokens",
    "elapsed_seconds", "error", "raw_response"
]

PROMPT = """You are examining a photograph from a vintage clothing listing.
The garment category is: {garment_type}.
Determine whether a measuring tape or ruler is visibly measuring a garment.
Only report a numerical measurement if its reading and unit are visible.
Identify WHAT is measured using tape position, endpoints, seams and garment geometry.
Do not infer a measurement type solely from its numerical value.
If the endpoints or measurement type cannot be identified, use "unknown".
A photograph of a label, garment, or text without a tape/ruler is not a tape measurement.
Return ONLY a JSON object with:
{{
 "has_tape": boolean,
 "measurement_type": one of {types},
 "value": number or null,
 "unit": "in", "cm", or null,
 "evidence": brief visual description of tape placement and endpoints,
 "confidence": "high", "medium", or "low",
 "needs_review": boolean
}}
Use null for unreadable numbers. Never fabricate a number or endpoints.
If no tape/ruler is visible, set has_tape=false, measurement_type="unknown",
value=null, unit=null, needs_review=true.
"""

def truth_bool(value):
    value = value.strip().lower()
    if value in ("true", "1", "yes"): return True
    if value in ("false", "0", "no"): return False
    return None

def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def to_cm(value, unit):
    return value * (2.54 if unit == "in" else 1.0) if value is not None and unit in ("in", "cm") else None

def parse_response(content):
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", content, flags=re.I).strip()
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return a JSON object")
        obj = json.loads(content[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("Model response must be an object")
    if type(obj.get("has_tape")) is not bool:
        raise ValueError("has_tape must be boolean")
    kind = obj.get("measurement_type")
    if kind not in TYPES:
        raise ValueError("Unknown measurement_type: " + str(kind))
    unit = obj.get("unit")
    if unit not in ("in", "cm", None):
        raise ValueError("Invalid unit")
    value = obj.get("value")
    if value is not None and (type(value) not in (int, float) or value <= 0):
        raise ValueError("Invalid value")
    if not obj["has_tape"] and (value is not None or kind != "unknown"):
        raise ValueError("Inconsistent no-tape result")
    return obj

def download_image(url, max_bytes=8 * 1024 * 1024):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Image must use an HTTPS URL")
    # Restrict network access to public eBay image hosts for this experiment.
    if parsed.hostname.lower() not in ("i.ebayimg.com", "i.ebayimg.co.uk"):
        raise ValueError("Only eBay image-host URLs are accepted")
    with requests.get(url, timeout=(10, 20), stream=True, allow_redirects=False,
                      headers={"User-Agent": "VintageWardrobeWatcher/measurement-eval"}) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").split(";")[0].lower()
        if content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError("Unsupported image MIME type: " + content_type)
        data = bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ValueError("Image exceeds 8 MiB limit")
        if not data:
            raise ValueError("Image is empty")
        return "data:" + content_type + ";base64," + base64.b64encode(data).decode("ascii")

def analyze(url, garment_type, api_key, model, timeout):
    data_url = download_image(url)
    prompt = PROMPT.format(garment_type=garment_type or "unknown",
                           types=", ".join(sorted(TYPES)))
    response = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": "Bearer " + api_key},
        json={
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]}],
            "thinking": {"type": "disabled"},
            "max_tokens": 1000
        },
        timeout=(10, timeout)
    )
    response.raise_for_status()
    payload = response.json()
    choice = payload["choices"][0]
    raw = choice["message"].get("content") or ""
    parsed = parse_response(raw)
    usage = payload.get("usage") or {}
    return parsed, raw, payload.get("model", ""), choice.get("finish_reason", ""), usage

def evaluate(row, pred):
    expected_tape = truth_bool(row.get("expected_has_tape", ""))
    expected_type = row.get("expected_type", "").strip()
    expected_value = number(row.get("expected_value", ""))
    expected_unit = row.get("expected_unit", "").strip().lower()
    tape_correct = "" if expected_tape is None else str(expected_tape == pred["has_tape"])
    type_correct = "" if not expected_type else str(expected_type == pred["measurement_type"])
    actual_cm = to_cm(expected_value, expected_unit)
    predicted_cm = to_cm(pred.get("value"), pred.get("unit"))
    error = "" if actual_cm is None or predicted_cm is None else round(abs(actual_cm - predicted_cm), 2)
    return tape_correct, type_correct, error

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="measurement_cases.csv", help="Labelled input CSV")
    parser.add_argument("--output", default="measurement_results.csv", help="Results CSV")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of cases; 0=all")
    parser.add_argument("--dry-run", action="store_true", help="Validate input without API calls")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not args.dry_run and not api_key:
        parser.error("DEEPSEEK_API_KEY is missing from .env")
    source = Path(args.input)
    if not source.exists():
        parser.error("Input file not found: " + str(source))
    with source.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(INPUT_FIELDS) - set(reader.fieldnames or [])
        if missing:
            parser.error("Missing CSV columns: " + ", ".join(sorted(missing)))
        cases = list(reader)
    if args.limit:
        cases = cases[:args.limit]
    ids = set()
    for i, row in enumerate(cases, 1):
        case_id = row["case_id"].strip()
        if not case_id or case_id in ids:
            parser.error("Blank/duplicate case_id on row " + str(i + 1))
        ids.add(case_id)
        if row["expected_type"].strip() and row["expected_type"].strip() not in TYPES:
            parser.error("Invalid expected_type for " + case_id)
        if row["expected_unit"].strip() and row["expected_unit"].strip() not in ("in", "cm"):
            parser.error("Invalid expected_unit for " + case_id)
        if row["expected_has_tape"].strip() and truth_bool(row["expected_has_tape"]) is None:
            parser.error("Invalid expected_has_tape for " + case_id)
    if args.dry_run:
        print("Validated", len(cases), "cases; no API requests made.")
        return
    output = Path(args.output)
    if output.resolve() == source.resolve():
        parser.error("Input and output paths must differ")
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for i, row in enumerate(cases, 1):
            result = {field: row.get(field, "") for field in INPUT_FIELDS}
            started = time.monotonic()
            try:
                pred, raw, model, finish, usage = analyze(
                    row["image_url"].strip(), row["garment_type"].strip(),
                    api_key, args.model, args.timeout)
                tape_ok, type_ok, error = evaluate(row, pred)
                result.update(
                    predicted_has_tape=pred["has_tape"],
                    predicted_type=pred["measurement_type"],
                    predicted_value=pred.get("value"),
                    predicted_unit=pred.get("unit"),
                    evidence=pred.get("evidence", ""),
                    confidence=pred.get("confidence", ""),
                    needs_review=pred.get("needs_review", True),
                    tape_correct=tape_ok, type_correct=type_ok,
                    value_error_cm=error, model=model, finish_reason=finish,
                    prompt_tokens=usage.get("prompt_tokens", ""),
                    completion_tokens=usage.get("completion_tokens", ""),
                    raw_response=raw)
                print(f"[{i}/{len(cases)}] {row['case_id']}: {pred['measurement_type']} {pred.get('value')} {pred.get('unit')}")
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                result["error"] = type(exc).__name__ + ": " + str(exc)
                print(f"[{i}/{len(cases)}] {row['case_id']}: ERROR {result['error']}", file=sys.stderr)
            result["elapsed_seconds"] = round(time.monotonic() - started, 2)
            writer.writerow(result)
            f.flush()
    print("Results saved to", output)
    print("Review all predicted measurements against the photographs before using them for fit decisions.")

if __name__ == "__main__":
    main()
