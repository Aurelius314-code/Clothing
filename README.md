# Vintage Wardrobe Watcher v0.8 – Windows / PyCharm

## Install
Open the folder in PyCharm. In the PyCharm terminal with the project interpreter active:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit normally opens http://localhost:8501 in your browser. Press Ctrl+C in the terminal to stop it.

Copy `.env.example` to `.env` and fill in your eBay keys and/or Tradera keys, plus `DEEPSEEK_API_KEY` if you want measurements read from listing photos. Never share `.env`.

## Searching eBay and Tradera, and reading measurements

```powershell
python watcher.py                                   # search eBay and Tradera, then write report.html
python watcher.py --source tradera                  # search only Tradera (or --source ebay)
python watcher.py --only W044 --limit-per-query 20  # search only some targets (IDs or categories such as Knitwear)
python watcher.py --analyze-images                  # search, then read measurements from new listings
python watcher.py --report-only --analyze-images    # read measurements only, no new search
```

With `--analyze-images`, each listing found for a jacket, coat, trousers, knitwear or shirt is read once by DeepSeek:

- The app fetches the full listing from eBay or Tradera: every photo at full size, the description and the item specifics.
- DeepSeek reads the measurements for that type of garment (for example pit to pit, shoulders, sleeve and back length for a jacket), from the tape photos and the text. For each one it says which photo it came from, whether it was measured flat or all the way round, and how sure it is.
- DeepSeek also says, for each photo reading, whether both ends of the tape and the scale are clearly visible. Readings where they aren't are marked uncertain. Set `STRICT_PHOTO_EVIDENCE=1` in `.env` to drop them instead.
- The app converts everything to cm, with widths stored flat, and shows it on the listing in **Annonser**, next to the photos, with where it came from: *AI-estimat* (read from a photo) or *Oppgitt av selger* (from the text). Neither is verified, and uncertain readings are marked so you know which photo to check.
- In the same request DeepSeek reads the fabric composition: from care and composition labels in the photos, and from the item specifics and description ("Material: Polyester"). Only the outer fabric counts; a polyester lining is fine. Each listing gets one of 🟢 *Naturfiber*, 🟡 *Med viskose e.l.*, 🔴 *Syntetisk* (any polyester, nylon, acrylic, elastane … in the outer fabric) or ⚪ *Stoff ukjent – sjekk lappen*. **Annonser** hides synthetic listings by default; change the *Stoff* filter to see them.
- The seller's description and item specifics are saved with the analysis; **Vis selgerens beskrivelse** on the listing shows them.

Each run analyses at most 100 listings, newest first (`--analyze-limit 200` to change it). Listings already analysed are not sent again (except once more for the fabric, if they were analysed before fabric reading was added), rejected listings are skipped, and accessories, shoes and basics are left out because they are bought by size. A failed analysis is shown in the app and retried on the next run, up to 3 times. A wrong key or an empty DeepSeek balance stops the analysis with a message.

`--only` narrows a search to some wardrobe targets, by ID (`W044`) or by category (`Knitwear`), comma-separated. A category searches the targets in it that you still want; a target named by ID is searched even if you already own enough of it, so you can look for one more without changing the plan.

Blazer and sport coat searches also bring back coats. Before a result is stored under a jacket target, its title is checked (`garment_route.py`): duffle coats go to the duffle target, trench coats and raincoats to the raincoat target, overcoats to the overcoat target and waxed jackets to the waxed jacket target. Other outerwear (parkas, pea coats, field and utility jackets, cardigans, Swedish *jacka* and *kappa*) is left out unless the title also says blazer, sport coat or *kavaj*. Listings stored before this was added were sorted the same way once; those with no coat target were marked rejected. **Annonser** can be filtered by wardrobe target, and each listing shows which target it belongs to.

## Tradera

Tradera is searched as well when `TRADERA_APP_ID` and `TRADERA_APP_KEY` are in `.env`. Both are free: make a developer account at https://api.tradera.com/register and create an application there. Tradera allows 10,000 calls a day per method, which is far more than one run uses.

- **Search words** are Swedish and live in `tradera.json`, per wardrobe ID (for example `"W005": ["harris tweed kavaj", "tweedkavaj herr"]`). A wardrobe target without Swedish words is searched with its English words from `wardrobe.json`. When you add a target to the plan, add Swedish words for it here too.
- **Categories:** clothes are searched in *Herrkläder* (302074); shoes, accessories and basics in all categories. Change this under `categories` in `tradera.json`.
- **Prices** are in SEK. Auctions show the current bid, or the next bid if nobody has bid yet. The search filters under **⚙️ Søkefiltre** apply too, but a price limit in GBP doesn't stop SEK listings.
- **Shipping:** Tradera's API only gives the price within Sweden, and a seller can choose to ship only within Sweden. The app doesn't show a shipping price for Tradera listings, so check on the listing that the seller ships to Norway and what it costs. Norwegian import VAT and the carrier's customs handling fee can come on top.
- Tradera listings are analysed by DeepSeek like eBay listings, with Swedish measurement words (axelbredd, ärmlängd, midja, grenhöjd, innerbenslängd …) explained in the prompt.
- Tradera links work in **➕ Legg til annonse** and in `test_one.py`.

Tradera's REST API is still in beta, and its search reply isn't fully documented, so try it once with your keys before the first full run:

```powershell
python tradera.py "harris tweed kavaj"                                   # 5 results in Herrkläder and in all categories
python tradera.py https://www.tradera.com/item/1640/654970712/gant-ullkavaj   # one listing, as the app will store it
```

If it prints *unexpected search reply*, the field names it lists show what Tradera sent, and the parsing in `tradera.py` needs updating to match.

## A Swedish address

If you can receive parcels in Sweden (a pickup point, parcel locker or parcel holding service), set `SWEDISH_PICKUP=1` in `.env`. Then:

- **eBay** is searched a second time for sellers who ship to Sweden, on eBay Germany by default (`EBAY_SWEDEN_MARKETPLACE_ID`, for example `EBAY_NL` or `EBAY_FR`). That finds EU sellers who don't ship to Norway. Their prices are in that site's currency, and the shipping shown is to Sweden. A listing that also ships to Norway stays a Norway listing, with its Norwegian price and shipping.
- **Tradera** listings count as going to your Swedish address, so sellers who only ship within Sweden are fine. The Swedish shipping price is looked up from each new listing's full page, up to 200 per run (`--tradera-shipping-limit`); the rest follow on later runs.
- In **🔎 Annonser**, these listings are marked 📦 **Til Sverige-adressen**, and the *Levering* filter shows only them, or only listings that ship to Norway.

Search words are the same English ones as for eBay UK. Brand names (Barbour, Harris Tweed, Tricker's) work on every eBay site; add German words to `search_terms` in `wardrobe.json` if you want more from eBay Germany.

## Traffic light

Under **📐 Mine mål**, enter a range for each measurement you care about, per type of garment (jackets, coats, waistcoats, trousers, knitwear, shirts). Use flat measurements in cm from the measuring sheet, for example 1–2 cm either side of a garment that fits you. Leave a field empty to not judge that measurement.

Each listing in **🔎 Annonser** then gets a colour, with the reason:

- 🟢 **Passer**: every judged measurement is inside your range, and the key ones are known (for example pit to pit and shoulders for jackets, waist and front rise for trousers).
- 🟡 **Kanskje**: something a tailor can usually fix (a waist that can be taken in, sleeves that can be shortened), a measurement just outside your range, a key measurement missing, or an uncertain reading to check in the photo.
- 🔴 **Passer ikke**: a measurement clearly outside your range that can't be fixed, such as shoulders, rise or knitwear.
- ⚪ **Ukjent**: not analysed yet, no measurements shown, no targets set, bought by size, or measurements you haven't checked yet.

Only measurements you have checked yourself count. Under each listing, open **✔️ Kontroller mål**, compare each number with the photo or the text, and tick *Kontrollert* for the ones that are right. Correct a wrong number, empty a field to remove a wrong reading, or fill in a measurement the analysis missed; corrected and new numbers are saved as checked. Until then the listing stays ⚪, but the reason shows what it would get (for example *foreløpig 🟢*), so you can see which listings are worth checking. Checked measurements are kept if the listing is analysed again.

Red listings are hidden by default; choose them in the Trafikklys filter to see them, and sort by *Beste treff først* to see green first. An uncertain reading never makes a listing red. The rules of thumb for what can be altered, and by how much, are in `fit.py`.

To try the reading on a single listing or photo without saving anything:

```powershell
python test_one.py https://www.ebay.co.uk/itm/123456789012 trousers
python test_one.py https://www.tradera.com/item/1640/654970712/gant-ullkavaj jacket
python check.py                                     # how many listings are analysed, latest readings and errors
```

## Checking how good the readings are

The `eval` folder has a benchmark that scores DeepSeek's readings against photos you have measured yourself, and can compare the strict and lenient settings. In a first test on two real listings, a second, blinded look at the same photos could not confirm any of the four readings, so treat them as unverified until the benchmark has been run. See `eval/README.md`.

```powershell
python -m pytest -q tests eval/tests                 # offline tests, no API key needed
```

## Backups

The first time the app or `watcher.py` opens the database each day, a checked copy is saved in `backups/`. The program keeps 14 daily, 8 weekly and 6 monthly copies. Under **📏 Passform og historikk** you can make a copy now, download one, or restore one; the database as it was is saved as a copy first. The copies are on the same disk, so keep an extra one elsewhere now and then (for example in OneDrive).

If a copy can't be made, the app shows a warning and works as before. If the app can't open the database at all, close it and `watcher.py`, then restore from the terminal:

```powershell
python db_backup.py list
python db_backup.py restore wardrobe_20261102_204208_603552.sqlite3
```

## Upgrading
1. Close the program and **back up `wardrobe.sqlite3`**.
2. In PyCharm, **Git → Pull**, then run `python -m pip install -r requirements.txt`.
3. Keep your own `wardrobe.json`, `wardrobe.sqlite3` and `.env`. New tables are added on first start; nothing is removed.
4. From v0.5: coats and outerwear now have their own targets, separate from jackets, because they are worn over a jacket.
5. From v0.6: readings already stored are labelled *Eldre måling* (older reading); new analyses get the new labels.
6. From v0.8: only measurements you have checked under **✔️ Kontroller mål** give a colour, so listings are ⚪ until you check them. Add `TRADERA_APP_ID` and `TRADERA_APP_KEY` to `.env` to search Tradera as well (see `.env.example`). Tradera listings imported in the 🌍 tab before v0.8 get their Tradera item number on the first start, so they merge with the same listing from the search. Auctions now show the opening bid when nobody has bid, and both prices when a listing also has a buy-now price.

From v0.3, the first start also fixes the wardrobe targets of the two seeded pleated trousers (assign them in the garment register), re-keys hand-entered eBay listings to their item number, and moves listing notes to the reviews.

From the first DeepSeek version: its readings were lists of numbers from the tape without saying what was measured, so they are not carried over. Run `python watcher.py --report-only --analyze-images` to read those listings again.

## Features
- Wardrobe plan grouped by main category under **🧥 Garderobe** (Yttertøy, Bukser, Strikk …), in the order set under 🏷️ Gruppeprioritet. Each category opens to a table where owned and wanted counts, priority and search can be edited.
- Wardrobe principles (`principles` in `wardrobe.json`) shown under **🏠 Oversikt**.
- Separate physical-garment register, including fit problems and a wardrobe target you can change.
- Manual entry for listings. eBay links, including share links from the eBay app (`ebay.us/…`, `ebay.io/…`), are recognised by item number, so the same listing updates one record and merges with the API record for it. New notes are added under earlier ones with the date.
- Listing reviews with paging (50 per page) that stays on the same page after a review, and possible relisting warnings based on seller + normalized title.
- eBay API search that only returns sellers who ship to `EBAY_SHIP_TO_COUNTRY`, stores the cheapest shipping quote, and keeps auction bid changes out of the price history.
- Tradera API search with Swedish search words per wardrobe target (`tradera.json`).
- Optional Swedish address (`SWEDISH_PICKUP=1`): an extra eBay search for sellers who ship to Sweden, Swedish shipping on Tradera, and a delivery filter.
- Measurements and fabric composition read from listing photos, labels and text by DeepSeek, shown in the app and in `report.html`; synthetic outer fabrics hidden by default.
- Traffic light per listing against your own target ranges, based on measurements you have checked, with filtering and sorting by colour.
- A benchmark and diagnostics for the photo reading in `eval/`.

## Important limitations
- Reading a tape in a photo can go wrong when the photo is blurry, angled or the tape doesn't start at the garment's edge. Check the photo behind the measurements that matter before buying, especially readings marked uncertain.
- The alteration rules in `fit.py` are rules of thumb. What a tailor can do depends on the garment, so treat yellow as "worth a closer look".
- `report.html` shows the readings but not the traffic light; use the app for that.
- Non-eBay links are matched on the exact URL. eBay listings with size or colour variations can still appear twice. Relisting flags are only heuristic.
- `owned_quantity` in the wardrobe plan and the separate garment register are intentionally separate; update the plan count yourself when adding a garment.
- Shipping is stored, but landed Norwegian costs (VAT, duty, currency) are not calculated yet.
