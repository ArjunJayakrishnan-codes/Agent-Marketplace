import sqlite3
import os
p = os.path.join(os.path.dirname(__file__), 'Chinook.db')
print('db path=', p)
print('exists=', os.path.exists(p))
conn = sqlite3.connect(p)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('tables=')
for r in cur.fetchall():
    print('-', r[0])
conn.close()
