"""Try the DeepSeek measurement reading on one listing or one photo, without saving anything.

    python test_one.py <eBay listing link> [jacket|coat|waistcoat|trousers|knitwear|shirt]
    python test_one.py <photo address from i.ebayimg.com> [jacket|coat|waistcoat|trousers|knitwear|shirt]

The garment type defaults to the one the listing matched in your database, or jacket.
"""
import sys

from dotenv import load_dotenv

import measure
import watcher

load_dotenv(watcher.ROOT / '.env')
if len(sys.argv) < 2:
    sys.exit(__doc__)
link = sys.argv[1].strip()
garment_type = sys.argv[2] if len(sys.argv) > 2 else None
if garment_type and garment_type not in measure.MEASUREMENTS:
    sys.exit(f'Garment type must be one of: {", ".join(measure.MEASUREMENTS)}')
if not measure.api_key():
    sys.exit('DEEPSEEK_API_KEY is missing from .env')

if 'ebayimg.com' in link:
    photos, title, text = [measure.full_size_photo(link)], '(single photo test)', ''
else:
    item_id = watcher.ebay_item_key(watcher.resolve_ebay_url(link))
    if not item_id:
        sys.exit('That does not look like an eBay listing link')
    with watcher.connect() as conn:
        garment_type = garment_type or watcher.garment_types(conn).get(item_id)
    full = watcher.get_item(item_id, watcher.token())
    photos, title, text = measure.photos_from_item(full), full.get('title', ''), measure.listing_text(full)

garment_type = garment_type or 'jacket'
gate = 'strict' if measure.strict_photo_evidence() else 'lenient'
print(f'{title}\n{len(photos)} photo(s), garment type: {garment_type}, model: {measure.model_name()}, evidence gate: {gate}\n')
readings, raw = measure.read_measurements(photos, garment_type, title, text, measure.api_key(), measure.model_name())
for r in readings:
    width = ' flat' if r['name'] in measure.WIDTHS else ''
    print(f"  {r['name']:<12} {r['value_cm']:6.1f} cm{width}  ({r['raw_value']:g} {r['raw_unit']}, "
          f"{'flat' if r['flat'] else 'round'})  {r['source']}, {r['confidence']}  {r['note']}")
if not readings:
    print('  No measurements found.')
print('\nRaw reply from DeepSeek:\n' + raw)
