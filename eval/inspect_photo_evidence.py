"""Inspect DeepSeek's real-photo evidence decisions without ground-truth scoring.

Uses the local measurement_cases.csv and DeepSeek API. Does not write SQLite.
Run: python inspect_photo_evidence.py --limit 2
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from _paths import EVAL_DIR, ROOT
import measure
from measurement_benchmark import load_cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(EVAL_DIR / "measurement_cases.csv"))
    parser.add_argument("--output", default=str(EVAL_DIR / "photo_evidence_results.json"))
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    cases = load_cases(args.dataset)[:args.limit]
    load_dotenv(ROOT / ".env")
    key = measure.api_key()
    if not key:
        parser.error("DEEPSEEK_API_KEY missing from .env")
    results = []
    for case in cases:
        print(f"Analysing {case['case_id']} ({len(case['photos'])} photos)...", flush=True)
        try:
            accepted, raw = measure.read_measurements(
                case["photos"], case["garment_type"], case["title"],
                case["description"], key, measure.model_name()
            )
            payload = measure._json_object(raw)
            result = {
                "case_id": case["case_id"],
                "accepted_measurements": accepted,
                "rejected_photo_measurements": payload.get("rejected_photo_measurements", []),
                "model_claims": payload.get("measurements", []),
                "ground_truth_status": "UNLABELLED — no accuracy score",
            }
        except Exception as exc:
            result = {"case_id": case["case_id"], "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {args.output}. No database changes. Results are not accuracy scores.")


if __name__ == "__main__":
    main()
