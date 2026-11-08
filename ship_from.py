"""Where a listing is sent from: the seller's country (eBay's item location; Tradera is always Sweden)."""

# EU and EEA countries, Switzerland, the UK and the Crown Dependencies, where eBay UK sellers also live.
# Shipping from these to Norway is usually far cheaper and quicker than from North America or Asia.
EUROPE = frozenset('AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE '
                   'NO IS LI CH GB JE GG IM MC'.split())

NAMES = {'GB': 'Storbritannia', 'JE': 'Jersey', 'GG': 'Guernsey', 'IM': 'Isle of Man', 'IE': 'Irland',
         'SE': 'Sverige', 'DK': 'Danmark', 'FI': 'Finland', 'NO': 'Norge', 'DE': 'Tyskland', 'NL': 'Nederland',
         'BE': 'Belgia', 'FR': 'Frankrike', 'IT': 'Italia', 'ES': 'Spania', 'PT': 'Portugal', 'AT': 'Østerrike',
         'CH': 'Sveits', 'PL': 'Polen', 'CZ': 'Tsjekkia', 'US': 'USA', 'CA': 'Canada', 'AU': 'Australia',
         'NZ': 'New Zealand', 'JP': 'Japan', 'CN': 'Kina', 'HK': 'Hongkong', 'KR': 'Sør-Korea', 'TH': 'Thailand'}

ALL, IN_EUROPE, OUTSIDE_EUROPE = 'all', 'europe', 'outside'
FILTERS = {ALL: 'Alle land', IN_EUROPE: 'Europa (med Storbritannia)', OUTSIDE_EUROPE: 'Utenfor Europa'}


def country_of(item):
    """The two-letter country a search result or full listing is sent from, or None when not given."""
    if str(item.get('itemId', '')).startswith('tradera:'):
        return 'SE'
    country = str((item.get('itemLocation') or {}).get('country') or '').strip().upper()
    return country if len(country) == 2 and country.isalpha() else None


def name(country):
    return NAMES.get(country, country) if country else 'ukjent land'


def sql_condition(choice, column='l.item_country'):
    """(SQL condition, arguments) for the "Sendes fra" filter; listings with no known country are left out."""
    marks = ','.join('?' * len(EUROPE))
    if choice == IN_EUROPE:
        return f'{column} IN ({marks})', sorted(EUROPE)
    if choice == OUTSIDE_EUROPE:
        return f'{column} IS NOT NULL AND {column} NOT IN ({marks})', sorted(EUROPE)
    return '', []
