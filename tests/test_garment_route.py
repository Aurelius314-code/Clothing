"""Offline tests: coats and outer jackets found by blazer searches go to a coat target or are left out."""
import garment_route
import tradera
import watcher

KINDS = {'W001': 'coat', 'W002': 'coat', 'W003': 'coat', 'W004': 'coat',
         'W048': 'jacket', 'W049': 'jacket', 'W050': 'jacket', 'W008': 'waistcoat'}


def route(title, wid='W050'):
    return garment_route.route(title, wid, KINDS)


def test_coats_go_to_their_own_targets():
    # Titles as they came back from the cord, double-breasted and wool sport coat searches.
    assert route("Men's Black Wool Duffle Coat Hooded Vintage Trench Parka Winter Overcoat") == 'W002'
    assert route('Christian Dior Trenchcoat / Herr 40R', 'W049') == 'W004'
    assert route('Kasy of Sweden, trenchcoat, herrkappa, mörkblå, dubbelknäppt, bälte, strl L', 'W049') == 'W004'
    assert route('Herrrock, The Golden Tailor by Junex, dubbelknäppt långrock, vintage, svart', 'W049') == 'W001'
    assert route('Vintage Oscar Jacobson Dubbelknäppt Kashmir/Ullrock C52 mörkblå – Made in Sweden', 'W049') == 'W001'
    assert route('Barbour Bedale waxed jacket olive XL', 'W048') == 'W003'


def test_outerwear_without_a_target_is_left_out():
    for title in ('Lacoste Pea Coat Mens 3XL Navy Blue Double Breasted Sport BH1525 Jacket',
                  'Stone Island Parka / Herr L',
                  'Mid Atlantic Tweed Coat Mens Small Green Keepers Shooting Hunting Field Jacket',
                  'M&S Jacket Mens XXL Italian Moleskin Utility Field Workwear Coat Bomber Emmetex',
                  "Vintage 60s Campus D'Italia Moleskin Front Wool Knit Cardigan Jacket USA Mens L",
                  'C.P. Company Kappa / Herr L–XL',
                  'Lardini beige jacka, storlek S',
                  'Retro vintage jacka herr manchesterjacka Design Michel Morau'):
        assert route(title, 'W048') is None, title


def test_blazers_and_sport_coats_stay():
    for title in ('Vintage St Michael Double Breasted Blazer Mens Size 44R Navy Pure Wool Jacket',
                  'Ted Baker Men 38 R Thomas Double Breasted Sport Jacket Coat Brown Textured Wool',
                  'Vintage Faconnable Hybrid Wool Sport/Travel Coat With Goat Skin Elbow Patch Sz L',
                  'Kavaj/jacka i ull, grå, herr 52',
                  'KappAhl kavaj i ull, marinblå',
                  'Moss 1898 Blazer Mens 42R Navy Blue 100% Cotton Moleskin Jacket',
                  'Vintage 1995 Mac Hugh University Shop Double Breasted Blazer Suit Jacket 0537'):
        assert route(title) == 'W050', title


def test_only_jacket_targets_are_sorted():
    assert route('Vintage Gloverall Duffle Coat Navy', 'W002') == 'W002'
    assert route('Tweed waistcoat with field jacket pockets', 'W008') == 'W008'
    # A coat target that is not in the plan (or switched off): the coat is left out.
    assert garment_route.route('Burberry trench coat', 'W050', {'W050': 'jacket'}) is None


def test_plan_targets_used_for_coats_are_coats():
    kinds = garment_route.kinds(watcher.catalog())
    assert all(kinds.get(target) == 'coat' for _, target in garment_route.COATS)


def _add(conn, item_id, title, wid, status=None):
    conn.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES(?,?,'2026-11-07','2026-11-07')",
                 (item_id, title))
    conn.execute('INSERT INTO matches(item_id,wardrobe_id) VALUES(?,?)', (item_id, wid))
    if status:
        conn.execute("INSERT INTO listing_reviews(item_id,status,notes) VALUES(?,?,'')", (item_id, status))


def test_stored_coats_are_moved_once(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        _add(conn, 'a', 'Christian Dior Trenchcoat / Herr 40R', 'W049')
        _add(conn, 'b', 'Stone Island Parka / Herr L', 'W049')
        _add(conn, 'c', 'Lacoste Pea Coat Mens 3XL', 'W049', status='saved')
        _add(conn, 'd', 'Vintage St Michael Double Breasted Blazer Navy', 'W049')
        conn.execute("DELETE FROM meta WHERE key='rerouted_coats_v1'")  # as in a database from before this change
        watcher._reroute_coats(conn, watcher.catalog())
        matches = dict(conn.execute('SELECT item_id, wardrobe_id FROM matches'))
        assert matches == {'a': 'W004', 'd': 'W049'}
        reviews = dict(conn.execute('SELECT item_id, status FROM listing_reviews'))
        assert reviews == {'b': 'rejected', 'c': 'saved'}  # your own review is kept
        # Runs once: a coat you file under a jacket target yourself afterwards stays there.
        _add(conn, 'e', 'Burberry trench coat', 'W050')
        watcher._reroute_coats(conn, watcher.catalog())
        assert conn.execute("SELECT wardrobe_id FROM matches WHERE item_id='e'").fetchone() == ('W050',)


def test_searches_sort_results_before_storing(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    found = [{'itemId': 'v1|1|0', 'title': 'Vintage Harris Tweed Sport Coat 44R'},
             {'itemId': 'v1|2|0', 'title': 'Vintage Gloverall Duffle Coat Navy'},
             {'itemId': 'v1|3|0', 'title': 'Barbour quilted gilet'}]
    monkeypatch.setattr(watcher, 'fetch', lambda *a, **k: iter(found))
    wardrobe = [{'id': 'W050', 'category': 'Tailoring', 'name': 'Single-breasted wool sport coat', 'search_terms': ['x']}]
    with watcher.connect() as conn:
        stats, prefilter = watcher.search_ebay(conn, 'token', wardrobe, country='NO')
        assert prefilter['not_a_jacket'] == 1 and stats['moved'] == 1 and stats['new'] == 2
        assert dict(conn.execute('SELECT item_id, wardrobe_id FROM matches')) == {'v1|1|0': 'W050', 'v1|2|0': 'W002'}
        assert not conn.execute("SELECT 1 FROM listings WHERE item_id='v1|3|0'").fetchone()

    monkeypatch.setattr(watcher, 'DB', tmp_path / 'tradera.sqlite3')
    monkeypatch.setattr(tradera, 'search', lambda query, category, limit: iter([
        {'id': 11, 'shortDescription': 'Tweedkavaj herr 52', 'itemType': 'PureBuyItNow', 'buyItNowPrice': 400,
         'itemUrl': 'https://www.tradera.com/item/1/11/x'},
        {'id': 12, 'shortDescription': 'Trenchcoat herr beige', 'itemType': 'PureBuyItNow', 'buyItNowPrice': 300,
         'itemUrl': 'https://www.tradera.com/item/1/12/x'},
        {'id': 13, 'shortDescription': 'Lardini jacka herr', 'itemType': 'PureBuyItNow', 'buyItNowPrice': 300,
         'itemUrl': 'https://www.tradera.com/item/1/13/x'}]))
    monkeypatch.setattr(watcher, 'swedish_pickup', lambda: False)
    with watcher.connect() as conn:
        stats = watcher.search_tradera(conn, wardrobe, 40, {}, max_queries=1)  # W050 has three Swedish terms
        assert stats['not_a_jacket'] == 1 and stats['moved'] == 1 and stats['new'] == 2
        assert dict(conn.execute('SELECT item_id, wardrobe_id FROM matches')) == {
            'tradera:11': 'W050', 'tradera:12': 'W004'}
