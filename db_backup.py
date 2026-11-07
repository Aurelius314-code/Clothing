"""Safe SQLite snapshots, retention, and guarded restore for the local wardrobe database."""
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DAILY_KEEP = 14
WEEKLY_KEEP = 8
MONTHLY_KEEP = 6
STALE_TEMPORARY_SECONDS = 3600


def backup_dir(db):
    return Path(db).parent / "backups"


# "with sqlite3.connect(...)" only commits; it does not close the file. Windows cannot move or delete
# a file that is still open (WinError 32), so every connection here is closed explicitly.
def _integrity(path):
    with closing(sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)) as conn:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def _copy(source_uri, target):
    """Copy a database with SQLite's online backup API and close both files."""
    with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination)


def _remove_stale_temporaries(directory, prefix):
    """Temporary copies left by an interrupted or failed backup (an hour old: not one in progress)."""
    for path in Path(directory).glob(f"{prefix}*.sqlite3"):
        try:
            if time.time() - path.stat().st_mtime > STALE_TEMPORARY_SECONDS:
                path.unlink()
        except OSError:
            pass


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
    _remove_stale_temporaries(directory, ".snapshot-")
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", suffix=".sqlite3", dir=directory)
    os.close(fd)
    try:
        # Read-only, unless a journal is left from an interrupted write: SQLite must roll it back
        # first, which needs write access (the app would do the same when it opens the file).
        read_only = "" if Path(str(db) + "-journal").exists() else "?mode=ro"
        _copy(f"file:{db.resolve().as_posix()}{read_only}", temporary)
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
    _remove_stale_temporaries(db.parent, ".restore-")
    fd, temporary = tempfile.mkstemp(prefix=".restore-", suffix=".sqlite3", dir=db.parent)
    os.close(fd)
    try:
        _copy(f"file:{snapshot.as_posix()}?mode=ro", temporary)
        if not _integrity(temporary):
            raise RuntimeError("Restored database failed integrity check")
        os.replace(temporary, db)
        for suffix in ("-wal", "-shm", "-journal"):  # an old journal would be replayed into the restored file
            sidecar = Path(str(db) + suffix)
            if sidecar.exists():
                sidecar.unlink()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _main(args):
    """python db_backup.py list   |   python db_backup.py restore <backup file name>

    For when the app itself can't open the database. Close the app and watcher.py first.
    """
    import sys
    db = Path(__file__).with_name("wardrobe.sqlite3")
    if args[:1] == ["list"]:
        for path in list_backups(db):
            print(path.name)
        return
    if len(args) == 2 and args[0] == "restore":
        matches = [p for p in list_backups(db) if p.name == Path(args[1]).name]
        if not matches:
            sys.exit(f"No backup named {args[1]!r}. See: python db_backup.py list")
        restore_backup(db, matches[0])
        print(f"Restored {db.name} from {matches[0].name}. The database as it was is kept as a new backup.")
        return
    sys.exit(_main.__doc__)


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
