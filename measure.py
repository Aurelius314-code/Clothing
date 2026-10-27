"""Reads garment measurements from eBay listing photos and text with DeepSeek's vision model.

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
# Accessories, footwear and basics are sold by size, so they are not analysed.
CATEGORY_TYPES = {'Outerwear': 'jacket', 'Tailoring': 'jacket', 'Trousers': 'trousers',
                  'Knitwear': 'knitwear', 'Shirts': 'shirt'}

# Measurement key -> how it is taken, as explained to the model (same method as the measuring sheet).
MEASUREMENTS = {
    'jacket': {
        'pit_to_pit': 'straight across the front from armpit seam to armpit seam, buttoned',
        'shoulders': 'across the back from the seam where one sleeve joins to the other',
        'sleeve': 'from the shoulder seam down the outside of the sleeve to the end of the cuff',
        'back_length': 'centre back, from the bottom of the collar seam to the hem',
        'waist': 'straight across at the narrowest point, around the top button',
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

# Measurements taken across the garment. All-round values are halved so every width is stored flat.
WIDTHS = {'pit_to_pit', 'waist', 'seat', 'thigh', 'leg_opening'}

LABELS = {'pit_to_pit': 'Brystvidde', 'shoulders': 'Skulderbredde', 'sleeve': 'Ermelengde',
          'back_length': 'Rygglengde', 'waist': 'Livvidde', 'seat': 'Setevidde',
          'front_rise': 'Livhøyde foran', 'back_rise': 'Livhøyde bak', 'thigh': 'Lårvidde',
          'inseam': 'Innerbenslengde', 'leg_opening': 'Benåpning', 'length': 'Lengde', 'collar': 'Krage'}
ORDER = list(LABELS)

EBAY_PHOTO = re.compile(r'^https://i\.ebayimg\.com/(?:thumbs/)?images/g/([^/?#]+)/s-l\d+(\.[a-z]+)', re.IGNORECASE)


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


def build_prompt(garment_type, title, text):
    """(text before the photos, text after the photos) for one listing."""
    wanted = MEASUREMENTS[garment_type]
    intro = (
        'You read garment measurements from an eBay listing. A buyer compares them with the measurements '
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
        '- The tape should start at 0 at the near edge. If it starts elsewhere, subtract the starting value; '
        'if you cannot see where it starts or ends, do not report a numerical photo measurement.\n'
        '- For photo measurements, verify the tape zero/start, the garment endpoint, and legible scale.\n'
        '- Set start_visible, end_visible, scale_legible to true only when each is clearly visible.\n'
        '- Set evidence_status to "verified" only when all three are true; otherwise "ambiguous".\n'
        '- Do not return numerical photo measurements with ambiguous evidence.\n'
        '- If the garment is folded or stretched, or the tape runs at a slant, use confidence "medium" or "low" and say why.\n\n'
        'Other rules:\n'
        '- "flat" is true when the measurement goes one layer across a garment lying flat (most tape photos, '
        '"pit to pit", "flat waist"); false when it goes all the way round (for example "waist 34 inches" or "chest 42").\n'
        '- Label sizes such as "42R", "W34 L30" or "Large" are not measurements; leave them out.\n'
        '- When the text and a photo disagree, report the photo reading and mention the text value in the note.\n'
        '- Leave out any measurement the listing does not show. Never estimate one.\n\n'
        'Reply with JSON only, in this form:\n'
        '{"measurements": [{"name": "pit_to_pit", "value": 21.5, "unit": "in", "flat": true, '
        '"source": "photo 3", "confidence": "high", "start_visible": true, "end_visible": true, "scale_legible": true, "evidence_status": "verified", "note": ""}]}\n'
        f'"name" is one of: {names}. "unit" is "in" or "cm". "source" is "photo N" or "text". '
        '"confidence" is "high", "medium" or "low". If the listing shows none of them, reply {"measurements": []}.'
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


def _download(url):
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
    r.raise_for_status()
    mime = r.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip() or 'image/jpeg'
    return f'data:{mime};base64,' + base64.b64encode(r.content).decode('ascii')


def read_measurements(photos, garment_type, title, text, api_key, model=DEFAULT_MODEL):
    """Send one listing (photos and text) to DeepSeek in a single request.

    Returns (readings, raw reply). Raises AnalysisError on failure, AuthError for key or balance problems.
    """
    if garment_type not in MEASUREMENTS:
        raise AnalysisError(f'unknown garment type {garment_type!r}')
    intro, task = build_prompt(garment_type, title, text)
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
            'max_tokens': 1500,
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
    # Preserve rejection reasons in the raw audit record without changing DB schema.
    if rejected:
        try:
            audit = _json_object(reply)
            audit["rejected_photo_measurements"] = rejected
            reply = json.dumps(audit, ensure_ascii=False)
        except (AnalysisError, TypeError, ValueError):
            pass
    return accepted, reply


def api_key():
    return os.environ.get('DEEPSEEK_API_KEY', '').strip()


def model_name():
    return os.environ.get('DEEPSEEK_MODEL', '').strip() or DEFAULT_MODEL
