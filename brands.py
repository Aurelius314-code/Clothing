"""Brand selector: listings from brands on the blacklist in brands.json are stopped before they are
stored and before anything is sent to DeepSeek.

Only `excluded_brands.hard` is used so far. Tiers, penalties and keywords in brands.json are data for
scoring later. A missing brands.json stops nothing.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).with_name('brands.json')
REJECT_NOTE = 'Merke på svartelista: {}'


class Excluded(Exception):
    """Raised before an analysis when the full listing's Brand field is on the blacklist."""

    def __init__(self, brand):
        super().__init__(brand)
        self.brand = brand


def normalize(text):
    """Lower case, no accents, & as 'and', no punctuation: "Tricker's" -> "trickers", "H&M" -> "h and m"."""
    text = unicodedata.normalize('NFKD', str(text or '').casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace('&', ' and ')
    text = re.sub(r"['’`´]", '', text)
    text = re.sub(r'[^\w\s]|_', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _phrase(words):
    return re.compile(rf'(?<!\w){re.escape(words)}(?!\w)')


class Blacklist:
    def __init__(self, config):
        excluded = (config or {}).get('excluded_brands') or {}
        field_only = {normalize(x) for x in excluded.get('brand_field_only') or []}
        styles = [normalize(p.replace('{brand}', ' BRANDSLOT ')) for p in
                  ((config or {}).get('matching') or {}).get('style_patterns') or []]
        self.brands = []  # (display name, phrase, style phrases, title too?)
        for name in excluded.get('hard') or []:
            words = normalize(name)
            if words:
                looks_like = [_phrase(s.replace('brandslot', words)) for s in styles if 'brandslot' in s]
                self.brands.append((name, _phrase(words), looks_like, words not in field_only))
        title_words = [normalize(n) for n, _, _, in_title in self.brands if in_title]
        self.any_in_title = re.compile('|'.join(rf'(?<!\w){re.escape(w)}(?!\w)' for w in title_words)) if title_words else None

    def match(self, title='', brand_field=''):
        """The blacklisted brand a listing is from, or None.

        The Brand field is checked for every name. The title is checked too, except for names that are
        ordinary words (brand_field_only, such as "Next"), and a name only counts when it isn't part of a
        comparison such as "Zara style" or "not Primark".
        """
        field = normalize(brand_field)
        if field:
            for name, phrase, _, _ in self.brands:
                if phrase.search(field):
                    return name
        text = normalize(title)
        if not text or not self.any_in_title or not self.any_in_title.search(text):
            return None
        for name, phrase, looks_like, in_title in self.brands:
            if not in_title or not phrase.search(text):
                continue
            rest = text
            for style in looks_like:
                rest = style.sub(' ', rest)
            if phrase.search(rest):
                return name
        return None


@lru_cache(maxsize=4)
def _load(path, mtime):
    return Blacklist(json.loads(Path(path).read_text(encoding='utf-8')))


def blacklist(path=CONFIG):
    """The blacklist from brands.json, read again whenever the file changes. Empty when there is no file."""
    path = Path(path)
    if not path.exists():
        return Blacklist({})
    return _load(str(path), path.stat().st_mtime_ns)


def excluded_brand(title='', brand_field='', path=CONFIG):
    return blacklist(path).match(title, brand_field)


def brand_field(item):
    """The seller's Brand from a full eBay listing: the brand field, else the Brand item specific."""
    if item.get('brand'):
        return item['brand']
    for aspect in item.get('localizedAspects') or []:
        if str(aspect.get('name', '')).casefold() == 'brand' and aspect.get('value'):
            return aspect['value']
    return ''
