from src.core.db import get_db_connection


def insert_one(table: str, data: dict, returning: str | None = None):
    """
    Insert one row into a table.

    :param table: table name
    :param data: dict of column -> value
    :param returning: column name to return (e.g. "user_id")
    :return: returned value or None
    """
    conn = get_db_connection()
    try:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        values = tuple(data.values())

        sql = f"""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
        """

        if returning:
            sql += f" RETURNING {returning};"

        with conn.cursor() as cur:
            cur.execute(sql, values)
            result = cur.fetchone() if returning else None
            conn.commit()

        return result[0] if result else None
    finally:
        conn.close()
