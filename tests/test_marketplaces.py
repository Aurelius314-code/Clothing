import marketplaces


def test_supported_markets():
    urls = {
        "https://www.tradera.com/item/343837/753582030/ullkofta": "Tradera",
        "https://www.sellpy.com/item/123": "Sellpy",
        "https://www.vestiairecollective.com/men-clothing/123": "Vestiaire Collective",
        "https://www.grailed.com/listings/123": "Grailed",
        "https://www.vinted.fr/items/123": "Vinted",
        "https://www.kleinanzeigen.de/s-anzeige/123": "Kleinanzeigen",
    }
    for url, expected in urls.items():
        assert marketplaces.identify(url) == expected
        assert marketplaces.listing_key(url)


def test_tracking_query_does_not_change_identity():
    url = "https://www.tradera.com/item/343837/753582030/ullkofta"
    assert marketplaces.listing_key(url) == marketplaces.listing_key(url + "?utm_source=app")


def test_reject_lookalike_domain():
    assert marketplaces.identify("https://tradera.com.evil.example/item/1") is None
    assert marketplaces.identify("file:///tmp/listing") is None
