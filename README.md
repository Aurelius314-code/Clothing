# Vintage Wardrobe Watcher v0.5 – Windows / PyCharm

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
- The app converts everything to cm, with widths stored flat, and shows it on the listing in **Annonser**, next to the photos. Uncertain readings are marked so you know which photo to check.

Each run analyses at most 100 listings, newest first (`--analyze-limit 200` to change it). Listings already analysed are not sent again, rejected listings are skipped, and accessories, shoes and basics are left out because they are bought by size. A failed analysis is shown in the app and retried on the next run, up to 3 times. A wrong key or an empty DeepSeek balance stops the analysis with a message.

To try the reading on a single listing or photo without saving anything:

```powershell
python test_one.py https://www.ebay.co.uk/itm/123456789012 trousers
python check.py                                     # how many listings are analysed, latest readings and errors
```

## Upgrading
1. Close the program and **back up `wardrobe.sqlite3`**.
2. In PyCharm, **Git → Pull**, then run `python -m pip install -r requirements.txt`.
3. Keep your own `wardrobe.json`, `wardrobe.sqlite3` and `.env`. New tables are added on first start; nothing is removed.

From v0.3, the first start also fixes the wardrobe targets of the two seeded pleated trousers (assign them in the garment register), re-keys hand-entered eBay listings to their item number, and moves listing notes to the reviews.

From the first DeepSeek version: its readings were lists of numbers from the tape without saying what was measured, so they are not carried over. Run `python watcher.py --report-only --analyze-images` to read those listings again.

## Features
- Wardrobe targets and owned counts editable in the browser.
- Separate physical-garment register, including fit problems and a wardrobe target you can change.
- Manual entry for listings. eBay links, including share links from the eBay app (`ebay.us/…`, `ebay.io/…`), are recognised by item number, so the same listing updates one record and merges with the API record for it. New notes are added under earlier ones with the date.
- Listing reviews with paging (50 per page) that stays on the same page after a review, and possible relisting warnings based on seller + normalized title.
- eBay API search that only returns sellers who ship to `EBAY_SHIP_TO_COUNTRY`, stores the cheapest shipping quote, and keeps auction bid changes out of the price history.
- Measurements read from listing photos and text by DeepSeek, shown in the app and in `report.html`.

## Important limitations
- Reading a tape in a photo can go wrong when the photo is blurry, angled or the tape doesn't start at the garment's edge. Check the photo behind the measurements that matter before buying, especially readings marked uncertain.
- The app does not yet compare readings with your own measurements.
- Non-eBay links are matched on the exact URL. eBay listings with size or colour variations can still appear twice. Relisting flags are only heuristic.
- `owned_quantity` in the wardrobe plan and the separate garment register are intentionally separate; update the plan count yourself when adding a garment.
- Shipping is stored, but landed Norwegian costs (VAT, duty, currency) are not calculated yet.
