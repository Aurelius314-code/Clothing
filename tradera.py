"""Tradera (the Swedish marketplace) through Tradera's official REST API v4.

Tradera listings are turned into the same shape as eBay's Browse API results, so
watcher.ingest(), the DeepSeek analysis, the traffic light and the app treat them like eBay
listings. Their keys in the database are 'tradera:<item number>'.

Needs TRADERA_APP_ID and TRADERA_APP_KEY in .env (free developer account: api.tradera.com/register).
Swedish search terms live in tradera.json, keyed by wardrobe ID; items without them use the
English terms from wardrobe.json.

Tradera's REST API is still in beta and its search reply is not fully documented, so the
parsing below accepts both camelCase (REST) and PascalCase (the older SOAP API) field names.
Try it on your own keys with:  python tradera.py "harris tweed kavaj"
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

import measure

API = 'https://api.tradera.com/v4'
CONFIG = Path(__file__).with_name('tradera.json')
KEY_PREFIX = 'tradera:'
CURRENCY = 'SEK'  # Tradera prices are whole Swedish kronor
MAX_PAGES = 20    # safety net for one search term
# https://www.tradera.com/item/1640/654970712/gant-ullkavaj -> 654970712 (category / item number / title)
ITEM_URL = re.compile(r'tradera\.com/(?:[a-z]{2}/)?item/\d+/(\d{5,10})(?!\d)', re.IGNORECASE)


class TraderaError(Exception):
    """Tradera refused or answered something unexpected."""


class RateLimited(TraderaError):
    """Tradera's daily limit (10,000 calls per method) is used up."""


def credentials():
    """(app id, app key) from .env, or None when Tradera isn't set up."""
    app_id = os.environ.get('TRADERA_APP_ID', '').strip()
    app_key = os.environ.get('TRADERA_APP_KEY', '').strip()
    return (app_id, app_key) if app_id and app_key else None


def item_key(url):
    """'tradera:<item number>' for a Tradera listing URL, else None."""
    match = ITEM_URL.search(url or '')
    return KEY_PREFIX + match.group(1) if match else None


def item_number(key_or_url):
    value = str(key_or_url or '').strip()
    if value.startswith(KEY_PREFIX):
        value = value[len(KEY_PREFIX):]
    elif not value.isdigit():
        value = (item_key(value) or '')[len(KEY_PREFIX):]
    if not value.isdigit():
        raise TraderaError(f'not a Tradera item number or link: {key_or_url!r}')
    return int(value)


# --- Reading Tradera's replies --------------------------------------------------------

def _get(data, name):
    """data[name], also accepting the PascalCase spelling of the SOAP API (ShortDescription)."""
    if not isinstance(data, dict):
        return None
    value = data.get(name)
    return data.get(name[:1].upper() + name[1:]) if value is None else value


def _list(value, wrapper):
    """A list, also when the SOAP style wraps it ({'ImageLink': [...]}) or sends a single object."""
    if isinstance(value, dict):
        value = value.get(wrapper, value.get(wrapper[:1].lower() + wrapper[1:], [value]))
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _number(data, name):
    try:
        value = float(_get(data, name))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _is_auction(item):
    kind = _get(item, 'itemType')
    return kind == 1 or 'auction' in str(kind or '').lower()  # REST uses 1, SOAP 'Auction'


def _format_rank(name):
    name = (name or '').lower()
    if any(word in name for word in ('large', 'original', 'big', 'xl', 'full')):
        return 3
    if any(word in name for word in ('medium', 'normal', 'standard', 'gallery')):
        return 2
    if any(word in name for word in ('small', 'thumb', 'mini')):
        return 1
    return 0


def _https(url):
    url = str(url or '').strip()
    return 'https://' + url[len('http://'):] if url.startswith('http://') else url


def _links(entries):
    """(url, format) for a list of image links that may be plain strings or {url, format} objects."""
    out = []
    for entry in entries:
        if isinstance(entry, str):
            out.append((entry, ''))
        elif isinstance(entry, dict) and _get(entry, 'url'):
            out.append((str(_get(entry, 'url')), str(_get(entry, 'format') or '')))
    return out


def photos(item):
    """The listing's photos, one size per photo (the largest offered), https, in listing order."""
    detailed = _links(_list(_get(item, 'detailedImageLinks'), 'ImageLink'))
    plain = _links(_list(_get(item, 'imageLinks'), 'ImageLink'))
    urls = []
    for links in (detailed, plain):
        best = max((_format_rank(fmt) for _, fmt in links), default=0)
        if best:
            urls = [url for url, fmt in links if _format_rank(fmt) == best]
            break
    if not urls:
        urls = [url for url, _ in plain or detailed]
    if not urls and _get(item, 'thumbnailLink'):
        urls = [_get(item, 'thumbnailLink')]
    out = []
    for url in map(_https, urls):
        if url.startswith('https://') and url not in out:
            out.append(url)
    return out[:measure.MAX_PHOTOS]


def to_listing(item):
    """A Tradera search result or full item in the shape of an eBay Browse API item, for watcher.ingest()."""
    number = _get(item, 'id')
    if not number:
        return {}
    buy_now = _number(item, 'buyItNowPrice')
    listing = {'itemId': f'{KEY_PREFIX}{int(number)}', 'title': _get(item, 'shortDescription') or '',
               'itemWebUrl': _get(item, 'itemUrl') or _get(item, 'itemLink') or '',
               'seller': {'username': _get(item, 'sellerAlias') or _get(_get(item, 'seller'), 'alias') or ''}}
    if _is_auction(item):
        bids = _get(item, 'hasBids') or (_number(item, 'bidCount') or _number(item, 'totalBids') or 0) > 0
        current = (_number(item, 'maxBid') if bids else None) or _number(item, 'nextBid') or _number(item, 'openingBid')
        listing['buyingOptions'] = ['AUCTION'] + (['FIXED_PRICE'] if buy_now else [])
        if current:
            listing['currentBidPrice'] = {'value': str(current), 'currency': CURRENCY}
    else:
        listing['buyingOptions'] = ['FIXED_PRICE']
    if buy_now:
        listing['price'] = {'value': str(buy_now), 'currency': CURRENCY}
    pictures = photos(item)
    if pictures:
        listing['image'] = {'imageUrl': pictures[0]}
        listing['additionalImages'] = [{'imageUrl': url} for url in pictures[1:]]
    # Shipping is left out on purpose: the API only gives the price within Sweden, and the seller
    # may not ship to Norway at all. Tradera shows the price for your country on the listing.
    return listing


def listing_text(item):
    """The seller's attributes and description as plain text, for DeepSeek."""
    values = _get(item, 'attributeValues') or {}
    lines = []
    for kind, wrapper in (('termAttributeValues', 'TermAttributeValue'), ('numberAttributeValues', 'NumberAttributeValue')):
        for attribute in _list(_get(values, kind), wrapper):
            name = _get(attribute, 'name')
            found = [str(v) for v in _list(_get(attribute, 'values'), 'Value') if v not in (None, '')]
            if name and found:
                lines.append(f'{name}: {", ".join(found)}')
    description = measure._plain_text(_get(item, 'longDescription') or '', 4000)
    parts = []
    if lines:
        parts.append('Item specifics:\n' + '\n'.join(lines)[:1500])
    if description:
        parts.append('Description:\n' + description)
    return '\n\n'.join(parts)


# --- Calling Tradera ------------------------------------------------------------------

def _call(path, params=None):
    keys = credentials()
    if not keys:
        raise TraderaError('add TRADERA_APP_ID and TRADERA_APP_KEY to .env (free at api.tradera.com/register)')
    r = requests.get(API + path, params=params, timeout=45,
                     headers={'X-App-Id': keys[0], 'X-App-Key': keys[1], 'Accept': 'application/json'})
    if r.status_code == 429:
        raise RateLimited("Tradera's daily limit is used up (10,000 calls per day); try again tomorrow")
    if r.status_code in (401, 403):
        raise TraderaError(f'Tradera refused the app ID or key ({r.status_code}). Check TRADERA_APP_ID and TRADERA_APP_KEY in .env')
    if r.status_code == 404:
        raise TraderaError('not found on Tradera (the listing may have ended)')
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError as exc:
        raise TraderaError('Tradera did not reply with JSON') from exc
    errors = _list(_get(data, 'errors'), 'Error') if isinstance(data, dict) else []
    if errors:
        raise TraderaError('; '.join(str(_get(e, 'message') or _get(e, 'code') or e) for e in errors))
    return data


def _search_items(data):
    if isinstance(data, list):
        return data
    for name in ('items', 'searchItems'):
        if _get(data, name) is not None:
            return [x for x in _list(_get(data, name), 'Item') if isinstance(x, dict)]
    if _get(data, 'totalNumberOfItems') is None:
        keys = ', '.join(sorted(data)[:12]) if isinstance(data, dict) else type(data).__name__
        raise TraderaError(f'unexpected search reply from Tradera (fields: {keys})')
    return []  # no hits


def search(query, category_id=0, limit=40):
    """Up to `limit` raw search results for one search term, page by page."""
    found = 0
    for page in range(1, MAX_PAGES + 1):
        params = {'query': query, 'pageNumber': page}
        if category_id:
            params['categoryId'] = int(category_id)
        data = _call('/search', params)
        items = _search_items(data)
        for item in items:
            yield item
            found += 1
            if found >= limit:
                return
        pages = _number(data, 'totalNumberOfPages')
        if not items or (pages is not None and page >= pages):
            return


def get_item(key_or_url):
    """The full listing: every photo, the description and the attributes."""
    data = _call(f'/items/{item_number(key_or_url)}')
    inner = _get(data, 'item')
    return inner if isinstance(inner, dict) else data


# --- Search plan ----------------------------------------------------------------------

def load_config(path=CONFIG):
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{Path(path).name} must contain an object')
    return data


def searches(wardrobe_items, config=None):
    """(wardrobe item, search term, category ID) for each Tradera search, in the order given."""
    config = load_config() if config is None else config
    terms, categories = config.get('terms', {}), config.get('categories', {})
    overrides = config.get('category_overrides', {})
    plan = []
    for item in wardrobe_items:
        category = overrides.get(item['id'], categories.get(item.get('category'), 0))
        plan += [(item, term, category) for term in terms.get(item['id']) or item.get('search_terms', [])]
    return plan


def _demo(args):
    """python tradera.py "search words" [category ID]   or   python tradera.py <Tradera link>"""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name('.env'))
    if not args:
        sys.exit(_demo.__doc__)
    if item_key(args[0]) or args[0].isdigit():
        item = get_item(args[0])
        listing = to_listing(item)
        print(json.dumps(listing, ensure_ascii=False, indent=2))
        print(f'\n{len(photos(item))} photo(s). Text sent to DeepSeek:\n{listing_text(item) or "(none)"}')
        print('\nFields in Tradera\'s reply:', ', '.join(sorted(item)))
        return
    category = int(args[1]) if len(args) > 1 else 302074  # Herrkläder
    for label, cat in ((f'category {category}', category), ('all categories', 0)):
        results = list(search(args[0], cat, limit=5))
        print(f'\n{args[0]!r} in {label}: {len(results)} shown')
        for raw in results:
            listing = to_listing(raw)
            money = listing.get('price') or listing.get('currentBidPrice') or {}
            print(f"  {listing.get('title', '')[:60]:<60} {money.get('value', '?')} SEK "
                  f"{'/'.join(listing.get('buyingOptions', []))}  {listing.get('itemWebUrl', '')}")
        if results:
            print('  Fields in a search result:', ', '.join(sorted(results[0])))


if __name__ == '__main__':
    try:
        _demo(sys.argv[1:])
    except (TraderaError, requests.RequestException) as exc:
        sys.exit(f'Tradera: {exc}')
