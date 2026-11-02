import listing_inspector


def test_full_listing_url():
    assert listing_inspector.item_number("https://www.ebay.com/itm/800191207354?var=&mkevt=1") == "800191207354"
    assert listing_inspector.item_number("https://www.ebay.com/itm/wool-jumper/317521940472") == "317521940472"


def test_raw_number_and_invalid_domain():
    assert listing_inspector.item_number("800191207354") == "800191207354"
    assert listing_inspector.item_number("https://notebay.com/itm/800191207354") is None


def test_api_lookup_uses_legacy_endpoint(monkeypatch):
    calls = {}
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"title": "Vintage wool jumper", "itemId": "v1|800191207354|0"}
    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["params"] = kwargs["params"]
        return Response()
    monkeypatch.setattr(listing_inspector.requests, "get", fake_get)
    number, item = listing_inspector.inspect("800191207354", "token", lambda token: {"Authorization": "Bearer token"})
    assert number == "800191207354"
    assert calls["url"].endswith("/get_item_by_legacy_id")
    assert calls["params"] == {"legacy_item_id": "800191207354"}
    assert item["title"] == "Vintage wool jumper"
