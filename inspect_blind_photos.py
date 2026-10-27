"""Run blinded photo-only second passes on the two unlabelled eBay candidates.

Costs one extraction call per listing plus one call per extracted photo measurement.
Does not modify SQLite. Results are NOT ground-truth accuracy scores.
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
import measure
from measurement_benchmark import load_cases
from photo_verification import inspect_case


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="measurement_cases.csv")
    p.add_argument("--output", default="blind_photo_results.json")
    p.add_argument("--limit", type=int, default=2)
    args = p.parse_args()
    if args.limit < 1:
        p.error("--limit must be >= 1")
    load_dotenv(Path(__file__).resolve().parent / ".env")
    key = measure.api_key()
    if not key:
        p.error("DEEPSEEK_API_KEY missing from .env")
    results = []
    for case in load_cases(args.dataset)[:args.limit]:
        print(f"Blinded inspection: {case['case_id']}", flush=True)
        try:
            result = inspect_case(case, key)
        except Exception as exc:
            result = {"case_id": case["case_id"], "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
