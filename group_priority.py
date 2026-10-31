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


def search_order(items, priorities):
    """Lower rank = searched first; item priority breaks ties, preserving original order."""
    indexed = [(i, item) for i, item in enumerate(items) if item.get("enabled") and
               item.get("owned_quantity", 0) < item.get("target_quantity", 0)]
    return [item for _, item in sorted(indexed, key=lambda pair: (
        priorities.get(pair[1].get("category"), 5),
        pair[1].get("priority", 5),
        pair[0]))]
