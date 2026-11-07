"""Coats and outer jackets found by a blazer or sport coat search: which wardrobe target they belong to.

Searches such as "vintage wool sport coat" or "kavaj manchester" also bring back trench coats, duffle
coats, parkas and field jackets. Those don't belong under a jacket target. One with a coat target of its
own in the plan is moved there; the rest are not a blazer at all and are left out.
"""
import re

import measure

# (words in the title, the wardrobe target it belongs to). The first match wins.
COATS = (
    (r'duffle|duffel', 'W002'),
    (r'trench|raincoat|rain coat|mackintosh|balmacaan|regnrock|regnkappa', 'W004'),
    (r'overcoat|over coat|top ?coat|covert coat|british warm|crombie|chesterfield|great ?coat|'
     r'överrock|ullrock|herrrock|långrock|vinterrock|kashmirrock', 'W001'),
    (r'wax(?:ed)? jacket|vaxjacka|vaxad jacka|bedale|beaufort', 'W003'),
)
# Outerwear with no target of its own. "jacka" and "kappa" are Swedish for jacket and coat; a blazer
# is "kavaj". \b keeps KappAhl (a Swedish shop that also sells blazers) out.
OUTERWEAR = (r'parka|pea ?coat|pea jacket|caban|bomber|field jacket|fältjacka|utility|workwear|chore jacket|'
             r'anorak|gilet|puffer|down jacket|dunjacka|car coat|kappa\b|jacka\b|cardigan')
# Words that say it is a tailored jacket after all. They outweigh OUTERWEAR, not COATS: a title that
# says trench or duffle is a coat whatever else it says.
TAILORED = r'blazer|sports? ?coat|sports? jacket|suit jacket|kavaj|kostym|tuxedo|dinner jacket|smoking'

REJECT_NOTE = 'Ikke en blazer eller sportsjakke (yttertøy), sortert ut automatisk'


def kinds(items):
    """wardrobe ID -> garment type ('jacket', 'coat', ...) for the plan in wardrobe.json."""
    return {item['id']: measure.garment_type_for(item) for item in items if item.get('enabled', True)}


def route(title, wardrobe_id, kinds_by_id):
    """The wardrobe target a listing found for `wardrobe_id` belongs to: the same one, a coat target,
    or None when it is outerwear with no target. Only listings found for a jacket target are moved."""
    if kinds_by_id.get(wardrobe_id) != 'jacket':
        return wardrobe_id
    text = (title or '').casefold()
    for words, target in COATS:
        if re.search(words, text):
            return target if kinds_by_id.get(target) == 'coat' else None
    if re.search(OUTERWEAR, text) and not re.search(TAILORED, text):
        return None
    return wardrobe_id
