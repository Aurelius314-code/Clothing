"""Run live garment-measurement evaluations against measure.py and save results locally."""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from _paths import EVAL_DIR, ROOT
import measure
from measurement_benchmark import load_cases, score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(EVAL_DIR / "measurement_cases.csv"))
    parser.add_argument("--output", default=str(EVAL_DIR / "measurement_results.json"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--strict", dest="strict", action="store_true", default=None,
                      help="drop photo readings without clear tape evidence")
    mode.add_argument("--lenient", dest="strict", action="store_false",
                      help="keep them, marked uncertain (default unless STRICT_PHOTO_EVIDENCE is set)")
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    cases = cases[:args.limit] if args.limit else cases
    if args.dry_run:
        print(f"Validated {len(cases)} cases. No DeepSeek calls made.")
        return
    load_dotenv(ROOT / ".env")
    key = measure.api_key()
    strict = measure.strict_photo_evidence() if args.strict is None else args.strict
    print(f"Photo evidence gate: {'strict' if strict else 'lenient'}")
    if not key:
        parser.error("DEEPSEEK_API_KEY missing from local .env")
    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['case_id']}", flush=True)
        try:
            readings, raw = measure.read_measurements(
                case["photos"], case["garment_type"], case["title"],
                case["description"], key, measure.model_name(), strict=strict
            )
            result = {
                "case_id": case["case_id"],
                "gate": "strict" if strict else "lenient",
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
