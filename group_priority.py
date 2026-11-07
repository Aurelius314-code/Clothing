"""Independent wardrobe category priorities, used to schedule eBay searches."""
import json
import os
import tempfile
from pathlib import Path

PATH = Path(__file__).with_name("group_priorities.json")


def load(path=PATH):
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("group_priorities.json must be an object")
    return {str(k): int(v) for k, v in data.items() if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10}


def save(priorities, path=PATH):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".group-priority-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(priorities, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _ordered(indexed, priorities):
    return [item for _, item in sorted(indexed, key=lambda pair: (
        priorities.get(pair[1].get("category"), 5),
        pair[1].get("priority", 5),
        pair[0]))]


def _still_wanted(item):
    return item.get("enabled") and item.get("owned_quantity", 0) < item.get("target_quantity", 0)


def search_order(items, priorities):
    """Lower rank = searched first; item priority breaks ties, preserving original order."""
    return _ordered([(i, item) for i, item in enumerate(items) if _still_wanted(item)], priorities)


def only(items, priorities, names):
    """The targets for a narrower search: wardrobe IDs and/or category names, comma-separated.

    A target named by its ID is searched even when you already own enough of it or its search is
    switched off, so you can look for one more. A category gives the targets in it that are still
    wanted, as in the full search. Raises ValueError for a name that matches nothing.
    """
    given = [name.strip() for name in names.split(",") if name.strip()]
    wanted = [name.lower() for name in given]
    ids = {str(item.get("id", "")).lower() for item in items}
    categories = {str(item.get("category", "")).lower() for item in items}
    unknown = [name for name in given if name.lower() not in ids and name.lower() not in categories]
    if not wanted or unknown:
        raise ValueError("--only: no wardrobe target or category called " + (", ".join(unknown) or "(empty)")
                         + ". Use IDs such as W044 or categories such as Knitwear.")
    return _ordered([(i, item) for i, item in enumerate(items)
                     if str(item.get("id", "")).lower() in wanted
                     or (str(item.get("category", "")).lower() in wanted and _still_wanted(item))], priorities)
