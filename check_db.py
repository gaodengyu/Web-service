import sqlite3

con = sqlite3.connect('data.db')
cur = con.cursor()

print('tables:')
for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(row)

print('\nusers:')
for row in cur.execute('SELECT username, role, banned, profile FROM users'):
    print(row)

print('\norders:')
for row in cur.execute('SELECT id, player, booster, status, price, rating, comment, complaint FROM orders'):
    print(row)

con.close()