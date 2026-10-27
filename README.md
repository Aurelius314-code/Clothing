# Vintage Wardrobe Watcher v0.7 – Windows / PyCharm

## Install
Open the folder in PyCharm. In the PyCharm terminal with the project interpreter active:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit normally opens http://localhost:8501 in your browser. Press Ctrl+C in the terminal to stop it.

Copy `.env.example` to `.env` and fill in your eBay keys, plus `DEEPSEEK_API_KEY` if you want measurements read from listing photos. Never share `.env`.

## Searching eBay and reading measurements

```powershell
python watcher.py                                   # search eBay, then write report.html
python watcher.py --analyze-images                  # search, then read measurements from new listings
python watcher.py --report-only --analyze-images    # read measurements only, no new search
```

With `--analyze-images`, each listing found for a jacket, coat, trousers, knitwear or shirt is read once by DeepSeek:

- The app fetches the full listing from eBay: every photo at full size, the description and the item specifics.
- DeepSeek reads the measurements for that type of garment (for example pit to pit, shoulders, sleeve and back length for a jacket), from the tape photos and the text. For each one it says which photo it came from, whether it was measured flat or all the way round, and how sure it is.
- DeepSeek also says, for each photo reading, whether both ends of the tape and the scale are clearly visible. Readings where they aren't are marked uncertain. Set `STRICT_PHOTO_EVIDENCE=1` in `.env` to drop them instead.
- The app converts everything to cm, with widths stored flat, and shows it on the listing in **Annonser**, next to the photos, with where it came from: *AI-estimat* (read from a photo) or *Oppgitt av selger* (from the text). Neither is verified, and uncertain readings are marked so you know which photo to check.

Each run analyses at most 100 listings, newest first (`--analyze-limit 200` to change it). Listings already analysed are not sent again, rejected listings are skipped, and accessories, shoes and basics are left out because they are bought by size. A failed analysis is shown in the app and retried on the next run, up to 3 times. A wrong key or an empty DeepSeek balance stops the analysis with a message.

## Traffic light

Under **📐 Mine mål**, enter a range for each measurement you care about, per type of garment (jackets, coats, waistcoats, trousers, knitwear, shirts). Use flat measurements in cm from the measuring sheet, for example 1–2 cm either side of a garment that fits you. Leave a field empty to not judge that measurement.

Each listing in **🔎 Annonser** then gets a colour, with the reason:

- 🟢 **Passer**: every judged measurement is inside your range, and the key ones are known (for example pit to pit and shoulders for jackets, waist and front rise for trousers).
- 🟡 **Kanskje**: something a tailor can usually fix (a waist that can be taken in, sleeves that can be shortened), a measurement just outside your range, a key measurement missing, or an uncertain reading to check in the photo.
- 🔴 **Passer ikke**: a measurement clearly outside your range that can't be fixed, such as shoulders, rise or knitwear.
- ⚪ **Ukjent**: not analysed yet, no measurements shown, no targets set, or bought by size.

Red listings are hidden by default; choose them in the Trafikklys filter to see them, and sort by *Beste treff først* to see green first. An uncertain reading never makes a listing red. The rules of thumb for what can be altered, and by how much, are in `fit.py`.

To try the reading on a single listing or photo without saving anything:

```powershell
python test_one.py https://www.ebay.co.uk/itm/123456789012 trousers
python check.py                                     # how many listings are analysed, latest readings and errors
```

## Checking how good the readings are

The `eval` folder has a benchmark that scores DeepSeek's readings against photos you have measured yourself, and can compare the strict and lenient settings. In a first test on two real listings, a second, blinded look at the same photos could not confirm any of the four readings, so treat them as unverified until the benchmark has been run. See `eval/README.md`.

```powershell
python -m pytest -q tests eval/tests                 # offline tests, no API key needed
```

## Upgrading
1. Close the program and **back up `wardrobe.sqlite3`**.
2. In PyCharm, **Git → Pull**, then run `python -m pip install -r requirements.txt`.
3. Keep your own `wardrobe.json`, `wardrobe.sqlite3` and `.env`. New tables are added on first start; nothing is removed.
4. From v0.5: coats and outerwear now have their own targets, separate from jackets, because they are worn over a jacket.
5. From v0.6: readings already stored are labelled *Eldre måling* (older reading); new analyses get the new labels.

From v0.3, the first start also fixes the wardrobe targets of the two seeded pleated trousers (assign them in the garment register), re-keys hand-entered eBay listings to their item number, and moves listing notes to the reviews.

From the first DeepSeek version: its readings were lists of numbers from the tape without saying what was measured, so they are not carried over. Run `python watcher.py --report-only --analyze-images` to read those listings again.

## Features
- Wardrobe targets and owned counts editable in the browser.
- Separate physical-garment register, including fit problems and a wardrobe target you can change.
- Manual entry for listings. eBay links, including share links from the eBay app (`ebay.us/…`, `ebay.io/…`), are recognised by item number, so the same listing updates one record and merges with the API record for it. New notes are added under earlier ones with the date.
- Listing reviews with paging (50 per page) that stays on the same page after a review, and possible relisting warnings based on seller + normalized title.
- eBay API search that only returns sellers who ship to `EBAY_SHIP_TO_COUNTRY`, stores the cheapest shipping quote, and keeps auction bid changes out of the price history.
- Measurements read from listing photos and text by DeepSeek, shown in the app and in `report.html`.
- Traffic light per listing against your own target ranges, with filtering and sorting by colour.
- A benchmark and diagnostics for the photo reading in `eval/`.

## Important limitations
- Reading a tape in a photo can go wrong when the photo is blurry, angled or the tape doesn't start at the garment's edge. Check the photo behind the measurements that matter before buying, especially readings marked uncertain.
- The alteration rules in `fit.py` are rules of thumb. What a tailor can do depends on the garment, so treat yellow as "worth a closer look".
- `report.html` shows the readings but not the traffic light; use the app for that.
- Non-eBay links are matched on the exact URL. eBay listings with size or colour variations can still appear twice. Relisting flags are only heuristic.
- `owned_quantity` in the wardrobe plan and the separate garment register are intentionally separate; update the plan count yourself when adding a garment.
- Shipping is stored, but landed Norwegian costs (VAT, duty, currency) are not calculated yet.
