from src.core.db import get_db_connection


def find_user_by_id(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM "user" WHERE user_id = %s;',
                (user_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()


