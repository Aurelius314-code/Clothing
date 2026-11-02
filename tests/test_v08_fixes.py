"""Offline tests for the v0.8 fixes: one key per Tradera listing, every photo kept, real website names,
and auction prices stored with their bids."""
import sqlite3

import marketplaces
import tradera
import watcher

TRADERA_LINK = 'https://www.tradera.com/item/1640/654970712/gant-ullkavaj'


def test_european_tab_and_search_give_a_tradera_listing_the_same_key():
    assert marketplaces.listing_key(TRADERA_LINK) == tradera.item_key(TRADERA_LINK) == 'tradera:654970712'
    assert marketplaces.listing_key(TRADERA_LINK + '?utm_source=app') == 'tradera:654970712'
    other = marketplaces.listing_key('https://www.sellpy.com/item/123')
    assert other.startswith('sellpy:') and other == marketplaces.listing_key('https://www.sellpy.com/item/123?x=1')


def test_hashed_tradera_listings_get_their_item_number(tmp_path, monkeypatch):
    db = tmp_path / 'old.sqlite3'
    monkeypatch.setattr(watcher, 'DB', db)
    with watcher.connect() as conn:  # a database from before v0.8, with one listing saved by the European tab
        conn.execute("DELETE FROM meta WHERE key='migrated_v0.8'")
        conn.execute('CREATE TABLE IF NOT EXISTS listing_source_snapshots (item_id TEXT PRIMARY KEY, description TEXT, aspects_json TEXT, saved_at TEXT)')
        old = 'tradera:3a4b5cccab68a2948f0ba94d'
        conn.execute("INSERT INTO listings(item_id,title,url,first_seen,last_seen) VALUES(?,?,?,'t','t')", (old, 'Gant ullkavaj', TRADERA_LINK))
        conn.execute("INSERT INTO listings(item_id,title,url,first_seen,last_seen) VALUES('tradera:ffff0000aaaa1111bbbb2222','x','https://www.tradera.com/category/1640','t','t')")
        conn.execute("INSERT INTO matches VALUES(?, 'W005')", (old,))
        conn.execute("INSERT INTO listing_reviews VALUES(?, 'saved', 'fin')", (old,))
        conn.execute("INSERT INTO listing_measurements(item_id,name,value_cm,source,confidence,verification_status) VALUES(?,'shoulders',46,'manual','high','human_verified')", (old,))
        conn.execute("INSERT INTO listing_source_snapshots VALUES(?, 'Axelbredd 46', '{}', 't')", (old,))
        conn.commit()
    with watcher.connect() as conn:
        keys = {k for (k,) in conn.execute('SELECT item_id FROM listings')}
        assert keys == {'tradera:654970712', 'tradera:ffff0000aaaa1111bbbb2222'}  # a link without item number is left alone
        for table in ('matches', 'listing_reviews', 'listing_measurements', 'listing_source_snapshots'):
            assert conn.execute(f"SELECT item_id FROM {table}").fetchone() == ('tradera:654970712',), table


def test_every_photo_kept_with_its_largest_size():
    # Photo b has no large size: it keeps its medium size instead of being dropped.
    shared_names = [{'url': 'https://img.tradera.net/large/a.jpg', 'format': 'Large'},
                    {'url': 'https://img.tradera.net/medium/a.jpg', 'format': 'Medium'},
                    {'url': 'https://img.tradera.net/medium/b.jpg', 'format': 'Medium'},
                    {'url': 'https://img.tradera.net/large/c.jpg', 'format': 'Large'},
                    {'url': 'https://img.tradera.net/medium/c.jpg', 'format': 'Medium'}]
    assert tradera.photos({'detailedImageLinks': shared_names}) == [
        'https://img.tradera.net/large/a.jpg', 'https://img.tradera.net/medium/b.jpg', 'https://img.tradera.net/large/c.jpg']
    # Sizes with different file names: use the largest size that every photo has.
    own_names = [{'url': 'https://img.tradera.net/a_l.jpg', 'format': 'Large'},
                 {'url': 'https://img.tradera.net/a_m.jpg', 'format': 'Medium'},
                 {'url': 'https://img.tradera.net/b_m.jpg', 'format': 'Medium'}]
    assert tradera.photos({'detailedImageLinks': own_names}) == ['https://img.tradera.net/a_m.jpg', 'https://img.tradera.net/b_m.jpg']


def test_live_tradera_photo_sizes():
    # As Tradera sent it for item 758913588: every photo as thumbs/ and minithumb/ with the same file name.
    names = ['666614049_5d084ada.jpg', '666614049_dea93650.jpg', '666614049_c77dfae8.jpg']
    links = [f'https://img.tradera.net/{size}/049/{name}' for name in names for size in ('thumbs', 'minithumb')]
    assert tradera.photos({'imageLinks': links}) == [f'https://img.tradera.net/thumbs/049/{name}' for name in names]
    # A larger size, when offered, wins for that photo only.
    bigger = links + ['https://img.tradera.net/images/049/666614049_dea93650.jpg']
    assert tradera.photos({'imageLinks': bigger}) == [
        'https://img.tradera.net/thumbs/049/666614049_5d084ada.jpg', 'https://img.tradera.net/images/049/666614049_dea93650.jpg',
        'https://img.tradera.net/thumbs/049/666614049_c77dfae8.jpg']


def test_lookalike_websites_are_not_recognised():
    assert watcher.ebay_item_key('https://www.ebay.com/itm/317521940472?var=&mkevt=1') == 'v1|317521940472|0'
    assert watcher.ebay_item_key('https://www.ebay.com/itm/Some-Title-Words/123456789012') == 'v1|123456789012|0'
    assert watcher.ebay_item_key('https://ebay.com.au/itm/123456789012') == 'v1|123456789012|0'
    for fake in ('https://www.ebay.com.evil.example/itm/123456789012', 'https://notebay.com/itm/123456789012',
                 'https://evil.example/?u=ebay.com/itm/123456789012'):
        assert watcher.ebay_item_key(fake) is None, fake
    assert tradera.item_key('www.tradera.com/en/item/1640/654970712') == 'tradera:654970712'
    for fake in ('https://nottradera.com/item/1/123456789', 'https://tradera.com.evil.example/item/1/123456789',
                 'https://evil.example/tradera.com/item/1/123456789', 'ftp://www.tradera.com/item/1/123456789'):
        assert tradera.item_key(fake) is None, fake


def test_auction_bids_are_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    base = {'id': 1, 'shortDescription': 'kavaj', 'itemType': 'Auction', 'nextBid': 150}
    with watcher.connect() as conn:
        watcher.ingest(conn, tradera.to_listing({**base, 'id': 1, 'hasBids': False, 'bidCount': 0}))
        watcher.ingest(conn, tradera.to_listing({**base, 'id': 2, 'hasBids': True, 'bidCount': 3, 'maxBid': 320, 'buyItNowPrice': 900}))
        watcher.ingest(conn, tradera.to_listing({**base, 'id': 3}))  # Tradera says nothing about bids
        rows = dict((r[0], r[1:]) for r in conn.execute('SELECT item_id,price,current_bid,bid_count,buying_options FROM listings'))
    assert rows['tradera:1'] == (150.0, 150.0, 0, 'AUCTION')
    assert rows['tradera:2'] == (900.0, 320.0, 3, 'AUCTION,FIXED_PRICE')
    assert rows['tradera:3'] == (150.0, 150.0, None, 'AUCTION')


def test_old_database_gets_the_new_columns(tmp_path, monkeypatch):
    db = tmp_path / 'old.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('''CREATE TABLE listings (item_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT, image_url TEXT,
            seller TEXT, price REAL, currency TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, fingerprint TEXT,
            notes TEXT DEFAULT '', status TEXT DEFAULT 'unreviewed')''')
        conn.execute("INSERT INTO listings(item_id,title,price,currency,first_seen,last_seen) VALUES('v1|1|0','coat',88,'USD','t','t')")
    monkeypatch.setattr(watcher, 'DB', db)
    with watcher.connect() as conn:
        assert conn.execute("SELECT title,price,current_bid,bid_count FROM listings").fetchone() == ('coat', 88.0, None, None)


def test_live_tradera_item_reply():
    """Shapes as Tradera's GET /v4/items sent them for item 758913588 (2 Nov 2026), shortened to 2 of 19 photos."""
    guids = ['5d084ada-e184-4e26-95ab-820992455c6d', 'dea93650-b5fb-456b-a725-6c1a75227eff']
    item = {
        'id': 758913588, 'itemType': 1, 'totalBids': 0, 'openingBid': 590, 'nextBid': 590, 'maxBid': 0, 'buyItNowPrice': 0,
        'shortDescription': 'Marks & Spencer Harris Tweed Kavaj Stl 52 L', 'numberOfImages': 2,
        'itemLink': 'http://www.tradera.com/item/1000679/758913588/marks-spencer-harris-tweed-kavaj',
        'imageLinks': [f'http://img.tradera.net/images/049/666614049_{g}.jpg' for g in guids],
        'detailedImageLinks': [{'url': f'https://img.tradera.net/{folder}/049/666614049_{g}.jpg', 'format': fmt}
                               for g in guids for folder, fmt in (('images', 'normal'), ('preview', 'preview'),
                                                                  ('thumbs', 'thumbnail'), ('minithumb', 'minithumbnail'))],
        'shippingOptions': [{'shippingOptionId': 6, 'cost': 140, 'shippingWeight': 0, 'shippingWeightSpecified': True,
                             'shippingProductId': 10, 'shippingProductIdSpecified': True, 'shippingProviderId': 6,
                             'sellerSurchargeSpecified': False, 'sellerDiscountSpecified': False}],
        'acceptsPickup': False, 'shippingCondition': '',
    }
    assert tradera.photos(item) == [f'https://img.tradera.net/images/049/666614049_{g}.jpg' for g in guids]
    assert tradera.cheapest_shipping(item) == 140.0
    listing = tradera.to_listing(item)
    assert listing['itemWebUrl'].startswith('https://www.tradera.com/item/1000679/758913588/')
    assert listing['buyingOptions'] == ['AUCTION'] and listing['bidCount'] == 0
    assert listing['currentBidPrice'] == {'value': '590.0', 'currency': 'SEK'}
