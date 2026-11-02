"""Offline tests for the Tradera source: no keys, network or real database needed."""
import pytest

import measure
import tradera
import watcher

# A search result as the REST API (camelCase) is expected to send it...
REST_AUCTION = {
    'id': 654970712, 'shortDescription': 'Harris Tweed kavaj strl 50', 'sellerAlias': 'vintagebod',
    'itemType': 1, 'hasBids': False, 'bidCount': 0, 'maxBid': 0, 'nextBid': 150, 'buyItNowPrice': 0,
    'itemUrl': 'https://www.tradera.com/item/1640/654970712/harris-tweed-kavaj',
    'thumbnailLink': 'http://img.tradera.net/thumbs/abc.jpg',
    'imageLinks': [{'url': 'https://img.tradera.net/small/abc.jpg', 'format': 'Small'},
                   {'url': 'https://img.tradera.net/large/abc.jpg', 'format': 'Large'},
                   {'url': 'https://img.tradera.net/small/def.jpg', 'format': 'Small'},
                   {'url': 'https://img.tradera.net/large/def.jpg', 'format': 'Large'}],
}
# ...and the same kind of item in the older SOAP style (PascalCase, wrapped lists).
SOAP_BUY_NOW = {
    'Id': 123456789, 'ShortDescription': 'Flanellbyxor grå', 'SellerAlias': 'klader', 'ItemType': 'PureBuyItNow',
    'BuyItNowPrice': 400, 'ItemUrl': 'https://www.tradera.com/item/1650/123456789/flanellbyxor',
    'ImageLinks': {'ImageLink': [{'Url': 'http://img.tradera.net/medium/x.jpg', 'Format': 'Medium'}]},
}


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise watcher.requests.HTTPError(str(self.status_code))


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv('TRADERA_APP_ID', '1234')
    monkeypatch.setenv('TRADERA_APP_KEY', 'secret')


def test_item_keys_from_links():
    assert tradera.item_key('https://www.tradera.com/item/1640/654970712/gant-ullkavaj') == 'tradera:654970712'
    assert tradera.item_key('https://www.tradera.com/en/item/1640/654970712/gant?utm=x') == 'tradera:654970712'
    assert tradera.item_key('https://www.ebay.com/itm/317521940472') is None
    assert watcher.listing_key('https://www.tradera.com/item/1640/654970712/x') == 'tradera:654970712'
    assert watcher.listing_key('https://www.ebay.co.uk/itm/317521940472?var=') == 'v1|317521940472|0'
    assert tradera.item_number('tradera:654970712') == 654970712


def test_auction_without_bids_uses_next_bid_and_largest_photos():
    listing = tradera.to_listing(REST_AUCTION)
    assert listing['itemId'] == 'tradera:654970712'
    assert listing['buyingOptions'] == ['AUCTION']
    assert listing['currentBidPrice'] == {'value': '150.0', 'currency': 'SEK'}
    assert 'price' not in listing
    assert listing['image']['imageUrl'] == 'https://img.tradera.net/large/abc.jpg'
    assert measure.photos_from_item(listing) == ['https://img.tradera.net/large/abc.jpg', 'https://img.tradera.net/large/def.jpg']
    assert watcher.is_auction_only(','.join(listing['buyingOptions']))


def test_soap_style_buy_now_and_http_photos():
    listing = tradera.to_listing(SOAP_BUY_NOW)
    assert listing['title'] == 'Flanellbyxor grå' and listing['seller']['username'] == 'klader'
    assert listing['price'] == {'value': '400.0', 'currency': 'SEK'} and listing['buyingOptions'] == ['FIXED_PRICE']
    # Tradera's live search sends item links as http://; they are stored as https://.
    live = tradera.to_listing({'id': 755387597, 'itemType': 'PureBuyItNow', 'buyItNowPrice': 1500,
                               'itemUrl': 'http://www.tradera.com/item/1000679/755387597/harris-tweed-kavaj'})
    assert live['itemWebUrl'] == 'https://www.tradera.com/item/1000679/755387597/harris-tweed-kavaj'
    assert tradera.item_key(live['itemWebUrl']) == 'tradera:755387597'
    assert listing['image']['imageUrl'] == 'https://img.tradera.net/medium/x.jpg'


def test_auction_with_bids_and_buy_now():
    listing = tradera.to_listing({**REST_AUCTION, 'hasBids': True, 'bidCount': 3, 'maxBid': 320, 'buyItNowPrice': 900})
    assert listing['buyingOptions'] == ['AUCTION', 'FIXED_PRICE']
    assert listing['currentBidPrice']['value'] == '320.0' and listing['price']['value'] == '900.0'


def test_full_item_photos_and_text():
    item = {'id': 1, 'imageLinks': ['https://img.tradera.net/a.jpg', 'https://img.tradera.net/b.jpg'],
            'detailedImageLinks': [{'url': 'https://img.tradera.net/a_t.jpg', 'format': 'Thumbnail'},
                                   {'url': 'https://img.tradera.net/a_l.jpg', 'format': 'Large'}],
            'attributeValues': {'termAttributeValues': [{'id': 1, 'name': 'Storlek', 'values': ['50']}]},
            'longDescription': '<p>Axelbredd 46 cm</p><p>Ärmlängd 64 cm</p>'}
    assert tradera.photos(item) == ['https://img.tradera.net/a_l.jpg']
    text = tradera.listing_text(item)
    assert 'Storlek: 50' in text and 'Axelbredd 46 cm\nÄrmlängd 64 cm' in text
    assert tradera.photos({'id': 1, 'imageLinks': ['https://img.tradera.net/a.jpg']}) == ['https://img.tradera.net/a.jpg']


def test_search_pages_until_limit_and_sends_keys(monkeypatch, keys):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, dict(params or {}), headers))
        page = params['pageNumber']
        return Reply({'totalNumberOfItems': 5, 'totalNumberOfPages': 3,
                      'items': [{'id': page * 10 + n, 'shortDescription': f'kavaj {page}.{n}'} for n in range(2)]})
    monkeypatch.setattr(tradera.requests, 'get', fake_get)
    found = list(tradera.search('tweedkavaj', 302074, limit=3))
    assert [x['id'] for x in found] == [10, 11, 20]
    assert calls[0][0] == 'https://api.tradera.com/v4/search'
    assert calls[0][1] == {'query': 'tweedkavaj', 'pageNumber': 1, 'categoryId': 302074}
    assert calls[0][2]['X-App-Id'] == '1234' and calls[0][2]['X-App-Key'] == 'secret'


def test_search_stops_on_last_page_and_handles_no_hits(monkeypatch, keys):
    monkeypatch.setattr(tradera.requests, 'get', lambda *a, **k: Reply({'TotalNumberOfItems': 1, 'TotalNumberOfPages': 1,
                                                                        'Items': [{'Id': 5}]}))
    assert [x['Id'] for x in tradera.search('x', limit=40)] == [5]
    monkeypatch.setattr(tradera.requests, 'get', lambda *a, **k: Reply({'totalNumberOfItems': 0, 'items': None}))
    assert list(tradera.search('x')) == []


def test_unexpected_reply_rate_limit_and_missing_keys(monkeypatch, keys):
    monkeypatch.setattr(tradera.requests, 'get', lambda *a, **k: Reply({'something': []}))
    with pytest.raises(tradera.TraderaError, match='unexpected search reply'):
        list(tradera.search('x'))
    monkeypatch.setattr(tradera.requests, 'get', lambda *a, **k: Reply({}, status=429))
    with pytest.raises(tradera.RateLimited):
        list(tradera.search('x'))
    monkeypatch.delenv('TRADERA_APP_ID')
    with pytest.raises(tradera.TraderaError, match='TRADERA_APP_ID'):
        list(tradera.search('x'))


def test_search_plan_uses_swedish_terms_and_categories():
    items = [{'id': 'W005', 'category': 'Tailoring', 'search_terms': ['harris tweed sport coat']},
             {'id': 'W999', 'category': 'Footwear', 'search_terms': ['trickers boots']}]
    config = {'categories': {'Tailoring': 302074}, 'terms': {'W005': ['tweedkavaj herr']}}
    assert [(i['id'], q, c) for i, q, c in tradera.searches(items, config)] == [
        ('W005', 'tweedkavaj herr', 302074), ('W999', 'trickers boots', 0)]


def test_tradera_json_covers_the_plan():
    config = tradera.load_config()
    ids = {item['id'] for item in watcher.catalog()}
    assert set(config['terms']) <= ids
    assert all(terms and all(isinstance(t, str) and t.strip() for t in terms) for terms in config['terms'].values())


def test_search_tradera_ingests_and_filters(monkeypatch, tmp_path, keys):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(tradera, 'search', lambda query, category, limit: iter([REST_AUCTION, {**SOAP_BUY_NOW, 'ShortDescription': 'Dam byxor'}]))
    # W999 has no Swedish terms in tradera.json, so its one English term is used: one search.
    wardrobe = [{'id': 'W999', 'category': 'Tailoring', 'name': 'Heavy tweed sport coat', 'search_terms': ['x'],
                 'enabled': True, 'owned_quantity': 0, 'target_quantity': 1}]
    filters = {'enabled': True, 'defaults': {'exclude_title_terms': ['dam']}}
    with watcher.connect() as conn:
        stats = watcher.search_tradera(conn, wardrobe, 40, filters)
        assert stats['returned'] == 2 and stats['rejected'] == 1 and stats['new'] == 1
        row = conn.execute("SELECT title,price,currency,buying_options,url FROM listings WHERE item_id='tradera:654970712'").fetchone()
        assert row == ('Harris Tweed kavaj strl 50', 150.0, 'SEK', 'AUCTION', REST_AUCTION['itemUrl'])
        assert conn.execute("SELECT wardrobe_id FROM matches WHERE item_id='tradera:654970712'").fetchone() == ('W999',)


def test_analysis_fetches_full_tradera_listing(monkeypatch, keys):
    seen = {}
    monkeypatch.setattr(tradera, 'get_item', lambda key: {'id': 654970712, 'imageLinks': ['https://img.tradera.net/full.jpg'],
                                                          'longDescription': 'Axelbredd 46 cm'})

    def fake_read(photos, garment_type, title, text, key, model):
        seen.update(photos=photos, text=text, garment_type=garment_type)
        return [], '{"measurements": []}'
    monkeypatch.setattr(measure, 'read_measurements', fake_read)
    job = ('tradera:654970712', 'Harris Tweed kavaj', 'jacket', ['https://img.tradera.net/thumb.jpg'])
    photos, readings, raw = watcher._analyze_one(job, None, 'deepseek-key', 'model')
    assert photos == ['https://img.tradera.net/full.jpg'] and seen['garment_type'] == 'jacket'
    assert 'Axelbredd 46 cm' in seen['text']
