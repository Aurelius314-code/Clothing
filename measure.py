"""Reads garment measurements and fabric composition from eBay and Tradera listing photos and text
with DeepSeek's vision model.

The model only extracts what the listing shows. Converting to cm and comparing with your
own measurements happens locally, so your measurements are never sent anywhere.
"""
import base64
import html
import json
import os
import re

import requests

DEEPSEEK_URL = 'https://api.deepseek.com/v1/chat/completions'
DEFAULT_MODEL = 'deepseek-flash'
MAX_PHOTOS = 24  # eBay allows up to 24 photos per listing
BROWSER_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# Wardrobe categories in wardrobe.json -> the kind of measurements to look for.
# Coats are worn over a jacket, so they get their own targets. Accessories, footwear and
# basics are sold by size, so they are not analysed.
CATEGORY_TYPES = {'Outerwear': 'coat', 'Tailoring': 'jacket', 'Trousers': 'trousers',
                  'Knitwear': 'knitwear', 'Shirts': 'shirt'}
TYPE_LABELS = {'jacket': 'Jakker og dresser', 'coat': 'Frakker og yttertøy', 'waistcoat': 'Vester',
               'trousers': 'Bukser', 'knitwear': 'Strikk', 'shirt': 'Skjorter'}

# Measurement key -> how it is taken, as explained to the model (same method as the measuring sheet).
MEASUREMENTS = {
    'jacket': {
        'pit_to_pit': 'straight across the front from armpit seam to armpit seam, buttoned',
        'shoulders': 'across the back from the seam where one sleeve joins to the other',
        'sleeve': 'from the shoulder seam down the outside of the sleeve to the end of the cuff',
        'back_length': 'centre back, from the bottom of the collar seam to the hem',
        'waist': 'straight across at the narrowest point, around the top button',
    },
    'waistcoat': {
        'pit_to_pit': 'straight across the front from armpit to armpit, buttoned',
        'back_length': 'centre back, from the collar seam or neck to the hem',
        'waist': 'straight across at the narrowest point, buttoned',
    },
    'trousers': {
        'waist': 'across the top edge of the waistband, buttoned',
        'seat': 'across the widest part, around the bottom of the fly',
        'front_rise': 'from the crotch seam up to the top of the waistband at the front',
        'back_rise': 'from the crotch seam up to the top of the waistband at the back',
        'thigh': 'across one leg, about 2.5 cm (1 in) below the crotch',
        'inseam': 'from the crotch seam down the inside leg to the hem',
        'leg_opening': 'straight across the hem',
    },
    'knitwear': {
        'pit_to_pit': 'straight across the front from armpit to armpit',
        'length': 'from the highest point of the shoulder beside the collar, straight down to the hem',
        'sleeve': 'from the shoulder seam to the cuff end (raglan sleeves: from the centre back of the collar)',
        'shoulders': 'seam to seam across the back',
    },
    'shirt': {
        'collar': 'collar laid open flat, from the centre of the button to the far end of the buttonhole',
        'pit_to_pit': 'straight across the front from armpit seam to armpit seam',
        'sleeve': 'from the shoulder seam to the end of the cuff',
        'back_length': 'from the collar seam at the centre back to the hem',
    },
}

MEASUREMENTS['coat'] = dict(MEASUREMENTS['jacket'])

# Measurements taken across the garment. All-round values are halved so every width is stored flat.
WIDTHS = {'pit_to_pit', 'waist', 'seat', 'thigh', 'leg_opening'}

# How each measurement is taken, for the "Mine mål" tab (same method as the measuring sheet).
HELP = {'pit_to_pit': 'Rett over fra armhule til armhule, knappet', 'shoulders': 'Over ryggen, fra søm til søm der ermene sitter',
        'sleeve': 'Fra skuldersømmen ned til enden av mansjetten', 'back_length': 'Midt bak, fra kragesømmen til kanten nederst',
        'waist': 'Rett over der plagget er smalest / øverste kant av linningen', 'seat': 'Over det bredeste partiet, ved bunnen av gylfen',
        'front_rise': 'Fra skrittsømmen opp til toppen av linningen foran', 'back_rise': 'Fra skrittsømmen opp til toppen av linningen bak',
        'thigh': 'Over ett ben, ca. 2,5 cm under skrittet', 'inseam': 'Fra skrittsømmen ned langs innsiden til kanten',
        'leg_opening': 'Rett over benåpningen nederst', 'length': 'Fra høyeste punkt ved kragen rett ned til kanten',
        'collar': 'Kragen brettet ut: fra midten av knappen til ytterenden av knapphullet'}

LABELS = {'pit_to_pit': 'Brystvidde', 'shoulders': 'Skulderbredde', 'sleeve': 'Ermelengde',
          'back_length': 'Rygglengde', 'waist': 'Livvidde', 'seat': 'Setevidde',
          'front_rise': 'Livhøyde foran', 'back_rise': 'Livhøyde bak', 'thigh': 'Lårvidde',
          'inseam': 'Innerbenslengde', 'leg_opening': 'Benåpning', 'length': 'Lengde', 'collar': 'Krage'}
ORDER = list(LABELS)

EBAY_PHOTO = re.compile(r'^https://i\.ebayimg\.com/(?:thumbs/)?images/g/([^/?#]+)/s-l\d+(\.[a-z]+)', re.IGNORECASE)


def garment_type_for(wardrobe_item):
    """The measurement type for a wardrobe.json item, or None for things bought by size."""
    if 'waistcoat' in wardrobe_item.get('name', '').lower():
        return 'waistcoat'
    return CATEGORY_TYPES.get(wardrobe_item.get('category'))


class AnalysisError(Exception):
    """The analysis of one listing failed; it is retried on a later run."""


class AuthError(AnalysisError):
    """DeepSeek refused the key or the account is empty; no point trying more listings."""


def full_size_photo(url):
    """Turn an eBay thumbnail address (s-l225 and similar) into the 1600 px version of the same photo."""
    match = EBAY_PHOTO.match(url or '')
    return f'https://i.ebayimg.com/images/g/{match.group(1)}/s-l1600{match.group(2)}' if match else (url or '')


def photos_from_item(item):
    """All photos of a Browse API item (search result or full listing), full size, in listing order."""
    urls = [(item.get('image') or {}).get('imageUrl')]
    urls += [p.get('imageUrl') for p in item.get('thumbnailImages') or []]
    urls += [p.get('imageUrl') for p in item.get('additionalImages') or []]
    photos, seen = [], set()
    for url in urls:
        if not url or not url.startswith('https://'):
            continue
        url = full_size_photo(url)
        match = EBAY_PHOTO.match(url)
        photo_id = match.group(1) if match else url
        if photo_id not in seen:
            seen.add(photo_id)
            photos.append(url)
    return photos[:MAX_PHOTOS]


def _plain_text(markup, limit):
    text = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', markup or '')
    text = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h\d)>', '\n', text)
    text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\s*\n\s*', '\n', text).strip()
    return text[:limit]


def listing_text(item):
    """The seller's item specifics and description from a full Browse API listing, as plain text."""
    aspects = '\n'.join(f"{a.get('name')}: {a.get('value')}" for a in item.get('localizedAspects') or []
                        if a.get('name') and a.get('value'))
    description = _plain_text(item.get('description') or item.get('shortDescription') or '', 4000)
    parts = []
    if aspects:
        parts.append('Item specifics:\n' + aspects[:1500])
    if description:
        parts.append('Description:\n' + description)
    return '\n\n'.join(parts)


def build_prompt(garment_type, title, text, strict=False):
    """(text before the photos, text after the photos) for one listing."""
    wanted = MEASUREMENTS[garment_type]
    intro = (
        'You read garment measurements from a second-hand listing (eBay or the Swedish site Tradera). '
        'A buyer compares them with the measurements '
        'of clothes that fit him, so every number must say exactly what was measured.\n\n'
        f'Garment type: {garment_type}\nListing title: {title}\n\n'
        + (text + '\n\n' if text else '')
        + 'The listing photos follow, each introduced by its number. Some may show a tape measure laid across the garment.'
    )
    names = ', '.join(wanted)
    task = (
        'Report these measurements when the listing shows them on a tape or states them as measurements:\n'
        + '\n'.join(f'- {key}: {how}' for key, how in wanted.items())
        + '\n\nHow to read a tape photo:\n'
        '- The measurement is the reading on the tape where it meets the far edge of the garment. '
        'Other numbers printed along the tape are not measurements.\n'
        '- The tape should start at 0 at the near edge. If it starts elsewhere, subtract the starting value.\n'
        '- For photo measurements, check the tape zero/start, the garment endpoint, and that the scale is legible.\n'
        '- Set start_visible, end_visible, scale_legible to true only when each is clearly visible.\n'
        '- Set evidence_status to "verified" only when all three are true; otherwise "ambiguous".\n'
        + ('- If you cannot see where the tape starts or ends, do not report a numerical photo measurement. '
           'Do not return numerical photo measurements with ambiguous evidence.\n' if strict else
           '- If you cannot see where the tape starts or ends, give your best reading with confidence "low", '
           'evidence_status "ambiguous", and say why in the note.\n')
        + 
        '- If the garment is folded or stretched, or the tape runs at a slant, use confidence "medium" or "low" and say why.\n\n'
        'Other rules:\n'
        '- "flat" is true when the measurement goes one layer across a garment lying flat (most tape photos, '
        '"pit to pit", "flat waist"); false when it goes all the way round (for example "waist 34 inches" or "chest 42").\n'
        '- Label sizes such as "42R", "W34 L30", "Large" or "strl 50" are not measurements; leave them out.\n'
        '- Swedish listings: axelbredd = shoulders, ärmlängd/armlängd = sleeve, bröstvidd/bröstbredd or "armhåla till armhåla" = '
        'pit_to_pit, midja/midjevidd = waist, stuss/sätesvidd = seat, grenhöjd/gren fram = front_rise, '
        'gren bak = back_rise, innerbenslängd = inseam, lårvidd = thigh, benvidd/benöppning = leg_opening, '
        'längd/rygglängd/längd bak = length or back_length, krage/halsvidd = collar. "Liggande", "platt", "platt mätta" or "x2" means '
        'measured flat; on men\'s clothes a bröstvidd above about 80 cm or a midja above about 70 cm is almost '
        'certainly all the way round.\n'
        '- When the text and a photo disagree, report the photo reading and mention the text value in the note.\n'
        '- Leave out any measurement the listing does not show. Never estimate one.\n\n'
        'Also report the fabric composition, which the buyer uses to avoid synthetic fabrics:\n'
        '- Read it from any care or composition label you can see in the photos (for example "100% WOOL", '
        '"65% POLYESTER 35% COTTON", "SHELL: 100% COTTON LINING: 100% VISCOSE", "Pure New Wool"), and from the '
        'item specifics and description (for example "Material: Polyester", "Outer Shell Material: Wool").\n'
        '- One entry per fibre and part. "part" is "shell" for the outer fabric (also called main, body, outer, '
        'face, self, ytterstoff or tyg), "lining" for linings and pocketing (fôr, foder, Futter, doublure), '
        '"other" for trims, collars, ribbing, padding or filling. A composition with no part named is "shell".\n'
        '- "fibre" is the English fibre name as written or translated (wool, lambswool, merino, cashmere, mohair, '
        'alpaca, camel, silk, cotton, linen, viscose, modal, lyocell, cupro, acetate, polyester, nylon, acrylic, '
        'elastane, ...). Swedish: ull, lammull, bomull, lin, siden, kashmir, viskos, polyamid, akryl, elastan.\n'
        '- "percent" is the number on the label, or null when none is given (for example "Pure cotton").\n'
        '- A blend or mix with no breakdown ("Wool Blend", "cotton mix", "ullblandning") is not pure: report the '
        'fibre named with "percent": null and add an entry with "fibre": "unknown" for the rest.\n'
        '- "source" is "photo N" for a label in a photo or "text". Report a label only when you can read it; '
        'if it is blurred or cut off, leave it out. Never guess a fibre from how the fabric looks.\n\n'
        'Reply with JSON only, in this form:\n'
        '{"measurements": [{"name": "pit_to_pit", "value": 21.5, "unit": "in", "flat": true, '
        '"source": "photo 3", "confidence": "high", "start_visible": true, "end_visible": true, "scale_legible": true, "evidence_status": "verified", "note": ""}], '
        '"materials": [{"part": "shell", "fibre": "cotton", "percent": 100, "source": "photo 7", "confidence": "high"}]}\n'
        f'"name" is one of: {names}. "unit" is "in" or "cm". "source" is "photo N" or "text". '
        '"confidence" is "high", "medium" or "low". If the listing shows none of the measurements, '
        'use "measurements": []; if it shows no composition, use "materials": [].'
    )
    return intro, task


def _json_object(content):
    content = (content or '').strip()
    if content.startswith('```'):
        content = content.strip('`').strip()
        content = content[4:] if content.lower().startswith('json') else content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find('{'), content.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise AnalysisError('DeepSeek did not reply with JSON')


def parse_readings(content, garment_type):
    """Validate the model's JSON reply and convert it to cm, with widths stored flat."""
    data = _json_object(content)
    entries = data.get('measurements') if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise AnalysisError('DeepSeek reply has no measurements list')
    rank = {'high': 3, 'medium': 2, 'low': 1}
    readings = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get('name', '')).strip().lower()
        if name not in MEASUREMENTS[garment_type]:
            continue
        try:
            value = float(entry.get('value'))
        except (TypeError, ValueError):
            continue
        unit = str(entry.get('unit', '')).strip().lower().rstrip('.')
        unit = 'in' if unit in ('in', 'inch', 'inches', '"', "''") else 'cm' if unit in ('cm', 'cms', 'centimetres', 'centimeters') else None
        if unit is None:
            continue
        value_cm = value * 2.54 if unit == 'in' else value
        flat = entry.get('flat', True)
        flat = flat if isinstance(flat, bool) else str(flat).strip().lower() not in ('false', 'no', '0')
        if name in WIDTHS and not flat:
            value_cm /= 2  # all the way round -> flat
        if not 0 < value_cm < 200:
            continue
        source = str(entry.get('source', '')).strip().lower()
        photo = re.search(r'\d+', source)
        source = f'photo {photo.group()}' if 'photo' in source and photo else 'text' if 'text' in source else source[:20]
        confidence = str(entry.get('confidence', '')).strip().lower()
        confidence = confidence if confidence in rank else 'low'
        reading = {'name': name, 'value_cm': round(value_cm, 1), 'raw_value': value, 'raw_unit': unit,
                   'flat': flat, 'source': source, 'confidence': confidence,
                   'note': str(entry.get('note') or '').strip()[:300]}
        if name not in readings or rank[confidence] > rank[readings[name]['confidence']]:
            readings[name] = reading
    return sorted(readings.values(), key=lambda r: ORDER.index(r['name']))


PART_ALIASES = {'shell': 'shell', 'main': 'shell', 'body': 'shell', 'outer': 'shell', 'outer shell': 'shell',
                'face': 'shell', 'self': 'shell', 'fabric': 'shell', 'ytterstoff': 'shell', 'tyg': 'shell',
                'lining': 'lining', 'linings': 'lining', 'pocketing': 'lining', 'sleeve lining': 'lining',
                'fôr': 'lining', 'for': 'lining', 'foder': 'lining', 'futter': 'lining', 'doublure': 'lining'}


def parse_materials(content):
    """The fabric composition from the model's JSON reply: [{part, fibre, percent, source, confidence, raw}].

    Fibres are given their canonical names (material.fibre_name); a reply without a materials list,
    or with an unreadable one, gives []. One entry per part and fibre, the most confident kept.
    """
    import material
    try:
        data = _json_object(content)
    except AnalysisError:
        return []
    entries = data.get('materials') if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    rank = {'high': 3, 'medium': 2, 'low': 1}
    found = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get('fibre') or entry.get('material') or '').strip()
        if not raw:
            continue
        part = str(entry.get('part') or 'shell').strip().lower()
        part = PART_ALIASES.get(part, 'other' if part else 'shell')
        percent = entry.get('percent')
        if percent is not None:
            try:
                percent = float(str(percent).strip().rstrip('%'))
            except ValueError:
                percent = None
            if percent is not None and not 0 <= percent <= 100:
                continue
        source = str(entry.get('source', '')).strip().lower()
        photo = re.search(r'\d+', source)
        source = f'photo {photo.group()}' if 'photo' in source and photo else 'text'
        confidence = str(entry.get('confidence', '')).strip().lower()
        confidence = confidence if confidence in rank else 'low'
        fibre = material.fibre_name(raw)
        key = (part, fibre)
        if key not in found or rank[confidence] > rank[found[key]['confidence']]:
            found[key] = {'part': part, 'fibre': fibre, 'percent': percent, 'source': source,
                          'confidence': confidence, 'raw': raw[:60]}
    return sorted(found.values(), key=lambda m: (material.PARTS.index(m['part']), -(m['percent'] or 0)))


def _download(url):
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
    r.raise_for_status()
    mime = r.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip() or 'image/jpeg'
    return f'data:{mime};base64,' + base64.b64encode(r.content).decode('ascii')


def strict_photo_evidence():
    """STRICT_PHOTO_EVIDENCE in .env. On: photo readings without clear tape evidence are dropped.
    Off (default): they are kept but marked uncertain, so they can't make a listing red."""
    return os.environ.get('STRICT_PHOTO_EVIDENCE', '').strip().lower() in ('1', 'true', 'yes', 'on')


UNVERIFIED_NOTE = 'DeepSeek kunne ikke bekrefte begge ender av målebåndet og skalaen'


def read_measurements(photos, garment_type, title, text, api_key, model=DEFAULT_MODEL, strict=None):
    """Send one listing (photos and text) to DeepSeek in a single request.

    strict: drop photo readings without clear tape evidence (default: STRICT_PHOTO_EVIDENCE in .env).
    Returns (readings, raw reply). Raises AnalysisError on failure, AuthError for key or balance problems.
    """
    strict = strict_photo_evidence() if strict is None else strict
    if garment_type not in MEASUREMENTS:
        raise AnalysisError(f'unknown garment type {garment_type!r}')
    intro, task = build_prompt(garment_type, title, text, strict)
    content = [{'type': 'text', 'text': intro}]
    sent = 0
    for number, url in enumerate(photos[:MAX_PHOTOS], 1):
        try:
            data_url = _download(url)
        except requests.RequestException:
            continue  # keep the numbering of the remaining photos unchanged
        content.append({'type': 'text', 'text': f'Photo {number}:'})
        content.append({'type': 'image_url', 'image_url': {'url': data_url}})
        sent += 1
    if photos and not sent and not text:
        raise AnalysisError('none of the photos could be downloaded')
    content.append({'type': 'text', 'text': task})
    try:
        r = requests.post(DEEPSEEK_URL, headers={'Authorization': f'Bearer {api_key}'}, timeout=180, json={
            'model': model,
            'messages': [{'role': 'user', 'content': content}],
            'thinking': {'type': 'disabled'},
            'max_tokens': 2000,
        })
    except requests.RequestException as exc:
        raise AnalysisError(f'could not reach DeepSeek ({type(exc).__name__})') from exc
    if r.status_code in (401, 403):
        raise AuthError(f'DeepSeek refused the API key ({r.status_code}). Check DEEPSEEK_API_KEY in .env')
    if r.status_code == 402:
        raise AuthError('DeepSeek account has no balance left (402). Top up at platform.deepseek.com')
    if r.status_code >= 400:
        raise AnalysisError(f'DeepSeek error {r.status_code}: {r.text[:200]}')
    try:
        reply = r.json()['choices'][0]['message']['content'] or ''
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AnalysisError('unexpected reply from DeepSeek') from exc
    from measurement_gate import filter_supported_readings
    readings = parse_readings(reply, garment_type)
    accepted, rejected = filter_supported_readings(readings, reply)
    if not strict:
        # Keep the readings DeepSeek couldn't back up, but mark them uncertain: the traffic light
        # then shows "sjekk bildet" instead of trusting the number.
        unverified = {(r.get('name'), r.get('source')) for r in rejected}
        for reading in readings:
            if (reading['name'], reading['source']) in unverified:
                reading['confidence'] = 'low'
                reading['note'] = '; '.join(filter(None, [reading['note'], UNVERIFIED_NOTE]))
        accepted = readings
    # Keep the gate's decisions in the raw audit record.
    if rejected:
        try:
            audit = _json_object(reply)
            audit['rejected_photo_measurements' if strict else 'unverified_photo_measurements'] = rejected
            reply = json.dumps(audit, ensure_ascii=False)
        except (AnalysisError, TypeError, ValueError):
            pass
    return accepted, reply


def api_key():
    return os.environ.get('DEEPSEEK_API_KEY', '').strip()


def model_name():
    return os.environ.get('DEEPSEEK_MODEL', '').strip() or DEFAULT_MODEL
