import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    try:
        database_url = os.environ.get('SUPABASE_DB_URL') or os.environ.get('DATABASE_URL')

        if database_url:
            return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

        host = os.environ.get('SUPABASE_DB_HOST')
        port = os.environ.get('SUPABASE_DB_PORT', '5432')
        dbname = os.environ.get('SUPABASE_DB_NAME', 'postgres')
        user = os.environ.get('SUPABASE_DB_USER', 'postgres')
        password = os.environ.get('SUPABASE_DB_PASSWORD')
        sslmode = os.environ.get('SUPABASE_DB_SSLMODE', 'require')

        if not host or not password:
            raise ValueError("Supabase DB credentials are missing. Set SUPABASE_DB_URL or SUPABASE_DB_HOST/SUPABASE_DB_PASSWORD.")

        return psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            sslmode=sslmode,
            cursor_factory=RealDictCursor,
        )
    except Exception as e:
        print(f"Database connection error: {e}")
        return None