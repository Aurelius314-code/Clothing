# First two eBay measurement benchmark candidates

The candidate listings have seller descriptions referring to measurement photographs:

1. [Cordings of Piccadilly green tweed jacket](https://www.ebay.co.uk/itm/800346841273), item ID `800346841273`. Seller says the first measuring-stick photo is length and the second is pit-to-pit. **This listing has sold**, so the Browse API may not return its full image gallery.
2. [Burberry London beige pleated trousers](https://www.ebay.co.uk/itm/168178929667), item ID `168178929667`. Seller says measurement photos were taken with the trousers laid flat.

Neither listing has independently verified tape readings yet. Seller size fields (such as W34 or 31-inch inseam) are **not** automatically valid tape-photo ground truth.

## Retrieve candidate photographs with your existing eBay credentials

```powershell
python prepare_measurement_cases.py
```

This fetches full listing details via `watcher.get_item`, gathers photos with `measure.photos_from_item`, and writes `measurement_cases.csv` **only if it does not already exist**. It never changes the SQLite database, calls DeepSeek or supplies guessed measurements.

Inspect the images and manually replace the `[]` in `expected_measurements` with confirmed flat-width/length values in centimetres, for example `[{"name":"pit_to_pit","value_cm":55.9}]`. If you cannot verify an image, exclude the case rather than leaving `[]` (which means verified absence of measurements).

Then run:

```powershell
python evaluate_measurements.py --dry-run
python evaluate_measurements.py --limit 1
```

**Caution:** The dry-run validates structure, not whether the reference measurements were independently verified. Only run the live evaluation after reviewing the labels.
