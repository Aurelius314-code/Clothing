"""Local visual UI. Run: python -m streamlit run app.py"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

import streamlit as st

from watcher import ROOT, DB, CATALOG, connect, fingerprint

st.set_page_config(page_title='Vintage Wardrobe Watcher', page_icon='🧥', layout='wide')



def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def inventory_db(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS owned_garments (
        garment_id INTEGER PRIMARY KEY AUTOINCREMENT, wardrobe_id TEXT, name TEXT NOT NULL,
        brand TEXT DEFAULT '', size TEXT DEFAULT '', fit TEXT DEFAULT 'good',
        notes TEXT DEFAULT '', image_url TEXT DEFAULT '', created_at TEXT NOT NULL)''')
    if conn.execute('SELECT COUNT(*) FROM owned_garments').fetchone()[0] == 0:
        seed = [
            ('W001','British Warm overcoat','Dunn & Co','', 'good','Crombie cloth; owned; check fit and condition',''),
            ('W009','High-waisted pleated chinos','Polo Ralph Lauren','W38 L30','poor','Waist too tight when sitting; needs unbuttoning when driving; not a satisfactory fit',''),
            ('W010','Second high-waisted pleated trousers','','','needs_review','Waist fit not yet measured or confirmed; category is provisional','')]
        conn.executemany('INSERT INTO owned_garments(wardrobe_id,name,brand,size,fit,notes,image_url,created_at) VALUES(?,?,?,?,?,?,?,?)',
            [(*r,now()) for r in seed])
    conn.commit()


def read_catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def write_catalog(data):
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def safe_url(url):
    p=urlparse(url.strip())
    return p.scheme in ('https','http') and bool(p.netloc) and not p.username and not p.password


def manual_add(conn, title, url, seller, price, currency, image, wid, notes):
    url=url.strip()
    key='manual:'+hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
    old=conn.execute('SELECT price,currency FROM listings WHERE item_id=?',(key,)).fetchone()
    t=now()
    conn.execute('''INSERT INTO listings(item_id,title,url,image_url,seller,price,currency,first_seen,last_seen,fingerprint,notes)
      VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET title=excluded.title,
      image_url=excluded.image_url,seller=excluded.seller,price=excluded.price,currency=excluded.currency,
      last_seen=excluded.last_seen,notes=excluded.notes''',
      (key,title,url,image,seller,price,currency,t,t,fingerprint(title,seller),notes))
    if wid:
        conn.execute('INSERT OR IGNORE INTO matches(item_id,wardrobe_id) VALUES(?,?)',(key,wid))
    if old is None or tuple(old)!=(price,currency):
        conn.execute('INSERT OR IGNORE INTO price_history(item_id,observed_at,price,currency) VALUES(?,?,?,?)',(key,t,price,currency))
    conn.commit()
    return old is None


def badge(status):
    return {'saved':'⭐ Lagret','rejected':'Avvist','purchased':'Kjøpt','unreviewed':'Ikke vurdert'}.get(status,status)


with connect() as conn:
    inventory_db(conn)
    catalog=read_catalog()
    items=catalog['items']
    names={i['id']:i['name'] for i in items}
    tabs=st.tabs(['🏠 Oversikt','🧥 Garderobe','🔎 Annonser','➕ Legg til annonse','📏 Passform og historikk'])

    with tabs[0]:
        st.title('Vintage Wardrobe Watcher')
        st.caption('Din lokale vintage-garderobe. Ingen eBay-tilgang kreves for å bruke disse sidene.')
        total=sum(int(i['target_quantity']) for i in items)
        owned=sum(int(i['owned_quantity']) for i in items)
        listed=conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
        saved=conn.execute("SELECT COUNT(*) FROM listing_reviews WHERE status='saved'").fetchone()[0]
        a,b,c,d=st.columns(4)
        a.metric('Planlagte enheter',total); b.metric('Registrert eid',owned); c.metric('Arkiverte annonser',listed); d.metric('Lagrede annonser',saved)
        st.progress(min(owned/total,1) if total else 0)
        st.subheader('Neste prioriterte plagg')
        pending=sorted((i for i in items if i['enabled'] and i['owned_quantity']<i['target_quantity']),key=lambda x:(x['priority'],x['category']))
        for i in pending[:12]:
            with st.container(border=True):
                st.markdown(f"**{i['name']}** · {i['category']} · prioritet {i['priority']}")
                st.caption(i.get('notes',''))

    with tabs[1]:
        st.header('Garderobeplan')
        st.caption('Antall og søkestatus lagres i wardrobe.json. Eksisterende data beholdes.')
        categories=sorted({i['category'] for i in items})
        cat=st.selectbox('Kategori', ['Alle']+categories)
        for i in items:
            if cat!='Alle' and i['category']!=cat: continue
            with st.expander(f"{i['name']}  ·  {i['owned_quantity']}/{i['target_quantity']}"):
                st.caption(i.get('notes',''))
                c1,c2,c3,c4=st.columns(4)
                q=c1.number_input('Antall eid',0,100,int(i['owned_quantity']),key='qty'+i['id'])
                target=c2.number_input('Ønsket antall',0,100,int(i['target_quantity']),key='target'+i['id'])
                priority=c3.number_input('Prioritet (1=høy)',1,10,int(i['priority']),key='prio'+i['id'])
                enabled=c4.checkbox('Aktivt søk',value=bool(i['enabled']),key='enable'+i['id'])
                if st.button('Lagre endringer',key='save'+i['id']):
                    i.update(owned_quantity=q,target_quantity=target,priority=priority,enabled=enabled)
                    write_catalog(catalog)
                    st.success('Lagret.'); st.rerun()
        st.divider()
        st.subheader('Mine faktiske plagg')
        with st.form('add_garment'):
            name=st.text_input('Navn på plagget')
            wid=st.selectbox('Tilhører garderobemål',list(names),format_func=lambda x:names[x])
            x,y=st.columns(2)
            brand=x.text_input('Merke'); size=y.text_input('Størrelse')
            fit=st.selectbox('Passform', ['good','needs_review','poor'],format_func=lambda x:{'good':'God','needs_review':'Må vurderes','poor':'Problem / bør erstattes'}[x])
            notes=st.text_area('Notater om passform, tilstand og mål')
            image=st.text_input('Bilde-URL (valgfritt)')
            if st.form_submit_button('Registrer plagg'):
                if not name.strip(): st.error('Oppgi navn')
                elif image and not safe_url(image): st.error('Ugyldig bilde-URL')
                else:
                    conn.execute('INSERT INTO owned_garments(wardrobe_id,name,brand,size,fit,notes,image_url,created_at) VALUES(?,?,?,?,?,?,?,?)',(wid,name,brand,size,fit,notes,image,now()))
                    conn.commit(); st.success('Plagg registrert. Antall eid i garderobeplanen oppdateres separat.'); st.rerun()
        garments=conn.execute('SELECT garment_id,name,brand,size,fit,notes,image_url FROM owned_garments ORDER BY garment_id DESC').fetchall()
        for gid,n,br,sz,fit,note,img in garments:
            with st.container(border=True):
                st.markdown(f'**{n}** · {br} · {sz} · {fit}')
                st.caption(note)
                if img and safe_url(img): st.image(img,width=180)
                if st.button('Slett denne registreringen',key='delg'+str(gid)):
                    conn.execute('DELETE FROM owned_garments WHERE garment_id=?',(gid,));conn.commit();st.rerun()

    with tabs[2]:
        st.header('Annonsearkiv')
        st.caption('Gamle annonser beholdes, også når de ikke lenger er aktive på eBay.')
        statuses=['Alle','unreviewed','saved','rejected','purchased']
        filter_status=st.selectbox('Vurdering',statuses)
        rows=conn.execute('''SELECT l.item_id,l.title,l.url,l.image_url,l.seller,l.price,l.currency,
          l.first_seen,l.last_seen,COALESCE(r.status,l.status),COALESCE(r.notes,l.notes),l.fingerprint
          FROM listings l LEFT JOIN listing_reviews r ON l.item_id=r.item_id ORDER BY l.first_seen DESC LIMIT 2000''').fetchall()
        shown=0
        for row in rows:
            iid,title,url,img,seller,price,currency,first,last,status,notes,fp=row
            if filter_status!='Alle' and status!=filter_status: continue
            shown+=1
            with st.container(border=True):
                left,right=st.columns([1,4])
                with left:
                    if img and safe_url(img): st.image(img,use_container_width=True)
                with right:
                    st.markdown(f'**{title}**')
                    st.write(f'{price if price is not None else "?"} {currency} · {seller or "Ukjent selger"} · {badge(status)}')
                    if url and safe_url(url): st.link_button('Åpne annonse',url)
                    st.caption(f'Først sett: {first} · Sist sett: {last}')
                    count=conn.execute('SELECT COUNT(*) FROM listings WHERE fingerprint=?',(fp,)).fetchone()[0]
                    if count>1: st.warning(f'{count} annonser med samme selger og normalisert tittel – mulig relisting, ikke bekreftet.')
                    with st.form('review'+iid):
                        choice=st.selectbox('Vurdering',['unreviewed','saved','rejected','purchased'],index=['unreviewed','saved','rejected','purchased'].index(status) if status in ['unreviewed','saved','rejected','purchased'] else 0)
                        comment=st.text_input('Begrunnelse / notater',value=notes or '')
                        if st.form_submit_button('Lagre vurdering'):
                            conn.execute('''INSERT INTO listing_reviews(item_id,status,notes) VALUES(?,?,?) ON CONFLICT(item_id)
                              DO UPDATE SET status=excluded.status,notes=excluded.notes''',(iid,choice,comment))
                            conn.commit();st.rerun()
        if not shown: st.info('Ingen annonser i dette utvalget ennå.')

    with tabs[3]:
        st.header('Manuell annonseimport')
        st.caption('Legg inn eBay-annonser mens vi venter på API-tilgang. Samme URL oppdaterer den eksisterende registreringen.')
        with st.form('manual'):
            title=st.text_input('Annonsetittel *')
            url=st.text_input('Annonse-URL *')
            x,y,z=st.columns(3)
            seller=x.text_input('Selger (valgfritt)')
            price=y.number_input('Pris (uten frakt)',min_value=0.0,step=5.0)
            currency=z.selectbox('Valuta',['GBP','USD','EUR','NOK','SEK','DKK'])
            image=st.text_input('Bilde-URL (valgfritt)')
            wid=st.selectbox('Match garderobemål',list(names),format_func=lambda x:names[x])
            notes=st.text_area('Notater')
            if st.form_submit_button('Lagre annonse'):
                if not title.strip() or not safe_url(url): st.error('Oppgi tittel og gyldig http(s)-URL.')
                elif image and not safe_url(image): st.error('Ugyldig bilde-URL.')
                else:
                    fresh=manual_add(conn,title.strip(),url,seller,float(price),currency,image,wid,notes)
                    st.success('Ny annonse registrert.' if fresh else 'Eksisterende annonse oppdatert.')

    with tabs[4]:
        st.header('Passform og prishistorikk')
        st.info('Foreløpig passformreferanse: Polo Ralph Lauren W38 L30 har for trang midje ved sitting. Bruk faktiske mål, ikke bare etikettstørrelse.')
        st.subheader('Prishistorikk')
        histories=conn.execute('''SELECT p.item_id,l.title,p.observed_at,p.price,p.currency FROM price_history p
          LEFT JOIN listings l ON p.item_id=l.item_id ORDER BY p.observed_at DESC LIMIT 300''').fetchall()
        if histories:
            st.dataframe([{'Annonse':r[1], 'Dato':r[2], 'Pris':r[3], 'Valuta':r[4]} for r in histories],hide_index=True,use_container_width=True)
        else: st.caption('Ingen prisobservasjoner ennå.')
        st.subheader('Eksporter sikkerhetskopi')
        st.download_button('Last ned garderobeplan (JSON)',CATALOG.read_bytes(),file_name='wardrobe_backup.json',mime='application/json')
        st.caption(f'Databasen ligger lokalt i {DB.name}. Ta også kopi av denne filen når programmet er lukket.')
