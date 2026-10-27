# DeepEval garment measurement benchmark

This experiment is based on **current main/v0.5** and uses the actual production `measure.py` parser and multi-image extractor. It does not write to SQLite or alter the watcher.

## Install and test (existing PyCharm venv)

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-eval.txt
python -m pytest -q tests/test_measurements.py
```

Offline tests validate the production parser with deterministic DeepEval metrics. No API key is needed.

## Collect manually verified examples

Copy `measurement_cases.example.csv` to `measurement_cases.csv`. Fill in real images and verified measurements. Do not treat DeepSeek's predictions as ground truth.

CSV columns:
- `case_id`: unique identifier
- `garment_type`: `jacket`, `trousers`, `knitwear`, `shirt` (exactly as in `measure.py`)
- `title`, `description`: listing context
- `photos`: JSON array of image URLs, e.g. `["https://i.ebayimg.com/..."]`
- `expected_measurements`: JSON array of manually verified normalized widths/lengths, e.g. `[{"name":"pit_to_pit","value_cm":55.9}]`

All expected values are **centimetres**, and widths use the flat convention of `measure.parse_readings`. A blank array means you verified there are no measurable dimensions in that case; do not use it for unlabelled examples.

```powershell
python evaluate_measurements.py --dry-run
python evaluate_measurements.py --limit 1
python evaluate_measurements.py
```

The live runner calls the actual `measure.read_measurements` and saves detailed output to local `measurement_results.json`. These calls consume DeepSeek credits. Begin with one case. The test script does not automatically modify any existing listings.

## Metrics and limitations

`score()` compares exact measurement keys, missing/extra measurements and absolute error in cm, using a 1 cm tolerance. A case is fully correct only if its measurement types match exactly and all values fall within tolerance. No second AI judges the results. The offline tests use DeepEval; the live runner produces scored results in JSON for manual review.

This is a **baseline**, not evidence of image-reading accuracy until labelled examples are provided and the live tests have been run. The production extractor may skip inaccessible photos, and model confidence is not calibrated. Keep evaluation cases diverse: negative examples, blurred tape endpoints, ambiguous garment types, text/photo disagreements and multiple photographs.
