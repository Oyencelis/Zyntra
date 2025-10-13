from mysql.connector import Error
from connection.db import get_db_connection 
from helpers.HelperFunction import responseData

def executePost(query, params=()):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        conn.commit()
        last_inserted_id = cursor.lastrowid
        return {"last_inserted_id": last_inserted_id, "rowcount": cursor.rowcount}
    except Error as e:
        return responseData("error", "An error occurred: {}".format(str(e)), "", 200)
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def executeGet(query, params=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or [])
        
        rows = cursor.fetchall()
        return rows
    except Error as e:
        return responseData("error", "An error occurred: {}".format(str(e)), "", 200)
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

def changeStatus(table_name, id_field, value_id, status_to):
    query = f"UPDATE {table_name} SET status = %s WHERE {id_field} = %s"
    try:
        result = executePost(query, (status_to, value_id))
        if result:
            return True
        return False
    except Exception as e:
        print(f"Error: {str(e)}")  
        return responseData("error", "Something went wrong!", "", 200)
    
def changeRole(table_name, id_field, value_id, status_to):
    query = f"UPDATE {table_name} SET role_id = %s WHERE {id_field} = %s"
    try:
        result = executePost(query, (status_to, value_id))
        if result:  
            return True
        return False
    except Exception as e:
        print(f"Error: {str(e)}")  
        return responseData("error", "Something went wrong!", "", 200)