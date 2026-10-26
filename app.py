"""Local visual UI. Run: python -m streamlit run app.py"""
import hashlib
import json
import os
import tempfile
from urllib.parse import urlparse

import streamlit as st

from watcher import (DB, CATALOG, REVIEW_STATUSES, connect, ebay_item_key, fingerprint,
                     has_flag, is_auction_only, set_flag, utc_now)

st.set_page_config(page_title='Vintage Wardrobe Watcher', page_icon='🧥', layout='wide')

PAGE_SIZE = 50
STATUS_LABELS = {'saved': '⭐ Lagret', 'rejected': 'Avvist', 'purchased': 'Kjøpt', 'unreviewed': 'Ikke vurdert'}
FIT_LABELS = {'good': 'God', 'needs_review': 'Må vurderes', 'poor': 'Problem / bør erstattes'}

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


def manual_add(conn, title, url, seller, price, currency, image, wid, notes):
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
    if notes.strip():
        conn.execute('''INSERT INTO listing_reviews(item_id,status,notes) VALUES(?,'unreviewed',?)
          ON CONFLICT(item_id) DO UPDATE SET notes=excluded.notes''', (key, notes.strip()))
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

    tabs = st.tabs(['🏠 Oversikt', '🧥 Garderobe', '🔎 Annonser', '➕ Legg til annonse', '📏 Passform og historikk'])

    with tabs[0]:
        st.title('Vintage Wardrobe Watcher')
        st.caption('Din lokale vintage-garderobe. Ingen eBay-tilgang kreves for å bruke disse sidene.')
        total = sum(int(i['target_quantity']) for i in items)
        owned = sum(int(i['owned_quantity']) for i in items)
        listed = conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
        saved = conn.execute("SELECT COUNT(*) FROM listing_reviews WHERE status='saved'").fetchone()[0]
        a, b, c, d = st.columns(4)
        a.metric('Planlagte enheter', total); b.metric('Registrert eid', owned); c.metric('Arkiverte annonser', listed); d.metric('Lagrede annonser', saved)
        st.progress(min(owned / total, 1) if total else 0)
        st.subheader('Neste prioriterte plagg')
        pending = sorted((i for i in items if i['enabled'] and i['owned_quantity'] < i['target_quantity']), key=lambda x: (x['priority'], x['category']))
        for i in pending[:12]:
            with st.container(border=True):
                st.markdown(f"**{i['name']}** · {i['category']} · prioritet {i['priority']}")
                st.caption(i.get('notes', ''))

    with tabs[1]:
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
            fit = st.selectbox('Passform', list(FIT_LABELS), format_func=FIT_LABELS.get)
            notes = st.text_area('Notater om passform, tilstand og mål')
            image = st.text_input('Bilde-URL (valgfritt)')
            if st.form_submit_button('Registrer plagg'):
                if not name.strip(): st.error('Oppgi navn')
                elif image and not safe_url(image): st.error('Ugyldig bilde-URL')
                else:
                    conn.execute('INSERT INTO owned_garments(wardrobe_id,name,brand,size,fit,notes,image_url,created_at) VALUES(?,?,?,?,?,?,?,?)', (wid, name, brand, size, fit, notes, image, utc_now()))
                    conn.commit(); st.success('Plagg registrert. Antall eid i garderobeplanen oppdateres separat.'); st.rerun()
        garments = conn.execute('SELECT garment_id,wardrobe_id,name,brand,size,fit,notes,image_url FROM owned_garments ORDER BY garment_id DESC').fetchall()
        for gid, gwid, n, br, sz, fit, note, img in garments:
            with st.container(border=True):
                st.markdown(f'**{n}** · {br} · {sz} · {FIT_LABELS.get(fit, fit)}')
                st.caption(note)
                if img and safe_url(img): st.image(img, width=180)
                options = target_options(gwid)
                left, right = st.columns([3, 1], vertical_alignment='bottom')
                new_wid = left.selectbox('Garderobemål', options, index=options.index(gwid), format_func=target_label, key=f'gw{gid}')
                if right.button('Lagre mål', key=f'gws{gid}', disabled=new_wid == gwid):
                    conn.execute('UPDATE owned_garments SET wardrobe_id=? WHERE garment_id=?', (new_wid, gid)); conn.commit(); st.rerun()
                if st.button('Slett denne registreringen', key='delg' + str(gid)):
                    conn.execute('DELETE FROM owned_garments WHERE garment_id=?', (gid,)); conn.commit(); st.rerun()

    with tabs[2]:
        st.header('Annonsearkiv')
        st.caption('Gamle annonser beholdes, også når de ikke lenger er aktive på eBay.')
        filter_status = st.selectbox('Vurdering', ['Alle', *REVIEW_STATUSES], format_func=lambda s: STATUS_LABELS.get(s, s))
        where, args = ('', ()) if filter_status == 'Alle' else ("WHERE COALESCE(r.status,'unreviewed')=?", (filter_status,))
        total = conn.execute(f'SELECT COUNT(*) FROM listings l LEFT JOIN listing_reviews r ON l.item_id=r.item_id {where}', args).fetchone()[0]
        pages = max(1, -(-total // PAGE_SIZE))
        # No key on purpose: the label changes with the filter and count, which starts the selector back on page 1.
        page = st.number_input(f'Side (av {pages}, {total} annonser)', 1, pages, 1) if pages > 1 else 1
        rows = conn.execute(f'''SELECT l.item_id,l.title,l.url,l.image_url,l.seller,l.price,l.currency,
          l.shipping_cost,l.shipping_currency,l.buying_options,l.first_seen,l.last_seen,
          COALESCE(r.status,'unreviewed'),COALESCE(r.notes,l.notes,''),
          (SELECT COUNT(*) FROM listings x WHERE x.fingerprint=l.fingerprint)
          FROM listings l LEFT JOIN listing_reviews r ON l.item_id=r.item_id {where}
          ORDER BY l.first_seen DESC LIMIT ? OFFSET ?''', (*args, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
        for (iid, title, url, img, seller, price, currency, ship, ship_currency, options,
             first, last, status, notes, similar) in rows:
            with st.container(border=True):
                left, right = st.columns([1, 4])
                with left:
                    if img and safe_url(img): st.image(img, width='stretch')
                with right:
                    st.markdown(f'**{title}**')
                    price_text = money(price, currency) + (' (gjeldende bud, auksjon)' if is_auction_only(options) else '')
                    if ship is not None:
                        price_text += f' + frakt {money(ship, ship_currency)}'
                    st.write(f'{price_text} · {seller or "Ukjent selger"} · {STATUS_LABELS.get(status, status)}')
                    if url and safe_url(url): st.link_button('Åpne annonse', url)
                    st.caption(f'Først sett: {first} · Sist sett: {last}')
                    if similar > 1: st.warning(f'{similar} annonser med samme selger og normalisert tittel – mulig relisting, ikke bekreftet.')
                    with st.form('review' + iid):
                        choice = st.selectbox('Vurdering', REVIEW_STATUSES, index=REVIEW_STATUSES.index(status) if status in REVIEW_STATUSES else 0,
                                              format_func=STATUS_LABELS.get, key='rs' + iid)
                        comment = st.text_input('Begrunnelse / notater', value=notes, key='rn' + iid)
                        if st.form_submit_button('Lagre vurdering'):
                            conn.execute('''INSERT INTO listing_reviews(item_id,status,notes) VALUES(?,?,?) ON CONFLICT(item_id)
                              DO UPDATE SET status=excluded.status,notes=excluded.notes''', (iid, choice, comment))
                            conn.commit(); st.rerun()
        if not rows: st.info('Ingen annonser i dette utvalget ennå.')

    with tabs[3]:
        st.header('Manuell annonseimport')
        st.caption('Legg inn eBay-annonser mens vi venter på API-tilgang. Samme eBay-annonse oppdaterer den eksisterende registreringen, også om lenken har andre sporingsparametere.')
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
                    fresh = manual_add(conn, title.strip(), url, seller, float(price), currency, image, wid, notes)
                    st.success('Ny annonse registrert.' if fresh else 'Eksisterende annonse oppdatert.')

    with tabs[4]:
        st.header('Passform og prishistorikk')
        st.subheader('Passformreferanser')
        problems = conn.execute("SELECT name,brand,size,fit,notes FROM owned_garments WHERE fit IN ('poor','needs_review') ORDER BY fit DESC, name").fetchall()
        for n, br, sz, fit, note in problems:
            st.info(f"**{n}**{' · ' + br if br else ''}{' · ' + sz if sz else ''} – {FIT_LABELS.get(fit, fit)}" + (f'\n\n{note}' if note else ''))
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
