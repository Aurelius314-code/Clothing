"""Build a local review sheet from real eBay item IDs using the existing Browse API.

Does not write SQLite or send images to DeepSeek. Labels remain empty until manually verified.
Run from the project folder: python eval/prepare_measurement_cases.py
"""
import csv
import json

from dotenv import load_dotenv

from _paths import EVAL_DIR, ROOT
import measure
import watcher

CANDIDATES = [
    ("cordings-jacket", "800346841273", "jacket"),
    ("burberry-trousers", "168178929667", "trousers"),
]
FIELDS = ["case_id", "garment_type", "title", "description", "photos", "expected_measurements"]


def main():
    load_dotenv(ROOT / ".env")
    output = EVAL_DIR / "measurement_cases.csv"
    if output.exists():
        raise SystemExit(f"{output} already exists; refusing to overwrite manual labels.")
    access_token = watcher.token()
    rows = []
    for case_id, number, kind in CANDIDATES:
        item_id = f"v1|{number}|0"
        try:
            full = watcher.get_item(item_id, access_token)
        except Exception as exc:
            print(f"{case_id}: full listing unavailable ({type(exc).__name__}: {exc})")
            continue
        photos = measure.photos_from_item(full)
        if not photos:
            print(f"{case_id}: no photos returned; skipping")
            continue
        rows.append({
            "case_id": case_id,
            "garment_type": kind,
            "title": full.get("title", ""),
            "description": measure.listing_text(full),
            "photos": json.dumps(photos),
            # Never manufacture reference labels from the seller's size fields or DeepSeek.
            "expected_measurements": "[]",
        })
        print(f"{case_id}: {len(photos)} photos; review before labelling.")
    if not rows:
        raise SystemExit("No full listings returned. No dataset created.")
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} unlabelled candidate(s) to {output}.")
    print("IMPORTANT: [] is a placeholder, NOT verified absence of measurements.")
    print("Replace each [] with manually verified values BEFORE running live evaluation.")


if __name__ == "__main__":
    main()
