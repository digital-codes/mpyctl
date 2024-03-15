"""create and maintain mpyctl device database"""
import sqlite3
from sqlite3 import Error
import os

# defs
# Device name
_devName = "MpyCtl"

# Database file
_db_dir = "/home/kugel/daten/work/database/mpyctl"
_db_name = 'devices.db'
_database = os.sep.join(_db_dir.split("/") + [_db_name])
print("DB:",_database)


# Define function to create connection to SQLite database
def create_connection(db_file):
    """ Create a database connection to a SQLite database """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(e)

    return conn

# Function to create table
def create_table(conn):
    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS devices
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT NOT NULL,
                      address TEXT NOT NULL,
                      config TEXT NOT NULL)''')
    except Error as e:
        print(e)


# Function to insert a new row with MAC address
def insert_row(conn, json_string, mac_address, dev_name):
    try:
        sql = ''' INSERT INTO devices(config, address, name)
                  VALUES(?,?,?) '''
        cur = conn.cursor()
        cur.execute(sql, (json_string, mac_address, dev_name))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(e)

# Function to get the ID of the latest row
def get_latest_id(conn):
    try:
        sql = ''' SELECT id FROM devices ORDER BY id DESC LIMIT 1'''
        cur = conn.cursor()
        cur.execute(sql)
        latest_id = cur.fetchone()
        return latest_id[0] if latest_id else None
    except Error as e:
        print(e)


# Create a database connection
conn = create_connection(_database)

if conn is not None:
    # Create table
    create_table(conn)

    # Insert a new row with JSON string and MAC address
    data = '{"name": "Alice", "age": 28, "city": "Los Angeles"}'
    address = "00:1B:3C:4D:5E:6F"

    latest_id = get_latest_id(conn)
    if latest_id == None:
        latest_id = 0
    print("Latest:",latest_id)

    name = "_".join([_devName,f"{(latest_id + 1):04}"])
    row_id = insert_row(conn, data, address,name)

    # Retrieve the ID of the latest row
    latest_id = get_latest_id(conn)
    print("New:",latest_id)

    # Close connection
    conn.close()

    latest_id
else:
    print("Error! cannot create the database connection.")


