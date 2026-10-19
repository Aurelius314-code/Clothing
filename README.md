# Vintage Wardrobe Watcher v0.3 – Windows / PyCharm

## Install
Open the folder in PyCharm. In the PyCharm terminal with the project interpreter active:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit normally opens http://localhost:8501 in your browser. Press Ctrl+C in the terminal to stop it.

## Existing v0.2 users: keep your data
1. Close the old program and any new Streamlit window.
2. **Back up your existing v0.2 project directory** before changing files.
3. Copy your existing `wardrobe.sqlite3` into this v0.3 directory (if it exists). The new UI uses the same existing listing tables and adds `owned_garments`. On first run with an empty owned-garments register it prepopulates your three known garments; review their category assignments.
4. Your existing `wardrobe.json` may be copied over if you edited it, but it will overwrite the v0.3 default owned count for the British Warm. If you have custom changes, merge carefully instead.
5. If you already configured an `.env`, copy it locally; never share your API secrets.

## Features
- Wardrobe targets and owned counts editable in the browser.
- Separate physical-garment register, including fit problems.
- Manual URL entry for listings, with updates to existing URL and price history.
- Listing reviews, possible relisting warnings based on seller + normalized title.
- Retains original `watcher.py` command-line eBay API search workflow.

## Important limitations
- Manual URL entry does **not** scrape eBay. Enter the title, price, and image URL yourself.
- Duplicate detection for manually entered ads uses the exact URL; URL variants can still duplicate. eBay API records use eBay item IDs. Relisting flags are only heuristic.
- No automatic eBay access without approved API credentials.
- `owned_quantity` in the wardrobe plan and the separate garment register are intentionally separate; update the plan count yourself when adding a garment.
- This version does not yet calculate landed Norwegian costs or verify garment measurements.
