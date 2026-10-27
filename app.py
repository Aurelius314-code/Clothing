"""Local visual UI. Run: python -m streamlit run app.py"""
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from urllib.parse import urlparse

import requests
import streamlit as st

import fit
import measure
from watcher import (DB, CATALOG, MAX_ATTEMPTS, REVIEW_STATUSES, connect, ebay_item_key, fingerprint, garment_types,
                     has_flag, is_auction_only, listing_photos, resolve_ebay_url, set_flag, store_photos, utc_now)

st.set_page_config(page_title='Vintage Wardrobe Watcher', page_icon='🧥', layout='wide')

PAGE_SIZE = 50
STATUS_LABELS = {'saved': '⭐ Lagret', 'rejected': 'Avvist', 'purchased': 'Kjøpt', 'unreviewed': 'Ikke vurdert'}
FIT_LABELS = {'good': 'God', 'needs_review': 'Må vurderes', 'poor': 'Problem / bør erstattes'}
CONFIDENCE_LABELS = {'high': 'sikker', 'medium': 'litt usikker', 'low': '⚠️ usikker'}

# Prefilled once per database. The two trousers have no wardrobe target yet: none of the
# trouser entries in wardrobe.json describes them, so assign them in the garment register.
SEED_GARMENTS = [
    ('W001', 'British Warm overcoat', 'Dunn & Co', '', 'good', 'Crombie cloth; owned; check fit and condition', ''),
    (None, 'High-waisted pleated chinos', 'Polo Ralph Lauren', 'W38 L30', 'poor', 'Waist too tight when sitting; needs unbuttoning when driving; not a satisfactory fit', ''),
    (None, 'Second high-waisted pleated trousers', '', '', 'needs_review', 'Waist fit not yet measured or confirmed; category is provisional', '')]


def seed_garments(conn):
    """Prefill the garment register once. Deleting garments afterwards never brings these back."""
    if has_flag(conn, 'garments_seeded'):
        return
    if conn.execute('SELECT COUNT(*) FROM owned_garments').fetchone()[0] == 0:
        conn.executemany('INSERT INTO owned_garments(wardrobe_id,name,brand,size,fit,notes,image_url,created_at) VALUES(?,?,?,?,?,?,?,?)',
                         [(*garment, utc_now()) for garment in SEED_GARMENTS])
    set_flag(conn, 'garments_seeded')
    conn.commit()


def read_catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def write_catalog(data):
    """Write to a temporary file first, so a crash mid-write can never leave wardrobe.json half-written."""
    fd, tmp = tempfile.mkstemp(dir=CATALOG.parent, prefix='.wardrobe-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CATALOG)
    except BaseException:
        os.unlink(tmp)
        raise


def safe_url(url):
    p = urlparse(url.strip())
    return p.scheme in ('https', 'http') and bool(p.netloc) and not p.username and not p.password


def md(text):
    """Escape text from eBay or DeepSeek so Streamlit shows it as written, not as markdown."""
    return re.sub(r'([\\`*_{}\[\]()#+!|<>~])', r'\\\1', str(text or ''))


def manual_add(conn, title, url, seller, price, currency, image, wid, notes):
    """Save a listing entered by hand. `url` should already be resolved if it was a share link."""
    url = url.strip()
    key = ebay_item_key(url) or 'manual:' + hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
    old = conn.execute('SELECT price,currency,seller,image_url FROM listings WHERE item_id=?', (key,)).fetchone()
    # Blank optional fields keep what is already stored, e.g. the seller from an earlier API search.
    seller = seller.strip() or (old[2] if old else '')
    image = image.strip() or (old[3] if old else '')
    t = utc_now()
    conn.execute('''INSERT INTO listings(item_id,title,url,image_url,seller,price,currency,first_seen,last_seen,fingerprint)
      VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET title=excluded.title,
      image_url=excluded.image_url,seller=excluded.seller,price=excluded.price,currency=excluded.currency,
      last_seen=excluded.last_seen,fingerprint=excluded.fingerprint''',
      (key, title, url, image, seller, price, currency, t, t, fingerprint(title, seller)))
    if wid:
        conn.execute('INSERT OR IGNORE INTO matches(item_id,wardrobe_id) VALUES(?,?)', (key, wid))
    if image and not listing_photos(conn, key):
        store_photos(conn, key, [measure.full_size_photo(image)])
    notes = notes.strip()
    if notes:
        existing = conn.execute('SELECT notes FROM listing_reviews WHERE item_id=?', (key,)).fetchone()
        existing = (existing[0] or '').strip() if existing else ''
        if notes not in existing:
            # A new note is added under the earlier ones, with the date, instead of replacing them.
            notes = f'{existing}\n{t[:10]}: {notes}' if existing else notes
            conn.execute('''INSERT INTO listing_reviews(item_id,status,notes) VALUES(?,'unreviewed',?)
              ON CONFLICT(item_id) DO UPDATE SET notes=excluded.notes''', (key, notes))
    if old is None or tuple(old[:2]) != (price, currency):
        conn.execute('INSERT OR IGNORE INTO price_history(item_id,observed_at,price,currency) VALUES(?,?,?,?)', (key, t, price, currency))
    conn.commit()
    return old is None


def money(value, currency):
    return f'{value:.2f} {currency}' if value is not None else '?'


with connect() as conn:
    seed_garments(conn)
    catalog = read_catalog()
    items = catalog['items']
    names = {i['id']: i['name'] for i in items}

    def target_label(wid):
        return 'Ikke tilordnet' if wid is None else names.get(wid, f'{wid} (finnes ikke i wardrobe.json)')

    def target_options(current=None):
        options = [None, *names]
        return options if current in options else [*options, current]

    types = garment_types(conn, items)
    verdicts = fit.all_verdicts(conn, types)
    tab_home, tab_wardrobe, tab_targets, tab_listings, tab_add, tab_fit = st.tabs(
        ['🏠 Oversikt', '🧥 Garderobe', '📐 Mine mål', '🔎 Annonser', '➕ Legg til annonse', '📏 Passform og historikk'])

    with tab_home:
        st.title('Vintage Wardrobe Watcher')
        st.caption('Din lokale vintage-garderobe. Ingen eBay-tilgang kreves for å bruke disse sidene.')
        total = sum(int(i['target_quantity']) for i in items)
        owned = sum(int(i['owned_quantity']) for i in items)
        listed = conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
        saved = conn.execute("SELECT COUNT(*) FROM listing_reviews WHERE status='saved'").fetchone()[0]
        a, b, c, d, e = st.columns(5)
        a.metric('Planlagte enheter', total); b.metric('Registrert eid', owned); c.metric('Arkiverte annonser', listed); d.metric('Lagrede annonser', saved)
        e.metric('Annonser som passer', sum(v.colour == fit.GREEN for v in verdicts.values()))
        st.progress(min(owned / total, 1) if total else 0)
        st.subheader('Neste prioriterte plagg')
        pending = sorted((i for i in items if i['enabled'] and i['owned_quantity'] < i['target_quantity']), key=lambda x: (x['priority'], x['category']))
        for i in pending[:12]:
            with st.container(border=True):
                st.markdown(f"**{i['name']}** · {i['category']} · prioritet {i['priority']}")
                st.caption(i.get('notes', ''))

    with tab_wardrobe:
        st.header('Garderobeplan')
        st.caption('Antall og søkestatus lagres i wardrobe.json. Eksisterende data beholdes.')
        categories = sorted({i['category'] for i in items})
        cat = st.selectbox('Kategori', ['Alle'] + categories)
        for i in items:
            if cat != 'Alle' and i['category'] != cat:
                continue
            with st.expander(f"{i['name']}  ·  {i['owned_quantity']}/{i['target_quantity']}"):
                st.caption(i.get('notes', ''))
                c1, c2, c3, c4 = st.columns(4)
                q = c1.number_input('Antall eid', 0, 100, int(i['owned_quantity']), key='qty' + i['id'])
                target = c2.number_input('Ønsket antall', 0, 100, int(i['target_quantity']), key='target' + i['id'])
                priority = c3.number_input('Prioritet (1=høy)', 1, 10, int(i['priority']), key='prio' + i['id'])
                enabled = c4.checkbox('Aktivt søk', value=bool(i['enabled']), key='enable' + i['id'])
                if st.button('Lagre endringer', key='save' + i['id']):
                    i.update(owned_quantity=q, target_quantity=target, priority=priority, enabled=enabled)
                    write_catalog(catalog)
                    st.success('Lagret.'); st.rerun()
        st.divider()
        st.subheader('Mine faktiske plagg')
        with st.form('add_garment'):
            name = st.text_input('Navn på plagget')
            wid = st.selectbox('Tilhører garderobemål', target_options(), format_func=target_label)
            x, y = st.columns(2)
            brand = x.text_input('Merke'); size = y.text_input('Størrelse')
            rating = st.selectbox('Passform', list(FIT_LABELS), format_func=FIT_LABELS.get)
            notes = st.text_area('Notater om passform, tilstand og mål')
            image = st.text_input('Bilde-URL (valgfritt)')
            if st.form_submit_button('Registrer plagg'):
                if not name.strip(): st.error('Oppgi navn')
                elif image and not safe_url(image): st.error('Ugyldig bilde-URL')
                else:
                    conn.execute('INSERT INTO owned_garments(wardrobe_id,name,brand,size,fit,notes,image_url,created_at) VALUES(?,?,?,?,?,?,?,?)', (wid, name, brand, size, rating, notes, image, utc_now()))
                    conn.commit(); st.success('Plagg registrert. Antall eid i garderobeplanen oppdateres separat.'); st.rerun()
        garments = conn.execute('SELECT garment_id,wardrobe_id,name,brand,size,fit,notes,image_url FROM owned_garments ORDER BY garment_id DESC').fetchall()
        for gid, gwid, n, br, sz, rating, note, img in garments:
            with st.container(border=True):
                st.markdown(f'**{n}** · {br} · {sz} · {FIT_LABELS.get(rating, rating)}')
                st.caption(note)
                if img and safe_url(img): st.image(img, width=180)
                options = target_options(gwid)
                left, right = st.columns([3, 1], vertical_alignment='bottom')
                new_wid = left.selectbox('Garderobemål', options, index=options.index(gwid), format_func=target_label, key=f'gw{gid}')
                if right.button('Lagre garderobemål', key=f'gws{gid}', disabled=new_wid == gwid):
                    conn.execute('UPDATE owned_garments SET wardrobe_id=? WHERE garment_id=?', (new_wid, gid)); conn.commit(); st.rerun()
                if st.button('Slett denne registreringen', key='delg' + str(gid)):
                    conn.execute('DELETE FROM owned_garments WHERE garment_id=?', (gid,)); conn.commit(); st.rerun()

    with tab_targets:
        st.header('Mine mål')
        st.caption('Områdene her avgjør trafikklyset på annonsene. Skriv inn flate mål i cm fra målearket, for eksempel '
                   '1–2 cm på hver side av et plagg som passer deg. La et felt stå tomt hvis målet ikke skal vurderes.')
        if st.session_state.pop('targets_saved', None):
            st.success('Målene er lagret, og trafikklysene er oppdatert.')
        kind = st.selectbox('Type plagg', list(measure.TYPE_LABELS), format_func=measure.TYPE_LABELS.get, key='target_kind')
        current = fit.load_targets(conn).get(kind, {})
        with st.form(f'targets_{kind}'):
            entered = {}
            for name in measure.MEASUREMENTS[kind]:
                label = measure.LABELS[name] + (' (flatt)' if name in measure.WIDTHS else '')
                must = ' Må være kjent for grønt lys.' if name in fit.KEY[kind] else ''
                info, low_col, high_col = st.columns([3, 1, 1])
                info.markdown(f'**{label}**')
                info.caption(f'{measure.HELP[name]}. {fit.rule_hint(kind, name)}.{must}')
                # The fields start empty (value=None) and are filled from the saved targets, because a
                # field that starts with a number can't be emptied again in the browser.
                for key, saved in zip((f't_{kind}_{name}_lo', f't_{kind}_{name}_hi'), current.get(name, (None, None))):
                    if key not in st.session_state:
                        st.session_state[key] = saved
                entered[name] = (
                    low_col.number_input('Fra (cm)', min_value=0.0, max_value=200.0, value=None, step=0.5, format='%.1f', key=f't_{kind}_{name}_lo'),
                    high_col.number_input('Til (cm)', min_value=0.0, max_value=200.0, value=None, step=0.5, format='%.1f', key=f't_{kind}_{name}_hi'))
            if st.form_submit_button('Lagre mine mål'):
                wrong = [measure.LABELS[n] for n, (lo, hi) in entered.items() if lo is not None and hi is not None and lo > hi]
                if wrong:
                    st.error('«Fra» er større enn «Til» for: ' + ', '.join(wrong))
                else:
                    fit.save_targets(conn, kind, entered)
                    st.session_state['targets_saved'] = True
                    st.rerun()
        counts = Counter(v.colour for item_id, v in verdicts.items() if types.get(item_id) == kind)
        if counts:
            st.caption(f'{measure.TYPE_LABELS[kind]} i arkivet nå: ' + ' · '.join(f'{fit.LABELS[c]} {counts[c]}' for c in fit.COLOURS if counts[c]))

    with tab_listings:
        st.header('Annonsearkiv')
        st.caption('Gamle annonser beholdes, også når de ikke lenger er aktive på eBay.')
        top_left, top_mid, top_right = st.columns([1, 2, 1])
        filter_status = top_left.selectbox('Vurdering', ['Alle', *REVIEW_STATUSES], format_func=lambda s: STATUS_LABELS.get(s, s))
        colours = top_mid.multiselect('Trafikklys', list(fit.COLOURS), default=[fit.GREEN, fit.YELLOW, fit.GREY],
                                      format_func=fit.LABELS.get, key='listing_colours')
        order = top_right.selectbox('Sortering', ['newest', 'best'], key='listing_order',
                                    format_func={'newest': 'Nyeste først', 'best': 'Beste treff først'}.get)
        where, args = ('', ()) if filter_status == 'Alle' else ("WHERE COALESCE(r.status,'unreviewed')=?", (filter_status,))
        candidates = [i for (i,) in conn.execute(
            f'SELECT l.item_id FROM listings l LEFT JOIN listing_reviews r ON l.item_id=r.item_id {where} ORDER BY l.first_seen DESC', args)]
        unknown = fit.Verdict(fit.GREY, [], {})
        selected = [i for i in candidates if verdicts.get(i, unknown).colour in colours]
        hidden = len(candidates) - len(selected)
        if order == 'best':
            selected.sort(key=lambda i: fit.RANK[verdicts.get(i, unknown).colour])  # stable: newest first within a colour
        total = len(selected)
        pages = max(1, -(-total // PAGE_SIZE))
        # One remembered page per filter. The widget's label and limits never change, so Streamlit keeps
        # the page when the count changes (for example after rejecting a listing); it only moves back
        # when the page no longer exists.
        page_key = f'listing_page_{filter_status}_{"-".join(sorted(colours))}_{order}'
        if st.session_state.get(page_key, 1) > pages:
            st.session_state[page_key] = pages
        page = min(int(st.number_input('Side', min_value=1, step=1, key=page_key)), pages) if pages > 1 else 1
        hidden_text = f' · {hidden} skjult av trafikklys-filteret' if hidden else ''
        st.caption((f'Side {page} av {pages} · ' if pages > 1 else '') + f'{total} annonser{hidden_text}')
        page_ids = selected[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
        rows = []
        if page_ids:
            by_id = {row[0]: row for row in conn.execute(f'''SELECT l.item_id,l.title,l.url,l.image_url,l.seller,l.price,l.currency,
              l.shipping_cost,l.shipping_currency,l.buying_options,l.first_seen,l.last_seen,
              COALESCE(r.status,'unreviewed'),COALESCE(r.notes,l.notes,''),
              (SELECT COUNT(*) FROM listings x WHERE x.fingerprint=l.fingerprint)
              FROM listings l LEFT JOIN listing_reviews r ON l.item_id=r.item_id
              WHERE l.item_id IN ({','.join('?' * len(page_ids))})''', page_ids)}
            rows = [by_id[i] for i in page_ids]
        targets = fit.load_targets(conn)
        ids = [row[0] for row in rows]
        marks = ','.join('?' * len(ids))
        readings, analyses, photos = {}, {}, {}
        if ids:
            for r in conn.execute(f'''SELECT item_id,name,value_cm,raw_value,raw_unit,flat,source,confidence,note,verification_status
                    FROM listing_measurements WHERE item_id IN ({marks})''', ids):
                readings.setdefault(r[0], []).append(r[1:])
            analyses = {r[0]: r[1:] for r in conn.execute(
                f'SELECT item_id,status,attempts,error FROM listing_analysis WHERE item_id IN ({marks})', ids)}
            for item_id, photo_url in conn.execute(
                    f'SELECT item_id,url FROM listing_photos WHERE item_id IN ({marks}) ORDER BY item_id,position', ids):
                photos.setdefault(item_id, []).append(photo_url)
        for (iid, title, url, img, seller, price, currency, ship, ship_currency, options,
             first, last, status, notes, similar) in rows:
            with st.container(border=True):
                left, right = st.columns([1, 4])
                with left:
                    if img and safe_url(img): st.image(img, width='stretch')
                with right:
                    st.markdown(f'**{md(title)}**')
                    verdict = verdicts.get(iid, unknown)
                    reasons = '; '.join(verdict.reasons)
                    st.markdown(f'{fit.LABELS[verdict.colour]}' + (f' – {reasons}' if reasons else ''))
                    price_text = money(price, currency) + (' (gjeldende bud, auksjon)' if is_auction_only(options) else '')
                    if ship is not None:
                        price_text += f' + frakt {money(ship, ship_currency)}'
                    st.write(f'{price_text} · {seller or "Ukjent selger"} · {STATUS_LABELS.get(status, status)}')
                    if url and safe_url(url): st.link_button('Åpne annonse', url)
                    st.caption(f'Først sett: {first} · Sist sett: {last}')
                    if similar > 1: st.warning(f'{similar} annonser med samme selger og normalisert tittel – mulig relisting, ikke bekreftet.')
                    found = sorted(readings.get(iid, []), key=lambda r: measure.ORDER.index(r[0]))
                    analysis = analyses.get(iid)
                    if found:
                        lines = []
                        wanted = targets.get(types.get(iid), {})
                        for name, value_cm, raw_value, raw_unit, flat, source, confidence, note, verification_status in found:
                            label = measure.LABELS.get(name, name) + (' (flatt)' if name in measure.WIDTHS else '')
                            raw = f'{raw_value:g} {raw_unit}' + (', målt rundt' if name in measure.WIDTHS and not flat else '')
                            where_from = source.replace('photo', 'bilde').replace('text', 'teksten')
                            dot = fit.DOTS[verdict.per_reading[name][0]] + ' ' if name in verdict.per_reading else ''
                            status_text = {'provisional': 'AI-estimat – ikke verifisert', 'seller_unverified': 'Oppgitt av selger – ikke verifisert', 'legacy_unverified': 'Eldre måling – ikke verifisert', 'human_verified': 'Manuelt verifisert'}.get(verification_status, 'Ikke verifisert')
                            line = f'- {dot}{label}: **{value_cm:.1f} cm** ({raw}) · {where_from} · {status_text} · {CONFIDENCE_LABELS.get(confidence, confidence)}'
                            if name in wanted:
                                low, high = wanted[name]
                                line += ' · mål ' + (f'{low:g}–{high:g}' if low is not None and high is not None
                                                     else f'minst {low:g}' if low is not None else f'høyst {high:g}') + ' cm'
                            lines.append(line + (f' – {md(note)}' if note else ''))
                        st.markdown('**Mål fra annonsen (AI-mål er ikke verifiserte passformmål)**\n' + '\n'.join(lines))
                    elif analysis and analysis[0] == 'ok':
                        st.caption('Mål fra annonsen: ingen mål vist i bildene eller teksten.')
                    elif analysis and analysis[0] == 'error':
                        retry = 'prøves igjen ved neste analyse' if analysis[1] < MAX_ATTEMPTS else f'gitt opp etter {MAX_ATTEMPTS} forsøk'
                        st.caption(f'Måling feilet: {md(analysis[2])} ({retry})')
                    shown = photos.get(iid) or ([measure.full_size_photo(img)] if img and safe_url(img) else [])
                    if shown and st.toggle(f'Vis bilder ({len(shown)})', key='ph' + iid):
                        st.image(shown, width=240, caption=[f'Bilde {n}' for n in range(1, len(shown) + 1)])
                    with st.form('review' + iid):
                        choice = st.selectbox('Vurdering', REVIEW_STATUSES, index=REVIEW_STATUSES.index(status) if status in REVIEW_STATUSES else 0,
                                              format_func=STATUS_LABELS.get, key='rs' + iid)
                        comment = st.text_area('Begrunnelse / notater', value=notes, key='rn' + iid, height=80)
                        if st.form_submit_button('Lagre vurdering'):
                            conn.execute('''INSERT INTO listing_reviews(item_id,status,notes) VALUES(?,?,?) ON CONFLICT(item_id)
                              DO UPDATE SET status=excluded.status,notes=excluded.notes''', (iid, choice, comment))
                            conn.commit(); st.rerun()
        if not rows: st.info('Ingen annonser i dette utvalget ennå.')

    with tab_add:
        st.header('Manuell annonseimport')
        st.caption('Samme eBay-annonse oppdaterer den eksisterende registreringen, også om lenken har andre sporingsparametere '
                   'eller er en delelenke fra eBay-appen (ebay.us/…, ebay.io/…). Bildene og målene hentes ved neste analyse.')
        with st.form('manual'):
            title = st.text_input('Annonsetittel *')
            url = st.text_input('Annonse-URL *')
            x, y, z = st.columns(3)
            seller = x.text_input('Selger (valgfritt)')
            price = y.number_input('Pris (uten frakt)', min_value=0.0, step=5.0)
            currency = z.selectbox('Valuta', ['GBP', 'USD', 'EUR', 'NOK', 'SEK', 'DKK'])
            image = st.text_input('Bilde-URL (valgfritt)')
            wid = st.selectbox('Match garderobemål', list(names), format_func=lambda x: names[x])
            notes = st.text_area('Notater')
            if st.form_submit_button('Lagre annonse'):
                if not title.strip() or not safe_url(url): st.error('Oppgi tittel og gyldig http(s)-URL.')
                elif image and not safe_url(image): st.error('Ugyldig bilde-URL.')
                else:
                    try:
                        url = resolve_ebay_url(url.strip())
                    except requests.RequestException:
                        st.warning('Klarte ikke å følge delelenken, så annonsen lagres med lenken slik den er. '
                                   'Den kan da dukke opp to ganger hvis søket finner den senere.')
                    fresh = manual_add(conn, title.strip(), url, seller, float(price), currency, image, wid, notes)
                    st.success('Ny annonse registrert.' if fresh else 'Eksisterende annonse oppdatert.')

    with tab_fit:
        st.header('Passform og prishistorikk')
        st.subheader('Passformreferanser')
        problems = conn.execute("SELECT name,brand,size,fit,notes FROM owned_garments WHERE fit IN ('poor','needs_review') ORDER BY fit DESC, name").fetchall()
        for n, br, sz, rating, note in problems:
            st.info(f"**{n}**{' · ' + br if br else ''}{' · ' + sz if sz else ''} – {FIT_LABELS.get(rating, rating)}" + (f'\n\n{note}' if note else ''))
        if not problems:
            st.caption('Ingen registrerte plagg er markert med passformproblemer.')
        st.caption('Bruk faktiske mål, ikke bare etikettstørrelse.')
        st.subheader('Prishistorikk')
        histories = conn.execute('''SELECT p.item_id,l.title,p.observed_at,p.price,p.currency FROM price_history p
          LEFT JOIN listings l ON p.item_id=l.item_id ORDER BY p.observed_at DESC LIMIT 300''').fetchall()
        if histories:
            st.dataframe([{'Annonse': r[1], 'Dato': r[2], 'Pris': r[3], 'Valuta': r[4]} for r in histories], hide_index=True, width='stretch')
        else: st.caption('Ingen prisobservasjoner ennå.')
        st.subheader('Eksporter sikkerhetskopi')
        st.download_button('Last ned garderobeplan (JSON)', CATALOG.read_bytes(), file_name='wardrobe_backup.json', mime='application/json')
        st.caption(f'Databasen ligger lokalt i {DB.name}. Ta også kopi av denne filen når programmet er lukket.')
