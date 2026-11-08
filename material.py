"""Fabric composition: which fibres a listing is made of, and whether its outer fabric is natural.

DeepSeek reads the composition from care labels in the photos and from the listing text in the
same request as the measurements (measure.parse_materials). This module names the fibres and
judges the outer fabric (the shell). Linings, pocketing and trims don't count: a wool coat with a
polyester lining is still a wool coat.
"""
import re

NATURAL, REGENERATED, SYNTHETIC, UNKNOWN = 'natural', 'regenerated', 'synthetic', 'unknown'
STATUSES = (NATURAL, REGENERATED, UNKNOWN, SYNTHETIC)
LABELS = {NATURAL: '🟢 Naturfiber', REGENERATED: '🟡 Med viskose e.l.', UNKNOWN: '⚪ Stoff ukjent – sjekk lappen',
          SYNTHETIC: '🔴 Syntetisk'}
# Shown by default in the listings tab: synthetic outer fabrics are hidden.
DEFAULT_SHOWN = (NATURAL, REGENERATED, UNKNOWN)

PARTS = ('shell', 'lining', 'other')
PART_LABELS = {'shell': 'ytterstoff', 'lining': 'fôr', 'other': 'annet'}

# Canonical fibre -> (kind, Norwegian name). Regenerated fibres are made from wood pulp: not
# synthetic, but not what you are looking for in an outer fabric either.
FIBRES = {
    'wool': (NATURAL, 'ull'), 'lambswool': (NATURAL, 'lammeull'), 'merino': (NATURAL, 'merinoull'),
    'cashmere': (NATURAL, 'kasjmir'), 'mohair': (NATURAL, 'mohair'), 'alpaca': (NATURAL, 'alpakka'),
    'camel': (NATURAL, 'kamelhår'), 'angora': (NATURAL, 'angora'), 'yak': (NATURAL, 'jakull'),
    'vicuna': (NATURAL, 'vikunja'), 'silk': (NATURAL, 'silke'), 'cotton': (NATURAL, 'bomull'),
    'linen': (NATURAL, 'lin'), 'hemp': (NATURAL, 'hamp'), 'ramie': (NATURAL, 'ramie'), 'leather': (NATURAL, 'skinn'),
    'viscose': (REGENERATED, 'viskose'), 'modal': (REGENERATED, 'modal'), 'lyocell': (REGENERATED, 'lyocell'),
    'cupro': (REGENERATED, 'cupro'), 'acetate': (REGENERATED, 'acetat'), 'triacetate': (REGENERATED, 'triacetat'),
    'polyester': (SYNTHETIC, 'polyester'), 'nylon': (SYNTHETIC, 'nylon'), 'acrylic': (SYNTHETIC, 'akryl'),
    'elastane': (SYNTHETIC, 'elastan'), 'polypropylene': (SYNTHETIC, 'polypropylen'),
    'polyurethane': (SYNTHETIC, 'polyuretan'), 'modacrylic': (SYNTHETIC, 'modakryl'),
    'metallic': (SYNTHETIC, 'metallfiber'),
}

# Other names on labels and in listings (English, Swedish, German, French, Italian, Spanish).
ALIASES = {
    'pure new wool': 'wool', 'new wool': 'wool', 'virgin wool': 'wool', 'pure wool': 'wool', 'worsted': 'wool',
    'shetland': 'wool', 'shetland wool': 'wool', 'tweed': 'wool', 'ull': 'wool', 'ren ull': 'wool', 'ny ull': 'wool',
    'wolle': 'wool', 'schurwolle': 'wool', 'laine': 'wool', 'lana': 'wool', 'lane': 'wool', 'wo': 'wool', 'wv': 'wool',
    'lambs wool': 'lambswool', "lamb's wool": 'lambswool', 'lamb wool': 'lambswool', 'lammull': 'lambswool',
    'lammwolle': 'lambswool', 'merino wool': 'merino', 'merinoull': 'merino',
    'kashmir': 'cashmere', 'kaschmir': 'cashmere', 'cachemire': 'cashmere', 'cashmir': 'cashmere',
    'camel hair': 'camel', 'camelhair': 'camel', 'kamelhår': 'camel', 'alpacka': 'alpaca', 'alpaka': 'alpaca',
    'bomull': 'cotton', 'baumwolle': 'cotton', 'coton': 'cotton', 'cotone': 'cotton', 'algodón': 'cotton',
    'algodon': 'cotton', 'pure cotton': 'cotton', 'co': 'cotton', 'moleskin': 'cotton',
    'flax': 'linen', 'leinen': 'linen', 'lino': 'linen', 'siden': 'silk', 'seide': 'silk', 'soie': 'silk',
    'seta': 'silk', 'se': 'silk', 'suede': 'leather', 'mocka': 'leather', 'läder': 'leather',
    'rayon': 'viscose', 'viskos': 'viscose', 'viskose': 'viscose', 'viscosa': 'viscose', 'vi': 'viscose',
    'cv': 'viscose', 'tencel': 'lyocell', 'acetat': 'acetate',
    'polyamide': 'nylon', 'polyamid': 'nylon', 'pa': 'nylon', 'polyester fibre': 'polyester', 'pes': 'polyester',
    'pl': 'polyester', 'poly': 'polyester', 'spandex': 'elastane', 'lycra': 'elastane', 'elastan': 'elastane',
    'elasthan': 'elastane', 'ea': 'elastane', 'el': 'elastane', 'akryl': 'acrylic', 'acryl': 'acrylic',
    'polyacrylic': 'acrylic', 'pan': 'acrylic', 'pu': 'polyurethane', 'polyurethan': 'polyurethane',
    'metallised': 'metallic', 'metallized': 'metallic', 'lurex': 'metallic',
}
_WORDS = sorted({*FIBRES, *ALIASES}, key=len, reverse=True)  # longest first: "lambswool" before "wool"


def fibre_name(raw):
    """The canonical fibre for a name read from a label, or 'other' when it is not recognised."""
    text = re.sub(r'[\d%.,()*:;]+', ' ', str(raw or '').lower()).strip()
    text = re.sub(r'\s+', ' ', text)
    if text in FIBRES:
        return text
    if text in ALIASES:
        return ALIASES[text]
    for word in _WORDS:
        if len(word) > 3 and re.search(rf'\b{re.escape(word)}\b', text):
            return ALIASES.get(word, word)
    return 'other'


# "Wool Blend", "British wool mix", "ullblandning": one fibre named, the rest left unsaid (often polyester).
BLEND = re.compile(r'(wool|cotton|cashmere|linen|silk|mohair|alpaca|ull|bomull|siden|lin)s?[ -]?'
                   r'(blend|mix|blandning|mischung)|\b(blend|mix)(ed)? (of )?(wool|cotton)', re.IGNORECASE)


def blend_unaccounted(rows, text):
    """True when the listing calls the fabric a blend but the outer fabric read adds up to less than 95 %."""
    if not text or not BLEND.search(text):
        return False
    return sum(percent or 0 for part, _, percent in rows if part == 'shell') < 95


def kind(fibre):
    return FIBRES.get(fibre, (UNKNOWN, ''))[0]


def describe(fibre, percent):
    name = FIBRES.get(fibre, (UNKNOWN, fibre))[1]
    return f'{percent:g} % {name}' if percent is not None else name


def judge(rows):
    """(status, text) for one listing. rows: [(part, fibre, percent)].

    Only the outer fabric counts. Any synthetic fibre in it makes it synthetic; otherwise any
    regenerated fibre (viscose and similar) gives REGENERATED; a fibre that was not recognised,
    or no outer fabric at all, gives UNKNOWN.
    """
    shell = [(fibre, percent) for part, fibre, percent in rows if part == 'shell' and (percent is None or percent > 0)]
    if not shell:
        others = [f'{PART_LABELS.get(part, part)} {describe(fibre, percent)}' for part, fibre, percent in rows]
        return UNKNOWN, ('ytterstoffet er ikke oppgitt' + (f' ({", ".join(others)})' if others else ''))
    kinds = {kind(fibre) for fibre, _ in shell}
    status = (SYNTHETIC if SYNTHETIC in kinds else REGENERATED if REGENERATED in kinds
              else UNKNOWN if UNKNOWN in kinds else NATURAL)
    shell.sort(key=lambda fp: -(fp[1] if fp[1] is not None else 0))
    return status, 'ytterstoff ' + ', '.join(describe(fibre, percent) for fibre, percent in shell)


def all_statuses(conn):
    """item_id -> (status, text, sources) for every listing, from the listing_materials table."""
    rows, sources = {}, {}
    for item_id, part, fibre, percent, source in conn.execute(
            'SELECT item_id,part,fibre,percent,source FROM listing_materials'):
        rows.setdefault(item_id, []).append((part, fibre, percent))
        if source and part == 'shell':
            sources.setdefault(item_id, set()).add(source)
    read, texts = set(), {}
    for item_id, status, materials_read, listing_text in conn.execute(
            'SELECT item_id,status,materials_read,listing_text FROM listing_analysis'):
        if status == 'ok' and materials_read == 1:
            read.add(item_id)
        texts[item_id] = listing_text
    statuses = {}
    for (item_id,) in conn.execute('SELECT item_id FROM listings'):
        if item_id in rows:
            status, text = judge(rows[item_id])
            if status == NATURAL and blend_unaccounted(rows[item_id], texts.get(item_id)):
                status, text = UNKNOWN, text + ' + mer: selgeren skriver «blend» uten å si hva resten er'
        else:
            status, text = UNKNOWN, ('ikke oppgitt i annonsen' if item_id in read else 'ikke lest ennå')
        statuses[item_id] = (status, text, sorted(sources.get(item_id, ())))
    return statuses
