"""No-network tests for the eBay prefilter layer."""
import search_prefilter as pf


def test_disabled_config_is_nonrestrictive():
    assert pf.options_for({"enabled": False, "garment_types": {"knitwear": {"max_item_price": 5}}}, "knitwear") == {}


def test_per_type_options_override_defaults():
    config = {"enabled": True, "defaults": {"max_item_price": 50, "price_currency": "GBP"},
              "garment_types": {"knitwear": {"max_item_price": 100}}}
    options = pf.options_for(config, "knitwear")
    assert options["max_item_price"] == 100
    assert pf.options_for(config, "trousers")["max_item_price"] == 50


def test_ebay_price_filter_requires_currency():
    assert pf.ebay_filters({"max_item_price": 100}, "NO") == "deliveryCountry:NO"
    assert pf.ebay_filters({"max_item_price": 100, "price_currency": "GBP"}, "NO") == (
        "deliveryCountry:NO,price:[..100],priceCurrency:GBP")


def test_local_filter_excludes_only_explicit_matches():
    options = {"exclude_title_terms": ["women"], "max_item_price": 100, "price_currency": "GBP"}
    assert not pf.accept_item({"title": "Women's jumper"}, options)[0]
    assert not pf.accept_item({"title": "Wool jumper", "price": {"value": "110", "currency": "GBP"}}, options)[0]
    assert pf.accept_item({"title": "Wool jumper", "price": {"value": "110", "currency": "USD"}}, options)[0]
    assert pf.accept_item({"title": "Wool jumper"}, options)[0]
