"""Offline tests: a failed backup never stops the app, restore removes stale side files, and the
wardrobe plan is grouped by main category."""
import sqlite3

import db_backup
import plan_view
import watcher


def test_failed_backup_warns_but_database_still_opens(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'wardrobe.sqlite3')

    def broken(db):
        raise sqlite3.DatabaseError('database disk image is malformed')
    monkeypatch.setattr(db_backup, 'automatic_backup', broken)
    with watcher.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM listings').fetchone() == (0,)
    assert 'malformed' in watcher.backup_error
    assert 'automatic backup' in capsys.readouterr().err
    monkeypatch.undo()
    monkeypatch.setattr(watcher, 'DB', tmp_path / 'wardrobe.sqlite3')
    with watcher.connect():
        assert watcher.backup_error is None


def test_restore_removes_an_old_journal(tmp_path):
    db = tmp_path / 'wardrobe.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE notes (value TEXT)')
        conn.execute("INSERT INTO notes VALUES ('kept')")
    snapshot = db_backup.create_backup(db, force=True)
    journal = tmp_path / 'wardrobe.sqlite3-journal'
    journal.write_bytes(b'left over from a crash')
    db_backup.restore_backup(db, snapshot)
    assert not journal.exists()
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT value FROM notes').fetchone() == ('kept',)


def test_command_line_restore(tmp_path, monkeypatch, capsys):
    db = tmp_path / 'wardrobe.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE notes (value TEXT)')
        conn.execute("INSERT INTO notes VALUES ('old')")
    snapshot = db_backup.create_backup(db, force=True)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE notes SET value='new'")
    monkeypatch.setattr(db_backup, '__file__', str(tmp_path / 'db_backup.py'))
    db_backup._main(['list'])
    assert snapshot.name in capsys.readouterr().out
    db_backup._main(['restore', snapshot.name])
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT value FROM notes').fetchone() == ('old',)


ITEMS = [
    {'id': 'W009', 'category': 'Trousers', 'name': 'Mid-grey flannel trousers', 'owned_quantity': 0, 'target_quantity': 1, 'priority': 1, 'enabled': True},
    {'id': 'W041', 'category': 'Trousers', 'name': 'Chinos', 'owned_quantity': 1, 'target_quantity': 2, 'priority': 1, 'enabled': True},
    {'id': 'W013', 'category': 'Trousers', 'name': 'Corduroy trousers', 'owned_quantity': 1, 'target_quantity': 1, 'priority': 2, 'enabled': True},
    {'id': 'W001', 'category': 'Outerwear', 'name': 'Heavy overcoat', 'owned_quantity': 1, 'target_quantity': 1, 'priority': 1, 'enabled': True},
    {'id': 'W016', 'category': 'Knitwear', 'name': 'Shetland crewnecks', 'owned_quantity': 0, 'target_quantity': 3, 'priority': 1, 'enabled': False},
]


def test_plan_grouped_by_category_in_priority_order():
    groups = plan_view.grouped(ITEMS, {'Knitwear': 1, 'Trousers': 2})
    assert [c for c, _ in groups] == ['Knitwear', 'Trousers', 'Outerwear']
    assert [i['name'] for i in dict(groups)['Trousers']] == ['Chinos', 'Mid-grey flannel trousers', 'Corduroy trousers']
    assert [c for c, _ in plan_view.grouped(ITEMS)] == ['Outerwear', 'Trousers', 'Knitwear']  # usual order
    assert plan_view.summary('Trousers', dict(groups)['Trousers']) == 'Bukser · 2 av 4 eid · 3 plagg · 2 søkes etter'
    assert plan_view.summary('Knitwear', dict(groups)['Knitwear']).endswith('0 søkes etter')


def test_plan_edits_saved_back_within_limits():
    items = [dict(i) for i in ITEMS]
    rows = plan_view.rows([i for i in items if i['category'] == 'Trousers'])
    assert plan_view.apply_edits(items, rows) == []  # nothing edited, nothing changed
    rows[0].update({'Eid': 1, 'Aktivt søk': False})
    rows[1].update({'Eid': 2, 'Prioritet': 0, 'Ønsket': None})  # priority 0 -> 1, emptied 'Ønsket' kept
    changed = plan_view.apply_edits(items, rows)
    assert changed == ['Mid-grey flannel trousers', 'Chinos']
    by_id = {i['id']: i for i in items}
    assert by_id['W009']['owned_quantity'] == 1 and by_id['W009']['enabled'] is False
    assert (by_id['W041']['owned_quantity'], by_id['W041']['priority'], by_id['W041']['target_quantity']) == (2, 1, 2)
    assert by_id['W001'] == ITEMS[3]  # other categories untouched


def test_every_plan_category_has_a_norwegian_name():
    assert {i['category'] for i in watcher.catalog()} <= set(plan_view.CATEGORY_LABELS)
