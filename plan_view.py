"""The wardrobe plan grouped by main category, for the 🧥 Garderobe tab.

Kept apart from app.py so the grouping and the saving of edits can be tested without Streamlit.
"""

# Main categories in wardrobe.json, with the names shown in the app, in the order used when no
# group priority is set (🏷️ Gruppeprioritet).
CATEGORY_LABELS = {
    'Outerwear': 'Yttertøy', 'Tailoring': 'Dress og jakker', 'Trousers': 'Bukser', 'Knitwear': 'Strikk',
    'Shirts': 'Skjorter', 'Footwear': 'Sko', 'Accessories': 'Tilbehør', 'Basics': 'Basisplagg',
}

# Table columns in the app -> wardrobe.json fields that can be edited there.
EDITABLE = {'Eid': 'owned_quantity', 'Ønsket': 'target_quantity', 'Prioritet': 'priority', 'Aktivt søk': 'enabled'}


def label(category):
    return CATEGORY_LABELS.get(category, category)


def grouped(items, priorities=None):
    """[(category, [items])] in group-priority order (then the usual order), items by priority then name."""
    priorities = priorities or {}
    usual = list(CATEGORY_LABELS)
    groups = {}
    for item in items:
        groups.setdefault(item.get('category') or 'Annet', []).append(item)
    order = sorted(groups, key=lambda c: (priorities.get(c, 5), usual.index(c) if c in usual else len(usual), c))
    return [(c, sorted(groups[c], key=lambda i: (int(i.get('priority', 5)), i.get('name', '')))) for c in order]


def summary(category, items):
    """One line for a collapsed category, e.g. 'Bukser · 1 av 18 eid · 14 plagg · 11 søkes etter'."""
    owned = sum(int(i.get('owned_quantity', 0)) for i in items)
    wanted = sum(int(i.get('target_quantity', 0)) for i in items)
    searching = sum(bool(i.get('enabled')) and int(i.get('owned_quantity', 0)) < int(i.get('target_quantity', 0))
                    for i in items)
    return f'{label(category)} · {owned} av {wanted} eid · {len(items)} plagg · {searching} søkes etter'


def rows(items):
    """Table rows for one category."""
    return [{'ID': i['id'], 'Plagg': i.get('name', ''), 'Eid': int(i.get('owned_quantity', 0)),
             'Ønsket': int(i.get('target_quantity', 0)), 'Prioritet': int(i.get('priority', 5)),
             'Aktivt søk': bool(i.get('enabled')), 'Notater': i.get('notes', '')} for i in items]


def apply_edits(items, edited_rows):
    """Copy edited table rows back into the wardrobe items. Returns the names of the items that changed.

    Numbers are kept within the same limits as before (counts 0-100, priority 1-10), and an emptied
    cell keeps the value it had.
    """
    def number(value, before, low, high):
        return before if value is None else min(high, max(low, int(value)))

    by_id = {i['id']: i for i in items}
    changed = []
    for row in edited_rows:
        item = by_id.get(row.get('ID'))
        if item is None:
            continue
        new = {'owned_quantity': number(row.get('Eid'), item.get('owned_quantity', 0), 0, 100),
               'target_quantity': number(row.get('Ønsket'), item.get('target_quantity', 0), 0, 100),
               'priority': number(row.get('Prioritet'), item.get('priority', 5), 1, 10),
               'enabled': bool(row.get('Aktivt søk'))}
        if any(item.get(field) != value for field, value in new.items()):
            item.update(new)
            changed.append(item.get('name', item['id']))
    return changed
