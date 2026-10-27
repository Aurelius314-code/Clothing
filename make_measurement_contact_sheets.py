"""Download eBay benchmark photos and create labelled contact sheets locally.

Usage: python make_measurement_contact_sheets.py
Output: measurement_review/<case_id>/photo_XX.jpg and <case_id>_contact_sheet.jpg
No API keys or DeepSeek calls; does not modify benchmark labels or SQLite.
"""
import csv
import io
import json
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "measurement_cases.csv"
OUTPUT = ROOT / "measurement_review"
THUMB = (360, 300)
COLS = 3
GAP = 16
HEADER = 36
MAX_BYTES = 16 * 1024 * 1024


def safe_name(value):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)[:80]


def download(url):
    if not url.startswith("https://i.ebayimg.com/"):
        raise ValueError("Only eBay image CDN URLs are permitted")
    with requests.get(url, timeout=25, stream=True) as response:
        response.raise_for_status()
        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            raise ValueError("URL did not return an image")
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError("Image exceeded 16 MB download limit")
    image = Image.open(io.BytesIO(data))
    image.load()
    return ImageOps.exif_transpose(image).convert("RGB")


def main():
    if not DATASET.exists():
        raise SystemExit("measurement_cases.csv missing; run prepare_measurement_cases.py first")
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    OUTPUT.mkdir(exist_ok=True)
    for row in rows:
        name = safe_name(row["case_id"])
        case_dir = OUTPUT / name
        case_dir.mkdir(exist_ok=True)
        photos = json.loads(row["photos"])
        images = []
        for idx, url in enumerate(photos, 1):
            try:
                image = download(url)
                image.save(case_dir / f"photo_{idx:02d}.jpg", quality=92)
                images.append((idx, image))
                print(f"{name}: saved photo {idx}/{len(photos)}")
            except Exception as exc:
                print(f"{name}: photo {idx} unavailable: {exc}")
        if not images:
            continue
        rows_count = (len(images) + COLS - 1) // COLS
        width = COLS * THUMB[0] + (COLS + 1) * GAP
        height = rows_count * (THUMB[1] + HEADER) + (rows_count + 1) * GAP
        sheet = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(sheet)
        for slot, (number, image) in enumerate(images):
            col, row_num = slot % COLS, slot // COLS
            x = GAP + col * (THUMB[0] + GAP)
            y = GAP + row_num * (THUMB[1] + HEADER + GAP)
            thumb = ImageOps.contain(image, THUMB)
            sheet.paste(thumb, (x + (THUMB[0] - thumb.width) // 2, y))
            draw.text((x + 8, y + THUMB[1] + 5), f"Photo {number:02d}", fill="black")
        dest = OUTPUT / f"{name}_contact_sheet.jpg"
        sheet.save(dest, quality=90)
        print(f"Created: {dest}")
    print("Upload the contact sheets here; individual full-size photos can be used to verify tape readings.")


if __name__ == "__main__":
    main()
