"""Show how far the photo analysis has come: python check.py"""
import watcher

with watcher.connect() as conn:
    q = lambda sql, *args: conn.execute(sql, args).fetchall()
    print('Listings:', q('SELECT COUNT(*) FROM listings')[0][0])
    print('Analysed:', dict(q('SELECT status, COUNT(*) FROM listing_analysis GROUP BY status')) or '(none yet)')
    print('Waiting for analysis:', len(watcher.pending_analysis(conn, 10**9)))
    print('Listings with measurements:', q('SELECT COUNT(DISTINCT item_id) FROM listing_measurements')[0][0])

    print('\nLatest readings:')
    for title, name, value_cm, source, confidence in q('''SELECT l.title, m.name, m.value_cm, m.source, m.confidence
            FROM listing_measurements m JOIN listings l ON l.item_id=m.item_id
            JOIN listing_analysis a ON a.item_id=m.item_id ORDER BY a.analyzed_at DESC LIMIT 15'''):
        print(f'  {title[:45]:<45} {name:<12} {value_cm:6.1f} cm  {source}, {confidence}')

    errors = q('''SELECT l.title, a.attempts, a.error FROM listing_analysis a JOIN listings l ON l.item_id=a.item_id
                  WHERE a.status='error' ORDER BY a.analyzed_at DESC LIMIT 10''')
    if errors:
        print('\nFailed analyses:')
        for title, attempts, error in errors:
            print(f'  {title[:45]:<45} attempt {attempts}: {error}')
