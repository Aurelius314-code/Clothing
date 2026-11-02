"""Marketplace identification for non-eBay vintage clothing listings.

This module does not scrape third-party sites. Import metadata from a seller
description or an authorized API separately.
"""
import hashlib
from urllib.parse import urlparse

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
    parsed = urlparse(url.strip())
    canonical = parsed.hostname.lower() + parsed.path.rstrip("/")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return marketplace.lower().replace(" ", "_") + ":" + digest
