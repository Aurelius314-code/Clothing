"""Offline tests for two faults seen on Windows: the daily backup and the eBay search in watcher.py."""
import os
import sqlite3
import sys
import time
from contextlib import closing

import db_backup
import watcher


class TrackedConnection(sqlite3.Connection):
    opened = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_open = True
        TrackedConnection.opened.append(self)

    def close(self):
        self.is_open = False
        super().close()


def _database(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE notes (value TEXT)")
        conn.execute("INSERT INTO notes VALUES ('x')")
        conn.commit()


def test_backup_and_restore_close_every_file_before_moving_it(tmp_path, monkeypatch):
    """Windows cannot move or delete an open file (WinError 32): nothing may still be open when it does."""
    db = tmp_path / "wardrobe.sqlite3"
    _database(db)
    real_connect, real_replace = sqlite3.connect, os.replace
    TrackedConnection.opened = []
    monkeypatch.setattr(db_backup.sqlite3, "connect", lambda *a, **k: real_connect(*a, factory=TrackedConnection, **k))

    def replace(source, target):
        assert not [c for c in TrackedConnection.opened if c.is_open], "a database file is still open"
        real_replace(source, target)
    monkeypatch.setattr(db_backup.os, "replace", replace)

    snapshot = db_backup.create_backup(db, force=True)
    db_backup.restore_backup(db, snapshot)
    assert TrackedConnection.opened and not [c for c in TrackedConnection.opened if c.is_open]
    assert not list((tmp_path / "backups").glob(".snapshot-*"))


def test_stale_temporary_copies_are_cleared(tmp_path):
    db = tmp_path / "wardrobe.sqlite3"
    _database(db)
    backups = tmp_path / "backups"
    backups.mkdir()
    stale, fresh = backups / ".snapshot-old.sqlite3", backups / ".snapshot-new.sqlite3"
    stale.write_bytes(b"left by a failed backup")
    fresh.write_bytes(b"another backup in progress")
    hours_ago = time.time() - 2 * 3600
    os.utime(stale, (hours_ago, hours_ago))
    assert db_backup.create_backup(db, force=True)
    assert not stale.exists() and fresh.exists()


def test_watcher_runs_the_ebay_search(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setattr(watcher, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(watcher, "ebay_configured", lambda: True)
    monkeypatch.setattr(watcher, "token", lambda: "token")
    monkeypatch.setattr(watcher, "swedish_pickup", lambda: False)
    monkeypatch.setattr(watcher, "report", lambda conn: "report.html")
    searched = []

    def fake_search(conn, access_token, wardrobe, *args, **kwargs):
        searched.append((access_token, [item["id"] for item in wardrobe]))
        return {"new": 0}, {"rejected": 0}
    monkeypatch.setattr(watcher, "search_ebay", fake_search)
    monkeypatch.setattr(sys, "argv", ["watcher.py", "--source", "ebay", "--only", "W048,W049"])
    watcher.main()
    assert searched == [("token", ["W048", "W049"])]
