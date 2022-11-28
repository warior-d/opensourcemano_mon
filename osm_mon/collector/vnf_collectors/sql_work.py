import sqlite3

def sql_connection():
    con = sqlite3.connect('rate.db')
    return con

def sql_insert(title, time_check, value, resource_id):
    connector = sql_connection()
    cursor = connector.cursor()
    cursor.execute("INSERT INTO metrics (title, curtime, value, resource_id) VALUES(? ,?, ?, ?)", [title, time_check, value, resource_id])
    connector.commit()
    connector.close()

def sql_select(title, resource_id):
    connector = sql_connection()
    cursor = connector.cursor()
    try:
        cursor.execute('SELECT title, curtime, value, resource_id from metrics where title = ? and resource_id = ? and curtime = (select max(curtime) from metrics where title = ? and resource_id = ? )', [title, resource_id, title, resource_id])
        rows = cursor.fetchone()
        connector.close()
        if rows == []:
            return (0, 0, 0)    
        else:
            return rows
    except sqlite3.OperationalError:
        if(sqlite3.OperationalError):
            try:
                cursor.execute('CREATE TABLE metrics (title text, curtime real, value real, resource_id text)')
            except sqlite3.Error() as e:
                print(e, " occured")
    connector.commit()
    connector.close()