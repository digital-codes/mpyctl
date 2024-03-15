import sqlite3
from sqlite3 import Error

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
                      address TEXT NOT NULL,
                      config TEXT NOT NULL)''')
    except Error as e:
        print(e)


# Function to insert a new row with MAC address
def insert_row(conn, json_string, mac_address):
    try:
        sql = ''' INSERT INTO devices(config, address)
                  VALUES(?,?) '''
        cur = conn.cursor()
        cur.execute(sql, (json_string, mac_address))
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

# Database file
db_file = 'devices.db'

# Create a database connection
conn = create_connection(db_file)

if conn is not None:
    # Create table
    create_table(conn)

    # Insert a new row with JSON string and MAC address
    json_string = '{"name": "Alice", "age": 28, "city": "Los Angeles"}'
    mac_address = "00:1B:3C:4D:5E:6F"
    row_id = insert_row(conn, json_string, mac_address)

    # Retrieve the ID of the latest row
    latest_id = get_latest_id(conn)
    print("Latest:",latest_id)

    # Close connection
    conn.close()

    latest_id
else:
    print("Error! cannot create the database connection.")


