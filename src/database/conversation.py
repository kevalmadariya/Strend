from src.core.db import get_db_connection

def find_conversation_by_id(conversation_id: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM conversation
                WHERE conversation_id = %s;
                """,
                (conversation_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()

