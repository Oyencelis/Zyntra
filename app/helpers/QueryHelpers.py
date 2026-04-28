from connection.db import get_db_connection 
from helpers.HelperFunction import responseData

def executePost(query, params=()):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn is None:
            return responseData("error", "Database connection is not available.", "", 500)

        cursor = conn.cursor()
        cursor.execute(query, params)

        last_inserted_id = None
        if query.strip().lower().startswith("insert"):
            try:
                cursor.execute("SELECT LASTVAL() AS last_inserted_id")
                last_row = cursor.fetchone()
                if last_row:
                    last_inserted_id = last_row.get('last_inserted_id')
            except Exception:
                last_inserted_id = None

        conn.commit()
        return {"last_inserted_id": last_inserted_id, "rowcount": cursor.rowcount}
    except Exception as e:
        if conn:
            conn.rollback()
        return responseData("error", "An error occurred: {}".format(str(e)), "", 200)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def executeGet(query, params=None):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn is None:
            return []

        cursor = conn.cursor()
        cursor.execute(query, params or [])
        
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        print("executeGet error:", str(e))
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
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