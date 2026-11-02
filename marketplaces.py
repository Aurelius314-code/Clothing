"""Marketplace identification for non-eBay vintage clothing listings.

This module does not scrape third-party sites. Import metadata from a seller
description or an authorized API separately.
"""
import hashlib
from urllib.parse import urlparse

import tradera

MARKETS = {
    "tradera.com": "Tradera",
    "sellpy.com": "Sellpy",
    "vestiairecollective.com": "Vestiaire Collective",
    "grailed.com": "Grailed",
    "vinted.fr": "Vinted",
    "vinted.de": "Vinted",
    "vinted.co.uk": "Vinted",
    "vinted.it": "Vinted",
    "vinted.es": "Vinted",
    "vinted.nl": "Vinted",
    "kleinanzeigen.de": "Kleinanzeigen",
}


def identify(url):
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    host = parsed.hostname.lower()
    for domain, label in MARKETS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return None


def listing_key(url):
    marketplace = identify(url)
    if not marketplace:
        raise ValueError("Unsupported marketplace URL")
    # A Tradera listing gets the same key as in Tradera's search ('tradera:<item number>'),
    # so importing it here and finding it in a search never stores it twice.
    known = tradera.item_key(url)
    if known:
        return known
    parsed = urlparse(url.strip())
    canonical = parsed.hostname.lower() + parsed.path.rstrip("/")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return marketplace.lower().replace(" ", "_") + ":" + digest
