# Vintage Wardrobe Watcher v0.4 – Windows / PyCharm

## Install
Open the folder in PyCharm. In the PyCharm terminal with the project interpreter active:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit normally opens http://localhost:8501 in your browser. Press Ctrl+C in the terminal to stop it.

## Upgrading from v0.3: keep your data
1. Close the program and **back up your project directory**, including `wardrobe.sqlite3`.
2. Replace `app.py`, `watcher.py`, `requirements.txt` and `README.md` with the v0.4 files. Keep your own `wardrobe.json`, `wardrobe.sqlite3` and `.env`.
3. Run `python -m pip install -r requirements.txt` again (v0.4 needs Streamlit 1.50 or newer).
4. On first start, v0.4 updates the database once:
   - The two pleated trousers that v0.3 seeded under *Mid-grey flannel trousers* (W009) and *Charcoal flannel trousers* (W010) become unassigned. Assign them to the right target in the garment register.
   - Listings you entered by hand from eBay are re-keyed to their eBay item number. If the same listing was entered twice with different links, the second copy is left as it is; reject or ignore it.
   - Notes stored on listings are copied to the listing reviews.
5. Consider changing `EBAY_MARKETPLACE_ID` in your `.env` to `EBAY_GB` (the new default in `.env.example`), since most of the wardrobe is British.

## Features
- Wardrobe targets and owned counts editable in the browser.
- Separate physical-garment register, including fit problems and a wardrobe target you can change.
- Manual URL entry for listings. eBay links are recognised by item number, so the same listing updates one record regardless of tracking parameters, and merges with the API record for it.
- Listing reviews with paging (50 per page), and possible relisting warnings based on seller + normalized title.
- Command-line eBay API search (`watcher.py`) that only returns sellers who ship to `EBAY_SHIP_TO_COUNTRY`, stores the cheapest shipping quote, and keeps auction bid changes out of the price history.

## Important limitations
- Manual URL entry does **not** scrape eBay. Enter the title, price, and image URL yourself.
- Non-eBay links are matched on the exact URL. eBay listings with size or colour variations can still appear twice. Relisting flags are only heuristic.
- No automatic eBay access without approved API credentials.
- `owned_quantity` in the wardrobe plan and the separate garment register are intentionally separate; update the plan count yourself when adding a garment.
- Shipping is stored, but this version does not yet calculate landed Norwegian costs (VAT, duty, currency) or verify garment measurements.
