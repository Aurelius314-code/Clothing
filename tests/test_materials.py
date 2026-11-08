"""Offline tests for reading the fabric composition (DeepSeek reply -> listing_materials) and judging it."""
import json

import material
import measure
import watcher


def reply(*materials, measurements=()):
    return json.dumps({'measurements': list(measurements), 'materials': list(materials)})


def test_fibre_names_from_labels_and_other_languages():
    assert material.fibre_name('100% Pure New Wool') == 'wool'
    assert material.fibre_name("Lamb's wool") == 'lambswool'
    assert material.fibre_name('Lammull') == 'lambswool'
    assert material.fibre_name('BAUMWOLLE') == 'cotton'
    assert material.fibre_name('Polyamid') == 'nylon'
    assert material.fibre_name('Lycra') == 'elastane'
    assert material.fibre_name('Rayon') == 'viscose'
    assert material.fibre_name('merino wool') == 'merino'
    assert material.fibre_name('mystery fibre') == 'other'


def test_parse_materials_parts_percent_and_sources():
    found = measure.parse_materials(reply(
        {'part': 'Outer shell', 'fibre': 'Cotton', 'percent': '100%', 'source': 'Photo 7', 'confidence': 'high'},
        {'part': 'Lining', 'fibre': 'Viscose', 'percent': 100, 'source': 'photo 7', 'confidence': 'high'},
        {'fibre': 'polyester', 'percent': 150, 'source': 'text'},                 # impossible percent: dropped
        {'part': 'shell', 'fibre': '', 'percent': 10},                             # no fibre: dropped
        {'part': 'shell', 'fibre': 'cotton', 'percent': 100, 'source': 'text', 'confidence': 'low'}))  # less confident duplicate
    assert found == [
        {'part': 'shell', 'fibre': 'cotton', 'percent': 100.0, 'source': 'photo 7', 'confidence': 'high', 'raw': 'Cotton'},
        {'part': 'lining', 'fibre': 'viscose', 'percent': 100.0, 'source': 'photo 7', 'confidence': 'high', 'raw': 'Viscose'}]


def test_parse_materials_tolerates_missing_or_broken_replies():
    assert measure.parse_materials('{"measurements": []}') == []
    assert measure.parse_materials('not json at all') == []
    assert measure.parse_materials('{"materials": "100% wool"}') == []
    no_part = measure.parse_materials(reply({'fibre': 'Polyester', 'percent': None, 'source': 'text'}))
    assert no_part[0]['part'] == 'shell' and no_part[0]['percent'] is None


def test_judge_counts_only_the_outer_fabric():
    assert material.judge([('shell', 'cotton', 100), ('lining', 'polyester', 100)]) == (
        material.NATURAL, 'ytterstoff 100 % bomull')
    status, text = material.judge([('shell', 'polyester', 83), ('shell', 'nylon', 15), ('shell', 'elastane', 2)])
    assert status == material.SYNTHETIC and text == 'ytterstoff 83 % polyester, 15 % nylon, 2 % elastan'
    assert material.judge([('shell', 'wool', 80), ('shell', 'viscose', 20)])[0] == material.REGENERATED
    assert material.judge([('shell', 'wool', 90), ('shell', 'nylon', 10)])[0] == material.SYNTHETIC
    assert material.judge([('shell', 'wool', None)]) == (material.NATURAL, 'ytterstoff ull')
    assert material.judge([('shell', 'other', 100)])[0] == material.UNKNOWN
    assert material.judge([('lining', 'viscose', 100)]) == (
        material.UNKNOWN, 'ytterstoffet er ikke oppgitt (fôr 100 % viskose)')
    assert material.judge([])[0] == material.UNKNOWN


def test_analysis_stores_materials_and_text_and_reanalyses_older_listings(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        for item_id in ('v1|1|0', 'v1|2|0', 'v1|3|0'):
            conn.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES(?, 'Cord jacket', '2026-11-07', '2026-11-07')",
                         (item_id,))
            conn.execute("INSERT INTO matches(item_id,wardrobe_id) VALUES(?, 'W048')", (item_id,))
        watcher.save_analysis(conn, 'v1|1|0', [], [], reply(
            {'part': 'shell', 'fibre': 'cotton', 'percent': 100, 'source': 'photo 7', 'confidence': 'high'}),
            text='Material: Cotton\nPit to pit 24"')
        watcher.save_analysis(conn, 'v1|2|0', [], [], reply(
            {'part': 'shell', 'fibre': 'polyester', 'percent': 83, 'source': 'text', 'confidence': 'high'}))
        # An analysis from before fabric reading existed.
        conn.execute("INSERT INTO listing_analysis(item_id,status,analyzed_at) VALUES('v1|3|0','ok','2026-10-27')")
        conn.commit()

        statuses = material.all_statuses(conn)
        assert statuses['v1|1|0'] == (material.NATURAL, 'ytterstoff 100 % bomull', ['photo 7'])
        assert statuses['v1|2|0'][0] == material.SYNTHETIC
        assert statuses['v1|3|0'] == (material.UNKNOWN, 'ikke lest ennå', [])
        assert conn.execute("SELECT listing_text FROM listing_analysis WHERE item_id='v1|1|0'").fetchone() == (
            'Material: Cotton\nPit to pit 24"',)
        monkeypatch.setattr(watcher, 'garment_types', lambda conn: {i: 'jacket' for i in ('v1|1|0', 'v1|2|0', 'v1|3|0')})
        assert [job[0] for job in watcher.pending_analysis(conn, 10)] == ['v1|3|0']

        # A failed analysis keeps the fabric read earlier; a new one replaces it.
        watcher.save_analysis(conn, 'v1|1|0', [], error='timeout')
        assert material.all_statuses(conn)['v1|1|0'][0] == material.NATURAL
        watcher.save_analysis(conn, 'v1|1|0', [], [], reply())
        assert material.all_statuses(conn)['v1|1|0'] == (material.UNKNOWN, 'ikke oppgitt i annonsen', [])


def test_prompt_asks_for_the_composition():
    intro, task = measure.build_prompt('jacket', 'Corduroy blazer', 'Material: Cotton')
    assert '"materials"' in task and 'care or composition label' in task and 'Never guess a fibre' in task


def test_a_blend_without_breakdown_is_not_natural(tmp_path, monkeypatch):
    """The Orvis blazer: "Outer Shell Material: Wool Blend" was read as plain wool."""
    assert material.blend_unaccounted([('shell', 'wool', None)], 'Outer Shell Material: Wool Blend\nFabric Type: Hopsack')
    assert material.blend_unaccounted([('shell', 'wool', 60)], 'British wool mix')
    assert material.blend_unaccounted([('shell', 'cotton', None)], 'Material: Bomullsblandning')
    assert not material.blend_unaccounted([('shell', 'wool', 100)], 'Wool blend? No, 100% wool label in photo 6')
    assert not material.blend_unaccounted([('shell', 'wool', None)], 'Material: Wool\nColour: Navy')
    assert not material.blend_unaccounted([('shell', 'wool', None)], 'Grå/svart melerad kavaj')
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'test.sqlite3')
    with watcher.connect() as conn:
        for item_id in ('v1|1|0', 'v1|2|0'):
            conn.execute("INSERT INTO listings(item_id,title,first_seen,last_seen) VALUES(?, 'Blazer', 'x', 'x')", (item_id,))
        watcher.save_analysis(conn, 'v1|1|0', [], [], reply({'part': 'shell', 'fibre': 'wool', 'source': 'text'}),
                              text='Outer Shell Material: Wool Blend')
        watcher.save_analysis(conn, 'v1|2|0', [], [], reply({'part': 'shell', 'fibre': 'wool', 'source': 'text'}),
                              text='Material: Wool')
        statuses = material.all_statuses(conn)
        assert statuses['v1|1|0'][0] == material.UNKNOWN and '«blend»' in statuses['v1|1|0'][1]
        assert statuses['v1|2|0'][0] == material.NATURAL
    intro, task = measure.build_prompt('jacket', 'Blazer', 'Outer Shell Material: Wool Blend')
    assert '"fibre": "unknown"' in task
