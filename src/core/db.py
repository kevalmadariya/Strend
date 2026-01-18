import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "user": "postgres",
    "password": "12345",
}


def get_db_connection():
    """
    Returns a new database connection.
    Caller is responsible for closing it.
    """
    return psycopg2.connect(**DB_CONFIG)
