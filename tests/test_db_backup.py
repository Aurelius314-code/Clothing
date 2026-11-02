import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import db_backup


def _database(path, value):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS notes (value TEXT)")
        conn.execute("DELETE FROM notes")
        conn.execute("INSERT INTO notes VALUES (?)", (value,))


def _value(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT value FROM notes").fetchone()[0]


def test_daily_backup_and_forced_backup(tmp_path):
    db = tmp_path / "wardrobe.sqlite3"
    _database(db, "original")
    date = datetime(2026, 11, 2, tzinfo=timezone.utc)
    first = db_backup.create_backup(db, now=date)
    assert first and first.exists()
    _database(db, "changed")
    assert db_backup.create_backup(db, now=date + timedelta(hours=1)) is None
    second = db_backup.create_backup(db, force=True, now=date + timedelta(hours=1))
    assert _value(first) == "original"
    assert _value(second) == "changed"


def test_restore_validated_and_preserves_pre_restore_copy(tmp_path):
    db = tmp_path / "wardrobe.sqlite3"
    _database(db, "before")
    snapshot = db_backup.create_backup(db, force=True)
    _database(db, "after")
    db_backup.restore_backup(db, snapshot)
    assert _value(db) == "before"
    assert any(_value(p) == "after" for p in db_backup.list_backups(db))


def test_restore_rejects_unknown_snapshot(tmp_path):
    db = tmp_path / "wardrobe.sqlite3"
    other = tmp_path / "other.sqlite3"
    _database(db, "safe")
    _database(other, "bad")
    with pytest.raises(ValueError):
        db_backup.restore_backup(db, other)
    assert _value(db) == "safe"


def test_retention_keeps_recent_buckets(tmp_path):
    db = tmp_path / "wardrobe.sqlite3"
    _database(db, "safe")
    base = datetime(2026, 11, 2, tzinfo=timezone.utc)
    for days in range(90):
        db_backup.create_backup(db, force=True, now=base - timedelta(days=days))
    removed = db_backup.prune_backups(db)
    assert removed > 0
    assert len(db_backup.list_backups(db)) < 90
    assert len(db_backup.list_backups(db)) >= 14
