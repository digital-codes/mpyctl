"""create and maintain mpyctl device database"""
import sqlite3
from sqlite3 import Error
import os

# defs
# Device name
_devName = "MpyCtl"

# Database file
#_db_dir = "/home/kugel/daten/work/database/mpyctl"
_db_dir = "."
_db_name = 'devices.db'
_database = os.sep.join(_db_dir.split("/") + [_db_name])
print("DB:",_database)


class DatabaseManager:
    def __init__(self, db_file):
        """
        Initialize the DatabaseManager class.

        Args:
            db_file (str): The path to the SQLite database file.
        """
        self.conn = self.create_connection(db_file)

    def create_connection(self, db_file):
        """
        Create a database connection to a SQLite database.

        Args:
            db_file (str): The path to the SQLite database file.

        Returns:
            conn (sqlite3.Connection): The database connection object.
        """
        conn = None
        try:
            conn = sqlite3.connect(db_file)
            return conn
        except Error as e:
            print(e)
        return conn

    def create_tables(self):
        """
        Create the 'devices' table if it doesn't exist.
        """
        try:
            c = self.conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS devices
                            (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            address TEXT NOT NULL,
                            config TEXT NOT NULL)''')
        except Error as e:
            print(e)

    def insert_row(self, json_string, mac_address, dev_name):
        """
        Insert a new row into the 'devices' table.

        Args:
            json_string (str): The JSON string to be inserted.
            mac_address (str): The MAC address to be inserted.
            dev_name (str): The name to be inserted.

        Returns:
            row_id (int): The ID of the inserted row.
        """
        try:
            sql = ''' INSERT INTO devices(config, address, name)
                        VALUES(?,?,?) '''
            cur = self.conn.cursor()
            cur.execute(sql, (json_string, mac_address, dev_name))
            self.conn.commit()
            return cur.lastrowid
        except Error as e:
            print(e)

    def get_latest_id(self):
        """
        Get the ID of the latest row in the 'devices' table.

        Returns:
            latest_id (int): The ID of the latest row.
        """
        try:
            sql = ''' SELECT id FROM devices ORDER BY id DESC LIMIT 1'''
            cur = self.conn.cursor()
            cur.execute(sql)
            latest_id = cur.fetchone()
            return latest_id[0] if latest_id else 0
        except Error as e:
            print(e)

    def get_by_name(self, name):
        """
        Get rows from the 'devices' table by name.

        Args:
            name (str): The name to search for.

        Returns:
            rows (list): A list of rows matching the name.
        """
        try:
            sql = ''' SELECT * FROM devices WHERE name = ?'''
            cur = self.conn.cursor()
            cur.execute(sql, (name,))
            rows = cur.fetchall()
            return rows
        except Error as e:
            print(e)

    def get_by_id(self, id):
        """
        Get rows from the 'devices' table by ID.

        Args:
            id (int): The ID to search for.

        Returns:
            rows (list): A list of rows matching the ID.
        """
        try:
            sql = ''' SELECT * FROM devices WHERE id = ?'''
            cur = self.conn.cursor()
            cur.execute(sql, (id,))
            rows = cur.fetchall()
            return rows
        except Error as e:
            print(e)

    def close(self):
        """
        Close the database connection.
        """
        self.conn.close()

def main():
    # Create a database connection
    dbm = DatabaseManager(_database)

    # Create table
    dbm.create_tables()

    # Insert a new row with JSON string and MAC address
    data = '{"name": "Alice", "age": 28, "city": "Los Angeles"}'
    address = "00:1B:3C:4D:5E:6F"

    latest_id = dbm.get_latest_id()
    if latest_id == None:
        latest_id = 0
    print("Latest:",latest_id)

    name = "_".join([_devName,f"{(latest_id + 1):04}"])
    row_id = dbm.insert_row(data, address,name)

    # Retrieve the ID of the latest row
    latest_id = dbm.get_latest_id()
    print("New:",latest_id)

    # Close connection
    dbm.close()

if __name__ == "__main__":
    main()

