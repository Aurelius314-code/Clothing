"""Offline tests for the Swedish address (SWEDISH_PICKUP): the extra eBay search, Tradera shipping and delivery marks."""
import sqlite3

import tradera
import watcher

WARDROBE = [{'id': 'W999', 'category': 'Tailoring', 'name': 'Heavy tweed sport coat', 'search_terms': ['harris tweed jacket'],
             'enabled': True, 'owned_quantity': 0, 'target_quantity': 1}]


def ebay_item(item_id, price, currency, shipping):
    return {'itemId': item_id, 'title': f'Harris Tweed jacket {item_id}', 'price': {'value': str(price), 'currency': currency},
            'buyingOptions': ['FIXED_PRICE'], 'shippingOptions': [{'shippingCost': {'value': str(shipping), 'currency': currency}}]}


def listing(conn, item_id):
    return conn.execute('SELECT price,currency,shipping_cost,shipping_currency,delivery_country FROM listings WHERE item_id=?',
                        (item_id,)).fetchone()


def test_sweden_search_marks_new_listings_and_leaves_norway_listings_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setenv('EBAY_SHIP_TO_COUNTRY', 'NO')
    calls = []

    def fake_fetch(query, token, limit, filters=None, country=None, marketplace=None):
        calls.append((country, marketplace, filters))
        if country == 'NO':
            return iter([ebay_item('v1|1|0', 90, 'GBP', 15)])
        return iter([ebay_item('v1|1|0', 105, 'EUR', 9), ebay_item('v1|2|0', 60, 'EUR', 8)])
    monkeypatch.setattr(watcher, 'fetch', fake_fetch)
    with watcher.connect() as conn:
        watcher.search_ebay(conn, 'token', WARDROBE, country='NO')
        stats, _ = watcher.search_ebay(conn, 'token', WARDROBE, filter_config={'enabled': True, 'garment_types': {
            'jacket': {'max_item_price': 50, 'price_currency': 'GBP'}}}, country='SE', marketplace='EBAY_DE')
        assert listing(conn, 'v1|1|0') == (90.0, 'GBP', 15.0, 'GBP', 'NO')   # ships to Norway: Norwegian price kept
        assert listing(conn, 'v1|2|0') == (60.0, 'EUR', 8.0, 'EUR', 'SE')    # only ships to Sweden
        assert stats['new'] == 1 and stats['seen'] == 1
        # Found by the Norway search later: becomes a Norway listing.
        monkeypatch.setattr(watcher, 'fetch', lambda *a, **k: iter([ebay_item('v1|2|0', 55, 'GBP', 12)]))
        watcher.search_ebay(conn, 'token', WARDROBE, country='NO')
        assert listing(conn, 'v1|2|0') == (55.0, 'GBP', 12.0, 'GBP', 'NO')
    assert calls[0] == ('NO', None, 'deliveryCountry:NO')
    assert calls[1][:2] == ('SE', 'EBAY_DE') and calls[1][2] == 'deliveryCountry:SE'  # GBP price limit not sent to eBay Germany


def test_fetch_sends_country_and_marketplace(monkeypatch):
    seen = {}

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {'itemSummaries': []}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen.update(headers=headers, params=params)
        return Reply()
    monkeypatch.setattr(watcher.requests, 'get', fake_get)
    list(watcher.fetch('tweed', 'token', 10, country='SE', marketplace='EBAY_DE'))
    assert seen['headers']['X-EBAY-C-MARKETPLACE-ID'] == 'EBAY_DE'
    assert seen['headers']['X-EBAY-C-ENDUSERCTX'] == 'contextualLocation=country%3DSE'
    assert seen['params']['filter'] == 'deliveryCountry:SE'


def test_tradera_shipping_price():
    item = {'shippingOptions': [{'cost': 79, 'sellerSurcharge': 10}, {'cost': 120, 'sellerDiscount': 20}, {'cost': 'x'}]}
    assert tradera.cheapest_shipping(item) == 89.0
    assert tradera.cheapest_shipping({'shippingOptions': [{'cost': 79, 'sellerDiscount': 79}]}) == 0.0  # free shipping
    assert tradera.cheapest_shipping({'ShippingOptions': {'ShippingOption': [{'Cost': 59}]}}) == 59.0
    assert tradera.cheapest_shipping({'acceptsPickup': True}) is None


def test_tradera_listings_get_swedish_shipping_once(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setenv('SWEDISH_PICKUP', '1')
    monkeypatch.setenv('TRADERA_APP_ID', '1')
    monkeypatch.setenv('TRADERA_APP_KEY', 'k')
    raw = [{'id': 111111, 'shortDescription': 'Tweedkavaj', 'itemType': 'PureBuyItNow', 'buyItNowPrice': 400},
           {'id': 222222, 'shortDescription': 'Tweedkavaj 2', 'itemType': 'PureBuyItNow', 'buyItNowPrice': 300}]
    monkeypatch.setattr(tradera, 'search', lambda q, c, limit: iter(raw))
    looked_up = []

    def fake_get_item(key):
        looked_up.append(key)
        if key == 'tradera:222222':
            raise tradera.TraderaError('not found on Tradera (the listing may have ended)')
        return {'id': 111111, 'shippingOptions': [{'cost': 79}]}
    monkeypatch.setattr(tradera, 'get_item', fake_get_item)
    with watcher.connect() as conn:
        watcher.search_tradera(conn, WARDROBE)
        assert watcher.tradera_shipping(conn) == 2
        assert listing(conn, 'tradera:111111') == (400.0, 'SEK', 79.0, 'SEK', 'SE')
        assert listing(conn, 'tradera:222222') == (300.0, 'SEK', None, '', 'SE')
        watcher.search_tradera(conn, WARDROBE)  # found again: the looked-up shipping stays
        assert listing(conn, 'tradera:111111')[2:4] == (79.0, 'SEK')
        assert watcher.tradera_shipping(conn) == 0 and len(looked_up) == 2  # never looked up twice


def test_without_swedish_pickup_nothing_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.delenv('SWEDISH_PICKUP', raising=False)
    monkeypatch.setattr(tradera, 'search', lambda q, c, limit: iter([{'id': 333333, 'shortDescription': 'x', 'buyItNowPrice': 100}]))
    with watcher.connect() as conn:
        watcher.search_tradera(conn, WARDROBE)
        assert listing(conn, 'tradera:333333')[4] is None
        assert watcher.tradera_shipping(conn) == 0


def test_old_ebay_listings_count_as_norway_listings(tmp_path, monkeypatch):
    db = tmp_path / 'old.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('''CREATE TABLE listings (item_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT, image_url TEXT,
            seller TEXT, price REAL, currency TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, fingerprint TEXT,
            notes TEXT DEFAULT '', status TEXT DEFAULT 'unreviewed', buying_options TEXT DEFAULT '')''')
        conn.execute("INSERT INTO listings(item_id,title,first_seen,last_seen,buying_options) VALUES('v1|1|0','searched','t','t','FIXED_PRICE')")
        conn.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES('v1|2|0','added by hand','t','t')")
    monkeypatch.setattr(watcher, 'DB', db)
    with watcher.connect() as conn:
        assert dict(conn.execute('SELECT item_id,delivery_country FROM listings')) == {'v1|1|0': 'NO', 'v1|2|0': None}
