import sqlite3

conn = sqlite3.connect('wardrobe.sqlite3')

print("Columns in listings:")
print([r[1] for r in conn.execute("PRAGMA table_info(listings)")])

print("\nListings with measurements:")
rows = conn.execute("SELECT item_id, substr(measurements,1,120) FROM listings WHERE measurements != ''").fetchall()
if not rows:
    print("  (none)")
for row in rows:
    print(" ", row)