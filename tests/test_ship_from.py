"""Offline tests: the seller's country is stored, shown and filtered on."""
import sqlite3

import ship_from
import tradera
import watcher


def test_country_of_search_results():
    assert ship_from.country_of({'itemId': 'v1|1|0', 'itemLocation': {'postalCode': 'SW1', 'country': 'GB'}}) == 'GB'
    assert ship_from.country_of({'itemId': 'v1|2|0', 'itemLocation': {'country': 'us'}}) == 'US'
    assert ship_from.country_of({'itemId': 'v1|3|0'}) is None
    assert ship_from.country_of({'itemId': 'v1|4|0', 'itemLocation': {'country': 'UNKNOWN'}}) is None
    assert ship_from.country_of(tradera.to_listing({'id': 5, 'shortDescription': 'Kavaj'})) == 'SE'
    assert ship_from.name('GB') == 'Storbritannia' and ship_from.name('BR') == 'BR' and ship_from.name(None) == 'ukjent land'
    assert 'GB' in ship_from.EUROPE and 'NO' in ship_from.EUROPE and 'US' not in ship_from.EUROPE


def test_country_stored_and_kept_and_filtered(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        watcher.ingest(conn, {'itemId': 'v1|1|0', 'title': 'Navy blazer', 'itemLocation': {'country': 'GB'}}, 'W050')
        watcher.ingest(conn, {'itemId': 'v1|2|0', 'title': 'Navy blazer', 'itemLocation': {'country': 'US'}}, 'W050')
        watcher.ingest(conn, {'itemId': 'v1|3|0', 'title': 'Navy blazer'}, 'W050')
        # Found again without a location (for example from a manual add): the country already known stays.
        watcher.ingest(conn, {'itemId': 'v1|1|0', 'title': 'Navy blazer, price cut'}, 'W050')
        watcher.ingest(conn, tradera.to_listing({'id': 7, 'shortDescription': 'Ullkavaj herr'}), 'W050')
        countries = dict(conn.execute('SELECT item_id, item_country FROM listings'))
        assert countries == {'v1|1|0': 'GB', 'v1|2|0': 'US', 'v1|3|0': None, 'tradera:7': 'SE'}

        def shown(choice):
            condition, args = ship_from.sql_condition(choice)
            where = f'WHERE {condition}' if condition else ''
            return sorted(i for (i,) in conn.execute(f'SELECT l.item_id FROM listings l {where}', args))
        assert shown(ship_from.ALL) == ['tradera:7', 'v1|1|0', 'v1|2|0', 'v1|3|0']
        assert shown(ship_from.IN_EUROPE) == ['tradera:7', 'v1|1|0']
        assert shown(ship_from.OUTSIDE_EUROPE) == ['v1|2|0']


def test_older_tradera_listings_get_sweden(tmp_path, monkeypatch):
    db = tmp_path / 'test.sqlite3'
    with sqlite3.connect(db) as old:  # a database from before the column existed
        old.execute('''CREATE TABLE listings (item_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT, image_url TEXT,
            seller TEXT, price REAL, currency TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, fingerprint TEXT,
            notes TEXT DEFAULT '', status TEXT DEFAULT 'unreviewed')''')
        old.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES('tradera:9','Kavaj','x','x')")
        old.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES('v1|9|0','Blazer','x','x')")
    monkeypatch.setattr(watcher, 'DB', db)
    with watcher.connect() as conn:
        assert dict(conn.execute('SELECT item_id, item_country FROM listings')) == {'tradera:9': 'SE', 'v1|9|0': None}
