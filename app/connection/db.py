import mysql.connector
from mysql.connector import Error

# Function to connect to MySQL database
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',      # MySQL host, usually localhost
            user='root',   # Your MySQL username
            password='',  # Your MySQL password
            database='zyntra'      # The name of the database
        )
        return conn
    except Error as e:
        print(f"Error: {e}")
        return None