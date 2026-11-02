"""Offline tests for checking measurements by hand (✔️ Kontroller mål) and how the traffic light uses them."""
import fit
import watcher

READING = {'name': 'pit_to_pit', 'value_cm': 55.9, 'raw_value': 22, 'raw_unit': 'in', 'flat': True,
           'source': 'text', 'confidence': 'medium', 'note': ''}
TARGETS = {'coat': {'pit_to_pit': (55, 57), 'shoulders': (45, 47)}}


def rows(conn, item_id='tradera:1'):
    return {r[0]: r[1:] for r in conn.execute(
        'SELECT name,value_cm,source,confidence,verification_status,note FROM listing_measurements WHERE item_id=?', (item_id,))}


def verdict(conn, item_id='tradera:1'):
    readings = [(n, v, c, s) for n, (v, src, c, s, note) in rows(conn, item_id).items()]
    return fit.judge_listing('coat', readings, TARGETS)


def test_check_correct_add_remove_and_uncheck(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        watcher.save_analysis(conn, 'tradera:1', [], [READING, {**READING, 'name': 'sleeve', 'value_cm': 66.0, 'source': 'photo 2'}], '{}')
        assert rows(conn)['pit_to_pit'][3] == 'seller_unverified' and rows(conn)['sleeve'][3] == 'provisional'
        assert verdict(conn).colour == fit.GREY

        changed = watcher.save_checked_measurements(conn, 'tradera:1', 'coat', {
            'pit_to_pit': (55.9, True),      # confirmed as it is
            'sleeve': (None, False),         # wrong reading removed
            'shoulders': (45.7, False),      # missed by the analysis, typed in
            'waist': (None, False),          # nothing there, nothing happens
            'not_a_measurement': (1, True)})
        assert changed == 3
        saved = rows(conn)
        assert 'sleeve' not in saved and 'waist' not in saved and 'not_a_measurement' not in saved
        assert saved['pit_to_pit'][2:4] == ('high', 'human_verified')
        assert saved['shoulders'][1:4] == ('manual', 'high', 'human_verified')
        assert verdict(conn).colour == fit.GREEN

        watcher.save_checked_measurements(conn, 'tradera:1', 'coat', {'pit_to_pit': (60.0, False)})
        assert rows(conn)['pit_to_pit'][0] == 60.0 and rows(conn)['pit_to_pit'][3] == 'human_verified'
        assert 'rettet manuelt fra 55.9 cm' in rows(conn)['pit_to_pit'][4]
        assert verdict(conn).colour == fit.RED

        watcher.save_checked_measurements(conn, 'tradera:1', 'coat', {'pit_to_pit': (60.0, False), 'shoulders': (45.7, False)})
        assert rows(conn)['pit_to_pit'][3] == 'seller_unverified' and rows(conn)['shoulders'][3] == 'provisional'
        assert watcher.save_checked_measurements(conn, 'tradera:1', 'coat', {'pit_to_pit': (60.0, False)}) == 0


def test_new_analysis_keeps_checked_measurements(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        watcher.save_analysis(conn, 'tradera:1', [], [READING], '{}')
        watcher.save_checked_measurements(conn, 'tradera:1', 'coat', {'pit_to_pit': (56.5, True)})
        watcher.save_analysis(conn, 'tradera:1', [], [{**READING, 'value_cm': 50.0}, {**READING, 'name': 'sleeve', 'value_cm': 66.0}], '{}')
        saved = rows(conn)
        assert saved['pit_to_pit'][0] == 56.5 and saved['pit_to_pit'][3] == 'human_verified'
        assert saved['sleeve'][3] == 'seller_unverified'


def test_unchecked_reading_stays_grey_but_shows_preliminary_colour():
    good = fit.judge_listing('coat', [('pit_to_pit', 56, 'high', 'seller_unverified')], TARGETS)
    bad = fit.judge_listing('coat', [('pit_to_pit', 70, 'medium', 'provisional')], TARGETS)
    unsure = fit.judge_listing('coat', [('pit_to_pit', 56, 'low', 'provisional')], TARGETS)
    assert good.colour == bad.colour == unsure.colour == fit.GREY
    assert 'foreløpig 🟢' in good.reasons[0] and 'foreløpig 🔴' in bad.reasons[0]
    assert 'foreløpig' not in unsure.reasons[0]
