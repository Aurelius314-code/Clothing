"""DeepEval regression tests for the production measure.py extractor.

Run: python -m pytest -q tests/test_measurements.py
Live evaluation (costs DeepSeek API credits): python evaluate_measurements.py --limit 3
"""
import csv
import json
import math
from pathlib import Path

import measure

FIELDS = ("case_id", "garment_type", "title", "description", "photos",
          "expected_measurements")
TOLERANCE_CM = 1.0


def load_cases(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Missing columns: " + ", ".join(sorted(set(FIELDS) - set(reader.fieldnames or []))))
        cases = []
        seen = set()
        for row in reader:
            case_id = row["case_id"].strip()
            if not case_id or case_id in seen:
                raise ValueError("Case IDs must be unique and nonempty")
            seen.add(case_id)
            kind = row["garment_type"].strip()
            if kind not in measure.MEASUREMENTS:
                raise ValueError(f"{case_id}: unsupported garment type {kind}")
            photos = json.loads(row["photos"])
            expected = json.loads(row["expected_measurements"])
            if not isinstance(photos, list) or not all(isinstance(p, str) and p.startswith("https://") for p in photos):
                raise ValueError(f"{case_id}: photos must be a JSON list of HTTPS image URLs")
            if not isinstance(expected, list):
                raise ValueError(f"{case_id}: expected_measurements must be a JSON list")
            names = set()
            for item in expected:
                if not isinstance(item, dict) or item.get("name") not in measure.MEASUREMENTS[kind]:
                    raise ValueError(f"{case_id}: invalid expected measurement name")
                if item["name"] in names:
                    raise ValueError(f"{case_id}: duplicate expected measurement name")
                names.add(item["name"])
                value = item.get("value_cm")
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{case_id}: invalid expected value_cm")
            cases.append({
                "case_id": case_id, "garment_type": kind,
                "title": row["title"], "description": row["description"],
                "photos": photos, "expected_measurements": expected
            })
        return cases


def score(expected, predicted, tolerance_cm=TOLERANCE_CM):
    """Exact type matches and absolute cm errors; no AI judge or confidence-based overrides."""
    truth = {m["name"]: m["value_cm"] for m in expected}
    observed = {m["name"]: m["value_cm"] for m in predicted}
    matched = truth.keys() & observed.keys()
    errors = {name: round(abs(truth[name] - observed[name]), 3) for name in matched}
    correct = sum(error <= tolerance_cm for error in errors.values())
    return {
        "expected_count": len(truth),
        "predicted_count": len(observed),
        "matched_types": len(matched),
        "missing_types": sorted(truth.keys() - observed.keys()),
        "extra_types": sorted(observed.keys() - truth.keys()),
        "within_tolerance": correct,
        "absolute_error_cm": errors,
        "exact_type_precision": len(matched) / len(observed) if observed else (1.0 if not truth else 0.0),
        "exact_type_recall": len(matched) / len(truth) if truth else 1.0,
        "all_correct": not (truth.keys() ^ observed.keys()) and correct == len(truth),
    }
