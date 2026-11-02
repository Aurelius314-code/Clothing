import group_priority


def test_category_order_precedes_item_order():
    items = [
        {"category": "Outerwear", "priority": 1, "enabled": True, "owned_quantity": 0, "target_quantity": 1},
        {"category": "Knitwear", "priority": 3, "enabled": True, "owned_quantity": 0, "target_quantity": 1},
        {"category": "Knitwear", "priority": 1, "enabled": True, "owned_quantity": 0, "target_quantity": 1},
    ]
    result = group_priority.search_order(items, {"Knitwear": 1, "Outerwear": 5})
    assert result == [items[2], items[1], items[0]]


def test_completed_items_are_excluded():
    items = [{"category": "Knitwear", "priority": 1, "enabled": True, "owned_quantity": 1, "target_quantity": 1}]
    assert group_priority.search_order(items, {}) == []


def test_priority_round_trip(tmp_path):
    path = tmp_path / "priorities.json"
    group_priority.save({"Knitwear": 1, "Outerwear": 8}, path)
    assert group_priority.load(path) == {"Knitwear": 1, "Outerwear": 8}
