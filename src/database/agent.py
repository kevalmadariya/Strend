from src.core.db import get_db_connection

def find_agent_by_name(agent_name: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM agent
                WHERE template = %s;
                """,
                (agent_name,)
            )
            return cur.fetchone()
    finally:
        conn.close()
