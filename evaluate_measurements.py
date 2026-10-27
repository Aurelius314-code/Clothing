"""Run live garment-measurement evaluations against measure.py and save results locally."""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

import measure
from measurement_benchmark import load_cases, score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="measurement_cases.csv")
    parser.add_argument("--output", default="measurement_results.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    cases = cases[:args.limit] if args.limit else cases
    if args.dry_run:
        print(f"Validated {len(cases)} cases. No DeepSeek calls made.")
        return
    load_dotenv(Path(__file__).resolve().parent / ".env")
    key = measure.api_key()
    if not key:
        parser.error("DEEPSEEK_API_KEY missing from local .env")
    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['case_id']}", flush=True)
        try:
            readings, raw = measure.read_measurements(
                case["photos"], case["garment_type"], case["title"],
                case["description"], key, measure.model_name()
            )
            result = {
                "case_id": case["case_id"],
                "predicted_measurements": readings,
                "score": score(case["expected_measurements"], readings),
                "raw_response": raw,
            }
        except Exception as exc:
            result = {"case_id": case["case_id"], "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    successful = [r for r in results if "score" in r]
    print(f"Completed {len(successful)}/{len(results)} calls.")
    if successful:
        print(f"Entirely correct cases: {sum(r['score']['all_correct'] for r in successful)}/{len(successful)}")
        print(f"Measurements within 1 cm: {sum(r['score']['within_tolerance'] for r in successful)}/"
              f"{sum(r['score']['expected_count'] for r in successful)} expected")
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
