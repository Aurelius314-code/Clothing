"""Conservative, configurable eBay prefilters. Unknown attributes are retained."""
import json
from pathlib import Path

CONFIG = Path(__file__).with_name("search_filters.json")


def load_config(path=CONFIG):
    if not Path(path).exists():
        return {"enabled": False, "defaults": {}, "garment_types": {}}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("search_filters.json must contain an object")
    return data


def options_for(config, garment_type):
    if not config.get("enabled", False):
        return {}
    return {**config.get("defaults", {}), **config.get("garment_types", {}).get(garment_type or "", {})}


def ebay_filters(options, country):
    """Only filters supported without ambiguous currency/category assumptions."""
    filters = [f"deliveryCountry:{country}"]
    maximum = options.get("max_item_price")
    currency = options.get("price_currency")
    if maximum is not None and currency:
        if float(maximum) <= 0 or not str(currency).isalpha() or len(currency) != 3:
            raise ValueError("Invalid price filter")
        filters.extend([f"price:[..{float(maximum):g}]", f"priceCurrency:{currency.upper()}"])
    if options.get("buying_options") in ("FIXED_PRICE", "AUCTION"):
        filters.append(f"buyingOptions:{{{options['buying_options']}}}")
    return ",".join(filters)


def accept_item(item, options):
    """Fail open when eBay omits data. No model calls or photo downloads."""
    if not options:
        return True, "accepted"
    title = (item.get("title") or "").casefold()
    excluded = [str(word).casefold() for word in options.get("exclude_title_terms", []) if str(word).strip()]
    if any(word in title for word in excluded):
        return False, "excluded_title"
    required = [str(word).casefold() for word in options.get("require_any_title_terms", []) if str(word).strip()]
    if required and not any(word in title for word in required):
        return False, "required_title_missing"
    maximum = options.get("max_item_price")
    currency = options.get("price_currency")
    price = item.get("price") or item.get("currentBidPrice") or {}
    if maximum is not None and currency and price.get("currency") == str(currency).upper():
        try:
            if float(price["value"]) > float(maximum):
                return False, "over_budget"
        except (ValueError, TypeError, KeyError):
            pass
    # Seller size labels are notoriously unreliable for vintage; do not hard-reject unknown sizes.
    return True, "accepted"
