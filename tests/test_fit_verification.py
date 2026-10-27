"""Offline regression tests for verification-aware fit verdicts and application imports."""
import importlib.util
import sqlite3
from pathlib import Path

import fit
import measure
import watcher


def test_application_import_dependencies_present():
    for module in ("fit", "measure", "watcher"):
        assert importlib.util.find_spec(module) is not None
    assert callable(measure.garment_type_for)
    assert callable(fit.all_verdicts)
    assert callable(watcher.garment_types)


def test_unverified_readings_cannot_generate_green_or_red():
    targets = {"trousers": {"waist": (45, 47)}}
    for status in ("provisional", "seller_unverified", "legacy_unverified", "unknown"):
        for value in (46, 30, 60):
            verdict = fit.judge_listing("trousers", [("waist", value, "high", status)], targets)
            assert verdict.colour == fit.GREY
            assert verdict.per_reading["waist"][0] == fit.GREY


def test_human_verified_readings_retain_fit_assessment():
    targets = {"trousers": {"waist": (45, 47)}}
    good = fit.judge_listing("trousers", [("waist", 46, "high", "human_verified")], targets)
    bad = fit.judge_listing("trousers", [("waist", 30, "high", "human_verified")], targets)
    assert good.per_reading["waist"][0] == fit.GREEN
    assert bad.colour == fit.RED


def test_legacy_database_migration_keeps_measurements(tmp_path, monkeypatch):
    db = tmp_path / "wardrobe.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE listing_measurements (
            item_id TEXT NOT NULL, name TEXT NOT NULL, value_cm REAL NOT NULL,
            raw_value REAL, raw_unit TEXT, flat INTEGER, source TEXT,
            confidence TEXT, note TEXT DEFAULT '', PRIMARY KEY(item_id, name))""")
        conn.execute("INSERT INTO listing_measurements(item_id,name,value_cm,confidence) VALUES('test','waist',46,'high')")
    monkeypatch.setattr(watcher, "DB", str(db))
    with watcher.connect() as conn:
        row = conn.execute("SELECT value_cm,verification_status FROM listing_measurements WHERE item_id='test'").fetchone()
        assert row == (46, "legacy_unverified")
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fit_targets'").fetchone()
