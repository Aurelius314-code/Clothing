"""Vintage Wardrobe Watcher - eBay Browse API search, SQLite archive and HTML report."""
import argparse
import base64
import hashlib
import html
import json
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from dotenv import load_dotenv

import measure
import search_prefilter
import group_priority

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'wardrobe.sqlite3'
CATALOG = ROOT / 'wardrobe.json'
REVIEW_STATUSES = ('unreviewed', 'saved', 'rejected', 'purchased')
MAX_ATTEMPTS = 3  # a listing whose analysis keeps failing is given up after this many tries
SHORT_LINK_HOSTS = {'ebay.us', 'ebay.io'}  # share links from the eBay app, without the item number
# Matches both https://www.ebay.co.uk/itm/123456789012 and the older
# https://www.ebay.com/itm/Some-Title-Words/123456789012 form, ignoring tracking parameters.
EBAY_ITEM_URL = re.compile(r'ebay\.[a-z.]+/itm/(?:[^/?#]+/)?(\d{9,15})(?!\d)', re.IGNORECASE)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ebay_item_key(url):
    """Item ID in the Browse API's own format ('v1|<item number>|0') for an eBay listing URL, else None.

    Using the API's format means a listing added by hand and the same listing found later
    by the API search end up as one record. (Listings with size/colour variations get a
    different suffix from the API, so those can still appear twice.)
    """
    match = EBAY_ITEM_URL.search(url or '')
    return f'v1|{match.group(1)}|0' if match else None


def resolve_ebay_url(url):
    """Follow an eBay share link (ebay.us/..., ebay.io/...) to the listing it points to.

    Other addresses are returned unchanged. Raises requests.RequestException if the link can't be followed.
    """
    host = urlparse(url).netloc.lower().removeprefix('www.')
    if host not in SHORT_LINK_HOSTS:
        return url
    r = requests.get(url, headers=measure.BROWSER_HEADERS, allow_redirects=True, timeout=15, stream=True)
    r.close()
    for candidate in [r.url] + [hop.headers.get('Location', '') for hop in r.history]:
        if ebay_item_key(candidate):
            return candidate
    return r.url


def has_flag(conn, key):
    return conn.execute('SELECT 1 FROM meta WHERE key=?', (key,)).fetchone() is not None


def set_flag(conn, key):
    conn.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (key, utc_now()))


def _add_column(conn, table, column, declaration):
    if column not in {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')


def _migrate_v04(conn):
    """One-time fixes for databases made by v0.3. Runs once per database file."""
    if has_flag(conn, 'migrated_v0.4'):
        return
    # v0.3 seeded these two trousers under W009/W010, which are the flannel trousers in wardrobe.json.
    conn.execute('''UPDATE owned_garments SET wardrobe_id=NULL WHERE
        (wardrobe_id='W009' AND name='High-waisted pleated chinos') OR
        (wardrobe_id='W010' AND name='Second high-waisted pleated trousers')''')
    # A register that already has garments counts as seeded, so deleting them never re-seeds.
    if conn.execute('SELECT COUNT(*) FROM owned_garments').fetchone()[0]:
        set_flag(conn, 'garments_seeded')
    # Listing notes now live only in listing_reviews.
    conn.execute("""INSERT OR IGNORE INTO listing_reviews(item_id,status,notes)
        SELECT item_id, COALESCE(NULLIF(status,''),'unreviewed'), notes FROM listings
        WHERE COALESCE(notes,'') != ''""")
    # Manually entered eBay listings are re-keyed to their eBay item number.
    manual = conn.execute("SELECT item_id,url FROM listings WHERE item_id LIKE 'manual:%'").fetchall()
    for old_key, url in manual:
        new_key = ebay_item_key(url)
        if not new_key or conn.execute('SELECT 1 FROM listings WHERE item_id=?', (new_key,)).fetchone():
            continue  # not an eBay URL, or a record for that item exists already: leave it alone
        for table in ('listings', 'price_history', 'matches', 'listing_reviews'):
            conn.execute(f'UPDATE {table} SET item_id=? WHERE item_id=?', (new_key, old_key))
    set_flag(conn, 'migrated_v0.4')


def connect():
    conn = sqlite3.connect(DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS listings (
        item_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT, image_url TEXT,
        seller TEXT, price REAL, currency TEXT, first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL, fingerprint TEXT, notes TEXT DEFAULT '',
        status TEXT DEFAULT 'unreviewed')''')  # notes/status are legacy; reviews live in listing_reviews
    _add_column(conn, 'listings', 'buying_options', "TEXT DEFAULT ''")
    _add_column(conn, 'listings', 'shipping_cost', 'REAL')
    _add_column(conn, 'listings', 'shipping_currency', "TEXT DEFAULT ''")
    conn.execute('''CREATE TABLE IF NOT EXISTS price_history (
        item_id TEXT NOT NULL, observed_at TEXT NOT NULL, price REAL,
        currency TEXT, PRIMARY KEY(item_id, observed_at))''')
    conn.execute('CREATE INDEX IF NOT EXISTS ix_fingerprint ON listings(fingerprint)')
    conn.execute('''CREATE TABLE IF NOT EXISTS matches (
        item_id TEXT NOT NULL, wardrobe_id TEXT NOT NULL,
        PRIMARY KEY(item_id,wardrobe_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS listing_reviews (
        item_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'unreviewed',
        notes TEXT DEFAULT '')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS owned_garments (
        garment_id INTEGER PRIMARY KEY AUTOINCREMENT, wardrobe_id TEXT, name TEXT NOT NULL,
        brand TEXT DEFAULT '', size TEXT DEFAULT '', fit TEXT DEFAULT 'good',
        notes TEXT DEFAULT '', image_url TEXT DEFAULT '', created_at TEXT NOT NULL)''')
    conn.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
    # Photo reading. (Databases from the first DeepSeek version also have a listings.measurements
    # column; it is no longer used.)
    conn.execute('''CREATE TABLE IF NOT EXISTS listing_photos (
        item_id TEXT NOT NULL, position INTEGER NOT NULL, url TEXT NOT NULL,
        PRIMARY KEY(item_id, position))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS listing_analysis (
        item_id TEXT PRIMARY KEY, status TEXT NOT NULL, analyzed_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, photo_count INTEGER DEFAULT 0, model TEXT DEFAULT '',
        error TEXT DEFAULT '', raw TEXT DEFAULT '')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS listing_measurements (
        item_id TEXT NOT NULL, name TEXT NOT NULL, value_cm REAL NOT NULL, raw_value REAL, raw_unit TEXT,
        flat INTEGER, source TEXT, confidence TEXT, note TEXT DEFAULT '',
        PRIMARY KEY(item_id, name))''')
    # Your own target ranges for the traffic light, in cm with widths flat.
    conn.execute('''CREATE TABLE IF NOT EXISTS fit_targets (
        garment_type TEXT NOT NULL, name TEXT NOT NULL, min_cm REAL, max_cm REAL,
        PRIMARY KEY(garment_type, name))''')
    _add_column(conn, 'listing_measurements', 'verification_status', "TEXT NOT NULL DEFAULT 'legacy_unverified'")
    _migrate_v04(conn)
    conn.commit()
    return conn


def token():
    client = os.environ.get('EBAY_CLIENT_ID')
    secret = os.environ.get('EBAY_CLIENT_SECRET')
    if not client or not secret:
        raise RuntimeError('Fill in EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env')
    credentials = base64.b64encode(f'{client}:{secret}'.encode()).decode()
    r = requests.post('https://api.ebay.com/identity/v1/oauth2/token',
                      headers={'Authorization': f'Basic {credentials}', 'Content-Type': 'application/x-www-form-urlencoded'},
                      data={'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'}, timeout=30)
    r.raise_for_status()
    return r.json()['access_token']


def _ship_to_country():
    country = os.getenv('EBAY_SHIP_TO_COUNTRY', 'NO').strip().upper()
    if not re.fullmatch(r'[A-Z]{2}', country):
        raise RuntimeError('EBAY_SHIP_TO_COUNTRY must be a two-letter country code, for example NO')
    return country


def _ebay_headers(access_token):
    return {'Authorization': f'Bearer {access_token}', 'X-EBAY-C-MARKETPLACE-ID': os.getenv('EBAY_MARKETPLACE_ID', 'EBAY_GB'),
            'X-EBAY-C-ENDUSERCTX': f'contextualLocation=country%3D{_ship_to_country()}'}


def get_item(item_id, access_token):
    """The full listing: every photo, the description and the item specifics."""
    r = requests.get(f'https://api.ebay.com/buy/browse/v1/item/{quote(item_id, safe="")}',
                     headers=_ebay_headers(access_token), timeout=45)
    r.raise_for_status()
    return r.json()


def fetch(query, access_token, limit=100, filters=None):
    country = _ship_to_country()
    headers = _ebay_headers(access_token)
    for offset in range(0, limit, 200):
        # deliveryCountry limits results to sellers who will ship to that country.
        params = {'q': query, 'limit': min(200, limit - offset), 'offset': offset,
                  'filter': filters or f'deliveryCountry:{country}'}
        r = requests.get('https://api.ebay.com/buy/browse/v1/item_summary/search', headers=headers, params=params, timeout=45)
        r.raise_for_status()
        items = r.json().get('itemSummaries', [])
        yield from items
        if len(items) < params['limit']:
            break


def fingerprint(title, seller):
    normalized = re.sub(r'[^a-z0-9]+', ' ', (title or '').lower()).strip()
    return hashlib.sha256(f'{(seller or "").lower()}|{normalized}'.encode()).hexdigest()


def is_auction_only(buying_options):
    options = set((buying_options or '').split(','))
    return 'AUCTION' in options and 'FIXED_PRICE' not in options


def _money(data):
    try:
        return float(data['value']), data.get('currency', '')
    except (KeyError, TypeError, ValueError):
        return None, ''


def _cheapest_shipping(item):
    """Cheapest shipping quote eBay gives for the buyer's country, or (None, '') if there is none."""
    quotes = [_money(option.get('shippingCost')) for option in item.get('shippingOptions') or []]
    quotes = [quote for quote in quotes if quote[0] is not None]
    return min(quotes) if quotes else (None, '')


def store_photos(conn, item_id, photos):
    if photos:
        conn.execute('DELETE FROM listing_photos WHERE item_id=?', (item_id,))
        conn.executemany('INSERT INTO listing_photos(item_id,position,url) VALUES(?,?,?)',
                         [(item_id, n, url) for n, url in enumerate(photos, 1)])


def listing_photos(conn, item_id):
    return [url for (url,) in conn.execute('SELECT url FROM listing_photos WHERE item_id=? ORDER BY position', (item_id,))]


def ingest(conn, item, wardrobe_id=None):
    item_id = item.get('itemId')
    if not item_id:
        return 'skipped'
    now = utc_now()
    title = item.get('title', '')
    seller = (item.get('seller') or {}).get('username', '')
    price, currency = _money(item.get('price') or item.get('currentBidPrice'))
    shipping_cost, shipping_currency = _cheapest_shipping(item)
    buying_options = ','.join(item.get('buyingOptions') or [])
    image_url = (item.get('image') or {}).get('imageUrl', '')
    old = conn.execute('SELECT price,currency FROM listings WHERE item_id=?', (item_id,)).fetchone()
    conn.execute('''INSERT INTO listings(item_id,title,url,image_url,seller,price,currency,first_seen,last_seen,
        fingerprint,buying_options,shipping_cost,shipping_currency)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET
        title=excluded.title,url=excluded.url,image_url=excluded.image_url,
        seller=excluded.seller,price=excluded.price,currency=excluded.currency,
        last_seen=excluded.last_seen,fingerprint=excluded.fingerprint,buying_options=excluded.buying_options,
        shipping_cost=excluded.shipping_cost,shipping_currency=excluded.shipping_currency''',
        (item_id, title, item.get('itemWebUrl', ''), image_url, seller, price, currency, now, now,
         fingerprint(title, seller), buying_options, shipping_cost, shipping_currency))
    if not listing_photos(conn, item_id):
        # The full photo list replaces these when the listing is analysed, so photo numbers stay stable.
        store_photos(conn, item_id, measure.photos_from_item(item))
    if wardrobe_id:
        conn.execute('INSERT OR IGNORE INTO matches(item_id,wardrobe_id) VALUES(?,?)', (item_id, wardrobe_id))
    if old is None:
        conn.execute('INSERT OR IGNORE INTO price_history VALUES(?,?,?,?)', (item_id, now, price, currency))
        return 'new'
    if tuple(old) == (price, currency):
        return 'seen'
    if is_auction_only(buying_options):
        return 'bid_changed'  # a rising bid is not a price change, so it stays out of the price history
    conn.execute('INSERT OR IGNORE INTO price_history VALUES(?,?,?,?)', (item_id, now, price, currency))
    return 'price_changed'


def catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))['items']


# --- Reading measurements from photos -------------------------------------------------

def garment_types(conn, items=None):
    """item_id -> garment type ('jacket', 'trousers', ...), from the wardrobe target each listing matched."""
    kind_of = {x['id']: measure.garment_type_for(x) for x in (items if items is not None else catalog())}
    types = {}
    for item_id, wid in conn.execute('SELECT item_id,wardrobe_id FROM matches ORDER BY rowid'):
        kind = kind_of.get(wid)
        if kind and item_id not in types:
            types[item_id] = kind
    return types


def pending_analysis(conn, limit):
    """Listings still to analyse, newest first: never analysed, or failed fewer than MAX_ATTEMPTS times.

    Rejected listings and garments sold by size (accessories, shoes, basics) are left out.
    """
    types = garment_types(conn)
    rows = conn.execute("""SELECT l.item_id, l.title, l.image_url FROM listings l
        LEFT JOIN listing_analysis a ON a.item_id=l.item_id
        LEFT JOIN listing_reviews r ON r.item_id=l.item_id
        WHERE (a.item_id IS NULL OR (a.status='error' AND a.attempts < ?))
          AND COALESCE(r.status,'unreviewed') != 'rejected'
        ORDER BY l.first_seen DESC""", (MAX_ATTEMPTS,)).fetchall()
    jobs = []
    for item_id, title, image_url in rows:
        if item_id in types:
            photos = listing_photos(conn, item_id) or ([measure.full_size_photo(image_url)] if image_url else [])
            if not photos and not item_id.startswith('v1|'):
                continue  # added by hand from another site without a photo: nothing to read
            jobs.append((item_id, title, types[item_id], photos))
            if len(jobs) >= limit:
                break
    return jobs


def _analyze_one(job, access_token, key, model):
    """Runs in a worker thread: fetch the full listing, then read it. Returns (photos, readings, raw)."""
    item_id, title, garment_type, photos = job
    text = ''
    if access_token and item_id.startswith('v1|'):
        try:
            full = get_item(item_id, access_token)
            photos = measure.photos_from_item(full) or photos
            text = measure.listing_text(full)
        except requests.RequestException:
            pass  # ended or unreachable listing: fall back to the photos stored from the search
    if not photos and not text:
        raise measure.AnalysisError('no photos available (the listing may have ended)')
    readings, raw = measure.read_measurements(photos, garment_type, title, text, key, model)
    return photos, readings, raw


def save_analysis(conn, item_id, photos, readings=None, raw='', error=None, model=''):
    """Store one result. A failure never removes readings from an earlier successful analysis."""
    store_photos(conn, item_id, photos)
    now = utc_now()
    if error:
        conn.execute("""INSERT INTO listing_analysis(item_id,status,analyzed_at,attempts,photo_count,model,error)
            VALUES(?,'error',?,1,?,?,?) ON CONFLICT(item_id) DO UPDATE SET status='error',
            analyzed_at=excluded.analyzed_at, attempts=listing_analysis.attempts+1, error=excluded.error""",
                     (item_id, now, len(photos), model, error))
        return
    conn.execute('DELETE FROM listing_measurements WHERE item_id=?', (item_id,))
    conn.executemany("""INSERT INTO listing_measurements(item_id,name,value_cm,raw_value,raw_unit,flat,source,confidence,note,verification_status)
        VALUES(?,?,?,?,?,?,?,?,?,?)""", [(item_id, r['name'], r['value_cm'], r['raw_value'], r['raw_unit'], int(r['flat']),
                                        r['source'], r['confidence'], r['note'], 'provisional' if r.get('source', '').startswith('photo ') else 'seller_unverified') for r in readings or []])
    conn.execute("""INSERT INTO listing_analysis(item_id,status,analyzed_at,attempts,photo_count,model,error,raw)
        VALUES(?,'ok',?,1,?,?,'',?) ON CONFLICT(item_id) DO UPDATE SET status='ok', analyzed_at=excluded.analyzed_at,
        attempts=listing_analysis.attempts+1, photo_count=excluded.photo_count, model=excluded.model, error='', raw=excluded.raw""",
                 (item_id, now, len(photos), model, (raw or '')[:20000]))


def analyze_pending(conn, access_token, limit=100, workers=4):
    """Read measurements for up to `limit` listings that have not been analysed yet. Prints progress."""
    key, model = measure.api_key(), measure.model_name()
    stats = {'analyzed': 0, 'with_measurements': 0, 'failed': 0}
    if not key:
        print('Photo analysis skipped: add DEEPSEEK_API_KEY to .env')
        return stats
    jobs = pending_analysis(conn, limit)
    if not jobs:
        print('Photo analysis: nothing new to analyse')
        return stats
    print(f'Analysing {len(jobs)} listing(s) with {model}...')
    stopped = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_analyze_one, job, access_token, key, model): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            item_id, title, _, photos = futures[future]
            prefix = f'  [{done}/{len(jobs)}] {title[:60]}'
            try:
                used_photos, readings, raw = future.result()
            except measure.AuthError as exc:
                stopped = str(exc)
                pool.shutdown(wait=False, cancel_futures=True)
                break
            except Exception as exc:  # one listing failing must not stop the rest
                error = str(exc) if isinstance(exc, measure.AnalysisError) else f'{type(exc).__name__}: {exc}'
                save_analysis(conn, item_id, photos, error=error, model=model)
                stats['failed'] += 1
                print(f'{prefix}: FAILED - {error}')
            else:
                save_analysis(conn, item_id, used_photos, readings, raw, model=model)
                stats['analyzed'] += 1
                stats['with_measurements'] += bool(readings)
                found = ', '.join(f"{r['name']} {r['value_cm']} cm" for r in readings) or 'no measurements shown'
                print(f'{prefix}: {found}')
            conn.commit()
    conn.commit()
    if stopped:
        print(f'Photo analysis stopped: {stopped}')
    return stats


# --- Report ---------------------------------------------------------------------------

REPORT_STYLE = ('body{font:15px system-ui;background:#f7f5f0;color:#222;max-width:1150px;margin:2rem auto;padding:0 1rem}'
                'article{display:flex;gap:1.2rem;padding:1rem;background:white;border:1px solid #ddd;border-radius:12px;margin:1rem 0}'
                'img{width:130px;height:140px;object-fit:contain}h3{margin:.3rem 0}a{color:#1f4b6e}small{color:#666}.m{color:#2d5a3d}'
                'table{border-collapse:collapse;width:100%;background:white}td,th{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}'
                '@media(max-width:600px){img{width:90px;height:100px}}')


def report(conn):
    items = catalog()
    by_id = {x['id']: x for x in items}
    rows = conn.execute('''SELECT l.item_id,l.title,l.url,l.image_url,l.seller,l.price,l.currency,
        l.shipping_cost,l.shipping_currency,l.buying_options,l.first_seen,l.last_seen,
        COALESCE(r.status,'unreviewed'),COALESCE(r.notes,l.notes,''),
        (SELECT COUNT(*) FROM listings x WHERE x.fingerprint=l.fingerprint) AS similar
        FROM listings l LEFT JOIN listing_reviews r ON l.item_id=r.item_id
        ORDER BY l.first_seen DESC LIMIT 2000''').fetchall()
    matched = {}
    for item_id, wid in conn.execute('SELECT item_id,wardrobe_id FROM matches'):
        matched.setdefault(item_id, []).append(wid)
    readings = {}
    for item_id, name, value_cm, source, confidence in conn.execute(
            'SELECT item_id,name,value_cm,source,confidence FROM listing_measurements'):
        readings.setdefault(item_id, []).append((name, value_cm, source, confidence))
    esc = lambda v: html.escape(str(v if v is not None else ''), quote=True)
    cards = []
    for (item_id, title, url, img, seller, price, currency, ship, ship_currency, options,
         first, last, status, notes, similar) in rows:
        labels = ', '.join(by_id[x]['name'] for x in matched.get(item_id, []) if x in by_id)
        safe_url = url if (url or '').startswith('https://') else '#'
        safe_img = img if (img or '').startswith('https://') else ''
        price_text = f'{price:.2f} {currency}' if price is not None else 'Price unknown'
        if is_auction_only(options):
            price_text += ' (current bid)'
        shipping_text = f' + {ship:.2f} {ship_currency} shipping' if ship is not None else ''
        relist = f' · Possible relisting ({similar} with same seller and title)' if similar > 1 else ''
        found = sorted(readings.get(item_id, []), key=lambda r: measure.ORDER.index(r[0]))
        measured = ''
        if found:
            parts = [f"{name.replace('_', ' ')}{' (flat)' if name in measure.WIDTHS else ''} {value:.1f} cm"
                     f"{' ?' if confidence == 'low' else ''} [{source}]" for name, value, source, confidence in found]
            measured = f'<p class="m">Measured: {esc(" · ".join(parts))}</p>'
        cards.append(f'<article><img loading="lazy" src="{esc(safe_img)}" alt=""><div><h3><a href="{esc(safe_url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a></h3><p><strong>{esc(price_text)}</strong>{esc(shipping_text)} · {esc(seller)} · {esc(status)}</p>{measured}<p>{esc(labels)}</p><small>First: {esc(first)} · Last: {esc(last)}{esc(relist)} · {esc(notes)}</small></div></article>')
    inventory = ''.join(f'<tr><td>{esc(x["category"])}</td><td>{esc(x["name"])}</td><td>{esc(x["owned_quantity"])}/{esc(x["target_quantity"])}</td><td>{esc(x["priority"])}</td></tr>' for x in items)
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Vintage Wardrobe Watcher</title><style>{REPORT_STYLE}</style><h1>Vintage Wardrobe Watcher</h1>'
            '<p>Local archive. Similarity flags are possible relistings, not proof. Measurements are read from each listing by DeepSeek; '
            '"?" marks an uncertain reading and [photo N] says which photo to check.</p>'
            '<h2>Wardrobe plan</h2><table><tr><th>Category</th><th>Garment</th><th>Owned / target</th><th>Priority (1 highest)</th></tr>'
            + inventory + '</table><h2>Archived listings</h2>' + '\n'.join(cards) + '</html>')
    path = ROOT / 'report.html'
    path.write_text(page, encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-only', action='store_true', help='No eBay search; with --analyze-images, only analyse')
    parser.add_argument('--limit-per-query', type=int, default=40)
    parser.add_argument('--max-queries', type=int, default=0, help='0 means all enabled queries')
    parser.add_argument('--review', nargs=3, metavar=('ITEM_ID', 'STATUS', 'NOTES'), help='Set status: ' + '/'.join(REVIEW_STATUSES))
    parser.add_argument('--analyze-images', action='store_true',
                        help='Read measurements from listing photos with DeepSeek (each listing is analysed once)')
    parser.add_argument('--analyze-limit', type=int, default=100, help='Most listings to analyse in one run (default 100)')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    with connect() as conn:
        if args.review:
            item_id, status, notes = args.review
            if status not in REVIEW_STATUSES:
                parser.error('Invalid review status')
            if not conn.execute('SELECT 1 FROM listings WHERE item_id=?', (item_id,)).fetchone():
                parser.error('Unknown item ID')
            conn.execute('INSERT INTO listing_reviews VALUES(?,?,?) ON CONFLICT(item_id) DO UPDATE SET status=excluded.status,notes=excluded.notes', (item_id, status, notes))
            conn.commit()
            print('Report:', report(conn))
            return
        access_token = None
        if not args.report_only:
            access_token = token()
            stats = {'new': 0, 'seen': 0, 'price_changed': 0, 'bid_changed': 0, 'skipped': 0}
            filter_config = search_prefilter.load_config()
            searches = [(x, q) for x in group_priority.search_order(catalog(), group_priority.load()) for q in x['search_terms']]
            if args.max_queries:
                searches = searches[:args.max_queries]
            prefilter_stats = {'returned': 0, 'accepted': 0, 'rejected': 0, 'already_analyzed': 0}
            for wardrobe_item, query in searches:
                wardrobe_id = wardrobe_item['id']
                kind = measure.garment_type_for(wardrobe_item)
                options = search_prefilter.options_for(filter_config, kind)
                filters = search_prefilter.ebay_filters(options, _ship_to_country())
                try:
                    for item in fetch(query, access_token, args.limit_per_query, filters=filters):
                        prefilter_stats['returned'] += 1
                        accepted, reason = search_prefilter.accept_item(item, options)
                        if not accepted:
                            prefilter_stats['rejected'] += 1
                            continue
                        prefilter_stats['accepted'] += 1
                        existing_id = item.get('itemId')
                        if existing_id and conn.execute(
                                "SELECT 1 FROM listing_analysis WHERE item_id=? AND status='ok'", (existing_id,)).fetchone():
                            prefilter_stats['already_analyzed'] += 1
                        stats[ingest(conn, item, wardrobe_id)] += 1
                    conn.commit()
                except requests.RequestException as exc:
                    print(f'API error for {query!r}: {exc}')
            print('Search prefilter:', prefilter_stats)
            print(stats)
        if args.analyze_images:
            if access_token is None:
                try:
                    access_token = token()
                except (RuntimeError, requests.RequestException) as exc:
                    print(f'No eBay access ({exc}); analysing stored photos only, without descriptions')
            print(analyze_pending(conn, access_token, args.analyze_limit))
        print('Report:', report(conn))


if __name__ == '__main__':
    main()
