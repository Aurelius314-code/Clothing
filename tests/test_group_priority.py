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


ONLY_ITEMS = [
    {"id": "W016", "category": "Knitwear", "priority": 1, "enabled": True, "owned_quantity": 0, "target_quantity": 3},
    {"id": "W044", "category": "Knitwear", "priority": 2, "enabled": True, "owned_quantity": 1, "target_quantity": 1},
    {"id": "W009", "category": "Trousers", "priority": 1, "enabled": True, "owned_quantity": 0, "target_quantity": 1},
]


def test_only_by_id_includes_targets_already_owned():
    assert [x["id"] for x in group_priority.only(ONLY_ITEMS, {}, "w044")] == ["W044"]


def test_only_by_category_keeps_only_wanted_targets():
    assert [x["id"] for x in group_priority.only(ONLY_ITEMS, {}, "Knitwear")] == ["W016"]


def test_only_mixes_ids_and_categories_in_search_order():
    result = group_priority.only(ONLY_ITEMS, {"Trousers": 1, "Knitwear": 2}, "W044, knitwear, W009")
    assert [x["id"] for x in result] == ["W009", "W016", "W044"]


def test_only_rejects_unknown_names():
    import pytest
    with pytest.raises(ValueError, match="W999"):
        group_priority.only(ONLY_ITEMS, {}, "W044,W999")
    with pytest.raises(ValueError):
        group_priority.only(ONLY_ITEMS, {}, " , ")
