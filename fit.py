"""Traffic light: compares the measurements read from a listing with your own target ranges.

All values are in cm, with widths flat, as in the measuring sheet. The rules below are rules of
thumb for vintage clothes; adjust them here if your tailor tells you otherwise.
"""
from collections import namedtuple

import measure

GREEN, YELLOW, RED, GREY = 'green', 'yellow', 'red', 'grey'
COLOURS = (GREEN, YELLOW, RED, GREY)
LABELS = {GREEN: '🟢 Passer', YELLOW: '🟡 Kanskje', RED: '🔴 Passer ikke', GREY: '⚪ Ukjent'}
DOTS = {GREEN: '🟢', YELLOW: '🟡', RED: '🔴', GREY: '🔍'}
RANK = {GREEN: 0, YELLOW: 1, GREY: 2, RED: 3}

# near:      how far outside your range still counts as "just outside", since sellers' tapes are
#            rarely more exact than about a centimetre
# fix_big:   how much too big a tailor can usually fix, and how (0 = can't be altered)
# fix_small: how much too small a tailor can usually fix, and how
Rule = namedtuple('Rule', 'near fix_big how_big fix_small how_small')
HARD = lambda near: Rule(near, 0, '', 0, '')  # noqa: E731 - can't be altered

_JACKET = {
    'pit_to_pit': Rule(1, 2, 'kan tas inn', 1, 'kan kanskje slippes ut'),
    'shoulders': HARD(1),
    'sleeve': Rule(1, 6, 'kan kortes', 3, 'kan kanskje forlenges hvis det er stoff i ermet'),
    'back_length': HARD(1.5),
    'waist': Rule(1, 3, 'kan tas inn', 1.5, 'kan kanskje slippes ut'),
}
RULES = {
    'jacket': _JACKET,
    'coat': _JACKET,
    'waistcoat': {'pit_to_pit': _JACKET['pit_to_pit'], 'back_length': HARD(1.5), 'waist': _JACKET['waist']},
    'trousers': {
        'waist': Rule(1, 3, 'kan tas inn', 2, 'kan slippes ut hvis det er nok stoff i bakre søm'),
        'seat': Rule(1, 2, 'kan tas inn', 1, 'kan kanskje slippes ut'),
        'front_rise': HARD(1),
        'back_rise': HARD(1.5),
        'thigh': Rule(1, 2, 'kan smalnes', 0, ''),
        'inseam': Rule(1, 15, 'kan kortes', 3, 'kan kanskje forlenges hvis det er stoff i kanten'),
        'leg_opening': Rule(1, 3, 'kan smalnes', 0, ''),
    },
    # Knitwear can't really be altered, but it gives a little.
    'knitwear': {name: HARD(1.5) for name in measure.MEASUREMENTS['knitwear']},
    'shirt': {
        'collar': Rule(0.5, 0, '', 1, 'knappen kan flyttes litt'),
        'pit_to_pit': Rule(1, 3, 'kan tas inn', 0, ''),
        'sleeve': Rule(1, 5, 'kan kortes', 0, ''),
        'back_length': Rule(2, 10, 'går fint når skjorta stappes ned', 0, ''),
    },
}

# These must be known (and not wrong) before a listing can be green.
KEY = {'jacket': ('pit_to_pit', 'shoulders'), 'coat': ('pit_to_pit', 'shoulders'), 'waistcoat': ('pit_to_pit',),
       'trousers': ('waist', 'front_rise'), 'knitwear': ('pit_to_pit', 'length'), 'shirt': ('collar', 'pit_to_pit')}

_WORDS = {'shoulders': ('for bred', 'for smal'), 'collar': ('for vid', 'for trang')}
for _name in measure.WIDTHS:
    _WORDS[_name] = ('for vid', 'for trang')
for _name in ('sleeve', 'back_length', 'inseam', 'length', 'front_rise', 'back_rise'):
    _WORDS[_name] = ('for lang', 'for kort')

Verdict = namedtuple('Verdict', 'colour reasons per_reading')  # per_reading: name -> (colour, text)


def rule_hint(garment_type, name):
    """Short text for the "Mine mål" tab: what a tailor can do with this measurement."""
    rule = RULES[garment_type][name]
    if not rule.fix_big and not rule.fix_small:
        return 'Kan ikke sys om'
    parts = []
    if rule.fix_big:
        parts.append(f'{_WORDS[name][0]}: {rule.how_big} (inntil {rule.fix_big:g} cm)')
    if rule.fix_small:
        parts.append(f'{_WORDS[name][1]}: {rule.how_small} (inntil {rule.fix_small:g} cm)')
    return ' · '.join(parts)


def judge_reading(garment_type, name, value_cm, low=None, high=None):
    """(colour, text) for one measurement against your range."""
    rule = RULES[garment_type][name]
    label = measure.LABELS.get(name, name)
    if low is not None and value_cm < low:
        off, word, fix, how = low - value_cm, _WORDS[name][1], rule.fix_small, rule.how_small
    elif high is not None and value_cm > high:
        off, word, fix, how = value_cm - high, _WORDS[name][0], rule.fix_big, rule.how_big
    else:
        return GREEN, f'{label} passer'
    text = f'{label} {off:.1f} cm {word}'
    if off <= fix:
        return YELLOW, f'{text} ({how})'
    if off <= rule.near:
        return YELLOW, f'{text} (like utenfor, sjekk målet)'
    return RED, text


def judge_listing(garment_type, readings, targets):
    """Verdict for one listing.

    readings: list of (name, value_cm, confidence) read from the listing.
    targets:  {garment_type: {name: (low, high)}} from load_targets().
    """
    if garment_type is None:
        return Verdict(GREY, ['kjøpes etter størrelse, vurderes ikke'], {})
    wanted = {name: rng for name, rng in targets.get(garment_type, {}).items() if rng[0] is not None or rng[1] is not None}
    if not wanted:
        return Verdict(GREY, [f'ingen mål satt for {measure.TYPE_LABELS[garment_type].lower()} under Mine mål'], {})
    per_reading, confident = {}, {}
    for name, value_cm, confidence in readings:
        if name not in wanted:
            continue
        colour, text = judge_reading(garment_type, name, value_cm, *wanted[name])
        if confidence == 'low':
            per_reading[name] = (GREY, f'{measure.LABELS.get(name, name)} er usikker, sjekk bildet')
        else:
            per_reading[name] = (colour, text)
            confident[name] = colour
    reds = [per_reading[n][1] for n, c in confident.items() if c == RED]
    if reds:
        return Verdict(RED, reds, per_reading)
    if not confident:
        unsure = [text for colour, text in per_reading.values()]
        return Verdict(GREY, unsure or ['ingen av dine mål er vist i annonsen'], per_reading)
    reasons = [per_reading[n][1] for n, c in confident.items() if c == YELLOW]
    reasons += [text for n, (colour, text) in per_reading.items() if n not in confident]
    missing = [measure.LABELS[k].lower() for k in KEY[garment_type] if k in wanted and k not in confident]
    if missing:
        reasons.append('mangler ' + ' og '.join(missing))
    return Verdict(YELLOW if reasons else GREEN, reasons, per_reading)


def load_targets(conn):
    targets = {}
    for kind, name, low, high in conn.execute('SELECT garment_type,name,min_cm,max_cm FROM fit_targets'):
        if kind in RULES and name in RULES[kind]:
            targets.setdefault(kind, {})[name] = (low, high)
    return targets


def save_targets(conn, garment_type, ranges):
    """ranges: {name: (low, high)}; a measurement with neither is removed (not judged)."""
    for name, (low, high) in ranges.items():
        if low is None and high is None:
            conn.execute('DELETE FROM fit_targets WHERE garment_type=? AND name=?', (garment_type, name))
        else:
            conn.execute('''INSERT INTO fit_targets(garment_type,name,min_cm,max_cm) VALUES(?,?,?,?)
                ON CONFLICT(garment_type,name) DO UPDATE SET min_cm=excluded.min_cm, max_cm=excluded.max_cm''',
                         (garment_type, name, low, high))
    conn.commit()


def all_verdicts(conn, garment_types):
    """item_id -> Verdict for every listing. garment_types comes from watcher.garment_types()."""
    targets = load_targets(conn)
    readings, analysed = {}, {}
    for item_id, name, value_cm, confidence in conn.execute('SELECT item_id,name,value_cm,confidence FROM listing_measurements'):
        readings.setdefault(item_id, []).append((name, value_cm, confidence))
    for item_id, status in conn.execute('SELECT item_id,status FROM listing_analysis'):
        analysed[item_id] = status
    verdicts = {}
    for (item_id,) in conn.execute('SELECT item_id FROM listings'):
        kind = garment_types.get(item_id)
        if kind is not None and item_id not in readings and analysed.get(item_id) != 'ok':
            verdicts[item_id] = Verdict(GREY, ['ikke analysert ennå'], {})
        else:
            verdicts[item_id] = judge_listing(kind, readings.get(item_id, []), targets)
    return verdicts
