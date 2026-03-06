import sqlite3

conn = sqlite3.connect("donors.db")
c = conn.cursor()

rows = c.execute("SELECT * FROM donors").fetchall()

for row in rows:
    print(row)

conn.close()
