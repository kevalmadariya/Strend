import psycopg2
from psycopg2.extras import RealDictCursor

import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "12345"),
    # "dbname": os.getenv("DB_NAME", "strend"),
    # "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}


def get_db_connection():
    """
    Returns a new database connection.
    Caller is responsible for closing it.
    """
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("go inside if")
        return psycopg2.connect(db_url)
    return psycopg2.connect(**DB_CONFIG)
