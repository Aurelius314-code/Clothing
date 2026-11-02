"""Safe SQLite snapshots, retention, and guarded restore for the local wardrobe database."""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DAILY_KEEP = 14
WEEKLY_KEEP = 8
MONTHLY_KEEP = 6


def backup_dir(db):
    return Path(db).parent / "backups"


def _integrity(path):
    with sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True) as conn:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def create_backup(db, directory=None, *, force=False, now=None):
    """Use SQLite's online backup API; never replace an existing snapshot."""
    db = Path(db)
    if not db.is_file():
        return None
    directory = Path(directory) if directory else backup_dir(db)
    directory.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")
    if not force:
        today = now.strftime("%Y%m%d")
        if any(directory.glob(f"{db.stem}_{today}_*.sqlite3")):
            return None
    target = directory / f"{db.stem}_{stamp}.sqlite3"
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", suffix=".sqlite3", dir=directory)
    os.close(fd)
    try:
        with sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True) as source:
            with sqlite3.connect(temporary) as destination:
                source.backup(destination)
        if not _integrity(temporary):
            raise RuntimeError("SQLite integrity check failed for new backup")
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def list_backups(db, directory=None):
    db = Path(db)
    directory = Path(directory) if directory else backup_dir(db)
    return sorted(directory.glob(f"{db.stem}_????????_??????_??????.sqlite3"), reverse=True) if directory.exists() else []


def prune_backups(db, directory=None):
    """Keep newest 14 daily, 8 weekly, 6 monthly buckets, plus newest snapshot."""
    snapshots = list_backups(db, directory)
    keep = set(snapshots[:1])
    for length, limit in ((8, DAILY_KEEP), (6, WEEKLY_KEEP), (4, MONTHLY_KEEP)):
        seen = set()
        for path in snapshots:
            stamp = path.name[len(Path(db).stem) + 1:][:8]
            try:
                date = datetime.strptime(stamp, "%Y%m%d")
            except ValueError:
                continue
            bucket = (date.strftime("%G-W%V") if length == 6
                      else date.strftime("%Y-%m") if length == 4 else stamp)
            if bucket not in seen and len(seen) < limit:
                seen.add(bucket)
                keep.add(path)
    for path in snapshots:
        if path not in keep:
            path.unlink()
    return len(snapshots) - len(keep)


def automatic_backup(db):
    """Once per UTC day when launched; exceptions prevent unsafe startup/migration."""
    result = create_backup(db)
    if result:
        prune_backups(db)
    return result


def restore_backup(db, snapshot):
    """Validate snapshot, protect current DB, then atomically restore while DB is closed."""
    db = Path(db)
    snapshot = Path(snapshot).resolve()
    if snapshot not in [p.resolve() for p in list_backups(db)]:
        raise ValueError("Snapshot must be one of the managed backups")
    if not _integrity(snapshot):
        raise RuntimeError("Selected snapshot failed SQLite integrity check")
    if db.exists():
        create_backup(db, force=True)
    fd, temporary = tempfile.mkstemp(prefix=".restore-", suffix=".sqlite3", dir=db.parent)
    os.close(fd)
    try:
        with sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True) as source:
            with sqlite3.connect(temporary) as destination:
                source.backup(destination)
        if not _integrity(temporary):
            raise RuntimeError("Restored database failed integrity check")
        os.replace(temporary, db)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db) + suffix)
            if sidecar.exists():
                sidecar.unlink()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
