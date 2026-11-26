"""Offline tests for the brand blacklist (brands.py and brands.json): no keys, network or real database needed."""
import json

import pytest

import brands
import measure
import tradera
import watcher

CONFIG = {
    'matching': {'style_patterns': ['{brand} style', 'not {brand}', 'like {brand}', 'similar to {brand}', '{brand} stil']},
    'excluded_brands': {'hard': ['Primark', 'Zara', 'H&M', 'Next', 'Jack & Jones', 'BoohooMAN'],
                        'brand_field_only': ['Next']},
}


@pytest.fixture
def blacklist():
    return brands.Blacklist(CONFIG)


def test_normalize():
    assert brands.normalize("Tricker's") == 'trickers'
    assert brands.normalize('H&M') == brands.normalize('H & M') == 'h and m'
    assert brands.normalize('St. Michael') == 'st michael'
    assert brands.normalize('Schöffel  Country') == 'schoffel country'
    assert brands.normalize(None) == ''


def test_title_names_a_blacklisted_brand(blacklist):
    assert blacklist.match('PRIMARK wool mix coat XL') == 'Primark'
    assert blacklist.match('H & M lambswool jumper') == 'H&M'
    assert blacklist.match('Jack and Jones parka') == 'Jack & Jones'
    assert blacklist.match('boohooMAN check blazer') == 'BoohooMAN'


def test_whole_words_only(blacklist):
    assert blacklist.match('Zarathustra tweed jacket') is None
    assert blacklist.match('Harris Tweed jacket') is None
    assert blacklist.match('') is None and blacklist.match(None) is None


def test_comparisons_are_not_the_brand(blacklist):
    assert blacklist.match('Barbour waxed jacket - not Primark!') is None
    assert blacklist.match('Zara style trench coat') is None
    assert blacklist.match('Wool coat, fits like Zara M') is None
    assert blacklist.match('Zara-stil kappa') is None
    assert blacklist.match('Zara coat, Zara style') == 'Zara'  # named outright as well


def test_ordinary_words_count_only_in_the_brand_field(blacklist):
    assert blacklist.match('Harris Tweed jacket next day dispatch') is None
    assert blacklist.match('Harris Tweed jacket', 'Next') == 'Next'
    assert blacklist.match('Wool coat', 'River Island') is None  # not on this test list
    assert blacklist.match('Wool coat', 'Zara Man') == 'Zara'


def test_brand_field_from_full_listing():
    assert brands.brand_field({'brand': 'Primark'}) == 'Primark'
    assert brands.brand_field({'localizedAspects': [{'name': 'Size', 'value': 'L'},
                                                    {'name': 'Brand', 'value': 'Zara'}]}) == 'Zara'
    assert brands.brand_field({}) == ''


def test_file_is_read_and_missing_file_stops_nothing(tmp_path):
    path = tmp_path / 'brands.json'
    assert brands.excluded_brand('Primark coat', path=path) is None
    path.write_text(json.dumps(CONFIG), encoding='utf-8')
    assert brands.excluded_brand('Primark coat', path=path) == 'Primark'


def test_shipped_brands_json():
    """The real brands.json: known cheap brands stop, good ones and ordinary words don't."""
    assert brands.excluded_brand('Primark mens coat') == 'Primark'
    assert brands.excluded_brand('George at Asda wool blazer') == 'George at Asda'
    assert brands.excluded_brand('Vintage George Cleverley brogues') is None
    assert brands.excluded_brand('Barbour Beaufort wax jacket next day post') is None
    assert brands.excluded_brand('Burton tweed jacket 1970s') is None  # Burton is only penalised
    assert brands.excluded_brand('Dior New Look era wool coat') is None
    assert brands.excluded_brand('Wool coat', 'New Look') == 'New Look'
    assert brands.excluded_brand('Harris Tweed jacket', 'Next') is None  # Next is only penalised


def test_search_skips_blacklisted_titles(monkeypatch, tmp_path):
    monkeypatch.setenv('TRADERA_APP_ID', '1234')
    monkeypatch.setenv('TRADERA_APP_KEY', 'secret')
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    found = [{'id': 1, 'shortDescription': 'Harris Tweed kavaj', 'itemType': 3, 'buyItNowPrice': 300},
             {'id': 2, 'shortDescription': 'Zara kavaj ull', 'itemType': 3, 'buyItNowPrice': 200}]
    monkeypatch.setattr(tradera, 'search', lambda query, category, limit: iter(found))
    wardrobe = [{'id': 'W999', 'category': 'Tailoring', 'name': 'Heavy tweed sport coat', 'search_terms': ['x'],
                 'enabled': True, 'owned_quantity': 0, 'target_quantity': 1}]
    with watcher.connect() as conn:
        stats = watcher.search_tradera(conn, wardrobe, 40)
        assert stats['returned'] == 2 and stats['excluded_brand'] == 1 and stats['new'] == 1
        assert [row[0] for row in conn.execute('SELECT item_id FROM listings')] == ['tradera:1']


def test_stored_listings_are_rejected_unless_reviewed(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        for item_id, title in (('v1|1|0', 'Primark wool coat'), ('v1|2|0', 'Primark coat I saved'),
                               ('v1|3|0', 'Crombie overcoat'), ('v1|4|0', 'Zara blazer')):
            conn.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES(?,?,'2026-11-26','2026-11-26')",
                         (item_id, title))
            conn.execute("INSERT INTO matches(item_id,wardrobe_id) VALUES(?, 'W048')", (item_id,))
        conn.execute("INSERT INTO listing_reviews VALUES('v1|2|0','saved','keep')")
        conn.execute("INSERT INTO listing_reviews VALUES('v1|4|0','unreviewed','my note')")
        assert watcher.reject_blacklisted(conn) == 2
        reviews = {r[0]: r[1:] for r in conn.execute('SELECT item_id,status,notes FROM listing_reviews')}
        assert reviews == {'v1|1|0': ('rejected', 'Merke på svartelista: Primark'), 'v1|2|0': ('saved', 'keep'),
                           'v1|4|0': ('rejected', 'my note')}
        monkeypatch.setattr(watcher, 'garment_types', lambda conn: {f'v1|{n}|0': 'coat' for n in range(1, 5)})
        assert sorted(job[0] for job in watcher.pending_analysis(conn, 10)) == ['v1|2|0', 'v1|3|0']
        assert watcher.reject_blacklisted(conn) == 0  # nothing left to reject


def test_brand_field_stops_the_analysis_before_deepseek(monkeypatch):
    monkeypatch.setattr(watcher, 'get_item', lambda item_id, token: {'brand': 'Primark', 'image': {'imageUrl': 'https://i/x.jpg'}})

    def must_not_run(*args):
        raise AssertionError('DeepSeek was called')
    monkeypatch.setattr(measure, 'read_measurements', must_not_run)
    job = ('v1|7|0', 'Harris Tweed jacket', 'jacket', ['https://i/thumb.jpg'])
    with pytest.raises(brands.Excluded) as caught:
        watcher._analyze_one(job, 'ebay-token', 'deepseek-key', 'model')
    assert caught.value.brand == 'Primark'

    monkeypatch.setattr(measure, 'read_measurements', lambda *args: ([], '{"measurements": []}'))
    assert watcher._analyze_one(job, 'ebay-token', 'deepseek-key', 'model', check_brand=False)[1] == []


def test_analysis_run_rejects_and_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(measure, 'api_key', lambda: 'deepseek-key')
    monkeypatch.setattr(watcher, 'get_item', lambda item_id, token: {'brand': 'Primark' if item_id == 'v1|1|0' else 'Crombie'})
    monkeypatch.setattr(measure, 'read_measurements', lambda *args: ([], '{"measurements": []}'))
    with watcher.connect() as conn:
        for item_id, title in (('v1|1|0', 'Wool overcoat'), ('v1|2|0', 'Crombie overcoat'), ('v1|3|0', 'Primark coat')):
            conn.execute("INSERT INTO listings(item_id,title,image_url,first_seen,last_seen) VALUES(?,?,'https://i/x.jpg','2026-11-26','2026-11-26')",
                         (item_id, title))
        monkeypatch.setattr(watcher, 'garment_types', lambda conn: {f'v1|{n}|0': 'coat' for n in range(1, 4)})
        stats = watcher.analyze_pending(conn, 'ebay-token', workers=1)
        assert stats == {'analyzed': 1, 'with_measurements': 0, 'failed': 0, 'excluded_brand': 2}
        assert dict(conn.execute('SELECT item_id,status FROM listing_reviews')) == {'v1|1|0': 'rejected', 'v1|3|0': 'rejected'}
        assert [row[0] for row in conn.execute('SELECT item_id FROM listing_analysis')] == ['v1|2|0']
