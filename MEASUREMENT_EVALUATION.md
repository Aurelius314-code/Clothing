# Garment measurement evaluation (experimental)

This is a **standalone test harness** for evaluating whether DeepSeek can identify both the **type** and **value** of a garment measurement from an eBay listing photograph. It does **not** modify `watcher.py`, `app.py`, `wardrobe.json`, or your SQLite database.

## Setup (Windows / PyCharm)

Use the existing virtual environment and install the repository's `requirements.txt`. Put `DEEPSEEK_API_KEY=...` in your local `.env` (never commit that file).

Copy `measurement_cases.example.csv` to `measurement_cases.csv`. The example includes the image used in the original smoke test, but its **ground-truth label is deliberately incomplete**: verify the tape placement yourself before filling in the expected type and number. The evaluator must not manufacture ground truth.

Run:

```powershell
python measurement_eval.py --input measurement_cases.csv --dry-run
python measurement_eval.py --input measurement_cases.csv --limit 1
python measurement_eval.py --input measurement_cases.csv
```

Results are written to `measurement_results.csv`. Both working CSV filenames are excluded from Git by `.gitignore`; the example template is tracked.

## Build the evaluation set

Aim for **20–30 independently labelled photographs**, across sweaters, jackets, coats and trousers. Include negative examples with no tape, unclear endpoints, different units, and ambiguous photos. Enter one image URL per row and a unique case ID.

Columns: `case_id`, `image_url`, `garment_type`, `expected_has_tape` (`true`/`false`), `expected_type`, `expected_value`, `expected_unit` (`in`/`cm`). Blank expected fields are permitted for unlabelled examples, but they **do not count toward accuracy**.

Types: `pit_to_pit`, `shoulder_width`, `sleeve_length`, `body_length`, `waist_flat`, `hip_flat`, `thigh_flat`, `inseam`, `outseam`, `front_rise`, `back_rise`, `leg_opening`, `neck`, `unknown`.

## Evaluation

The results CSV includes the model's measurement, tape-detection correctness, type correctness, absolute numeric error in **cm** (unit-normalized), confidence, visual evidence, token usage, and errors. Calculate rates only over rows with manual labels. Inspect every failure and uncertain prediction; model-reported confidence is not a calibrated probability.

Each API call sends an image to DeepSeek and may incur charges. The harness processes cases sequentially, with `--limit` for a small trial. It only downloads HTTPS images from the eBay image host, rejects unexpected content types, and caps downloads at 8 MiB. Do not use private or sensitive images.

## Known limitations

- One image per case; **multi-image and seller-description cross-checking are future work**.
- A tape reading is not automatically a reliable garment size: endpoints, stretch, and flat-versus-circumference semantics matter.
- No automatic filtering or deletion of listings.
- No live DeepSeek call is made in the repository itself; run the experiment locally with your key.
