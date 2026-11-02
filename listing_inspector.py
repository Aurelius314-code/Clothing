"""Inspect one eBay listing through the official Browse API, without scraping HTML."""
import re
from urllib.parse import urlparse, unquote
import requests

ITEM_PATH = re.compile(r"/itm/(?:[^/?#]+/)?(\d{9,15})(?:[/?#]|$)")
DIGITS = re.compile(r"^\d{9,15}$")


def item_number(value):
    value = (value or "").strip()
    if DIGITS.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not (
        parsed.hostname == "ebay.com" or (parsed.hostname or "").endswith(".ebay.com")
        or parsed.hostname == "ebay.co.uk" or (parsed.hostname or "").endswith(".ebay.co.uk")
    ):
        return None
    match = ITEM_PATH.search(unquote(parsed.path) + "/")
    return match.group(1) if match else None


def inspect(value, access_token, headers, resolve_short=None):
    number = item_number(value)
    if not number and resolve_short:
        resolved = resolve_short(value)
        number = item_number(resolved)
    if not number:
        raise ValueError("Could not find an eBay item number. Paste a full ebay.com/itm/... URL.")
    url = "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id"
    response = requests.get(url, headers=headers(access_token),
                            params={"legacy_item_id": number}, timeout=45)
    response.raise_for_status()
    return number, response.json()


def summary(item):
    return {
        "title": item.get("title", ""),
        "url": item.get("itemWebUrl", ""),
        "description": item.get("description", ""),
        "aspects": item.get("localizedAspects") or [],
        "condition": item.get("condition", ""),
        "price": item.get("price") or item.get("currentBidPrice") or {},
    }
