# Measurement benchmark

Tools for checking how well DeepSeek reads garment measurements, using the app's own `measure.py`. Nothing here writes to the app's database. Run every command from the project folder (the one with `app.py`); data files and results are kept in this `eval` folder and stay off GitHub.

## Install and run the offline tests

```powershell
python -m pip install -r requirements.txt
python -m pip install -r eval/requirements-eval.txt
python -m pytest -q tests eval/tests
```

The offline tests need no API key. The DeepEval test is skipped if DeepEval isn't installed.

## Collect manually verified examples

Copy `eval/measurement_cases.example.csv` to `eval/measurement_cases.csv`, or let `python eval/prepare_measurement_cases.py` fetch candidate listings (see `FIRST_CANDIDATES.md`). Fill in real images and measurements you have checked yourself. Do not treat DeepSeek's predictions as ground truth.

CSV columns:
- `case_id`: unique identifier
- `garment_type`: `jacket`, `coat`, `waistcoat`, `trousers`, `knitwear` or `shirt` (exactly as in `measure.py`)
- `title`, `description`: listing context
- `photos`: JSON array of image URLs, e.g. `["https://i.ebayimg.com/..."]`
- `expected_measurements`: JSON array of manually verified values, e.g. `[{"name":"pit_to_pit","value_cm":55.9}]`

All expected values are **centimetres**, and widths use the flat convention of `measure.parse_readings`. A blank array means you verified there are no measurable dimensions in that case; do not use it for unlabelled examples.

`python eval/make_measurement_contact_sheets.py` downloads the photos into `eval/measurement_review/` and makes one contact sheet per listing, which makes reading the tapes yourself easier.

## Run the live benchmark

```powershell
python eval/evaluate_measurements.py --dry-run
python eval/evaluate_measurements.py --limit 1
python eval/evaluate_measurements.py
```

The live runner calls the real `measure.read_measurements` and saves detailed output to `eval/measurement_results.json`. These calls use DeepSeek credits, so begin with one case.

### Strict or lenient photo evidence

The app asks DeepSeek to say, for each photo reading, whether both ends of the tape and the scale are clearly visible. `STRICT_PHOTO_EVIDENCE` in `.env` decides what happens to readings where they aren't:

- **lenient** (default): the reading is kept but marked uncertain, so it can't make a listing red.
- **strict**: the reading is dropped.

To find out which works better on your labelled cases, run both and compare:

```powershell
python eval/evaluate_measurements.py --lenient --output eval/results_lenient.json
python eval/evaluate_measurements.py --strict --output eval/results_strict.json
```

## Other diagnostics

- `python eval/inspect_photo_evidence.py --limit 2` shows which readings the evidence gate would accept or reject, without scoring.
- `python eval/inspect_blind_photos.py --limit 2` re-reads each photo-based measurement in a separate call that sees only that one photo, without the title, the description or the first answer. Two model calls agreeing is not proof of accuracy; it only flags readings for manual review.

## Metrics and limitations

`score()` compares exact measurement keys, missing and extra measurements, and absolute error in cm, using a 1 cm tolerance. A case is fully correct only if its measurement types match exactly and all values fall within tolerance. No second AI judges the results.

This is a **baseline**, not evidence of image-reading accuracy until labelled examples are provided and the live tests have been run. The extractor may skip photos it can't download, and the model's confidence is not calibrated. Keep the cases varied: listings without measurements, blurred tape ends, ambiguous garment types, text and photo disagreeing, and several photos per listing.

In the first live run on the two candidates in `FIRST_CANDIDATES.md`, the full-listing pass reported four measurements, and the blinded second look called all four photos unreadable (see `tests/test_live_observations.py`). The readings should therefore be treated as unverified until this benchmark has been run on labelled cases.
