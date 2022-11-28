import sqlite3

db = sqlite3.connect('rate.db')

c = db.cursor()

c.execute("""CREATE TABLE metrics (
    title text,
    curtime integer,
    value integer
)
""")

db.commit()

db.close()
