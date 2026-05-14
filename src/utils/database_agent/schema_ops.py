
"""
Schema Operations
==================
Single Responsibility: Schema inference, DDL (CREATE TABLE), data loading,
and schema introspection on PostgreSQL databases.
Does NOT generate queries from natural language — that's query_builder's job.
"""

from typing import List, Dict, Any
from psycopg2.extras import RealDictCursor, RealDictRow


# ─── Type Inference ─────────────────────────────────────────────────────────

def _infer_single_type(value: Any) -> str:
    """Infer PostgreSQL type from a single Python value."""
    if value is None:
        return "TEXT"  # Default to TEXT for null
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    # Try parsing string as number
    if isinstance(value, str):
        try:
            int(value)
            return "INTEGER"
        except (ValueError, TypeError):
            pass
        try:
            float(value)
            return "REAL"
        except (ValueError, TypeError):
            pass
    return "TEXT"


def infer_column_types(rows: List[Dict[str, Any]], sample_size: int = 2) -> Dict[str, str]:
    """
    Infer PostgreSQL column types from the first N rows.

    Priority: REAL > INTEGER > TEXT (if mixed types found, pick the broadest).

    Args:
        rows: List of row dicts
        sample_size: Number of rows to inspect (default: 2)

    Returns:
        Dict mapping column_name -> PostgreSQL type ('TEXT', 'INTEGER', 'REAL', 'BOOLEAN')
    """
    if not rows:
        return {}

    sample = rows[:sample_size]
    columns = list(sample[0].keys())
    schema = {}

    type_priority = {"TEXT": 0, "BOOLEAN": 1, "INTEGER": 2, "REAL": 2}

    for col in columns:
        detected_types = set()
        for row in sample:
            val = row.get(col)
            detected_types.add(_infer_single_type(val))

        # If mixed numeric types, prefer REAL; if any TEXT, use TEXT
        if "TEXT" in detected_types:
            has_real_text = False
            for row in sample:
                val = row.get(col)
                if val is not None and isinstance(val, str):
                    try:
                        float(val)
                    except (ValueError, TypeError):
                        has_real_text = True
                        break

            if has_real_text:
                schema[col] = "TEXT"
            elif "REAL" in detected_types:
                schema[col] = "REAL"
            else:
                schema[col] = "INTEGER"
        elif "REAL" in detected_types:
            schema[col] = "REAL"
        elif "INTEGER" in detected_types:
            schema[col] = "INTEGER"
        else:
            schema[col] = "TEXT"

    return schema


# ─── DDL Operations ─────────────────────────────────────────────────────────

def create_table(conn, table_name: str, schema: Dict[str, str]) -> None:
    """
    Create a table with the given schema on PostgreSQL.

    Args:
        conn: psycopg2 connection
        table_name: Name of the table to create
        schema: Dict mapping column_name -> PostgreSQL type

    Raises:
        ValueError: If schema is empty
    """
    if not schema:
        raise ValueError("Cannot create table with empty schema")

    columns_sql = ", ".join(
        f'"{col}" {col_type}' for col, col_type in schema.items()
    )

    sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (id SERIAL PRIMARY KEY, {columns_sql});'
    with conn.cursor() as cursor:
        cursor.execute(sql)
    conn.commit()
    print(f"[+] Created table '{table_name}' with {len(schema)} columns")


# ─── Data Loading ────────────────────────────────────────────────────────────

def bulk_insert(conn, table_name: str, rows: List[Dict[str, Any]]) -> int:
    """
    Batch-insert all rows into the table.

    Args:
        conn: psycopg2 connection
        table_name: Target table name
        rows: List of row dicts

    Returns:
        Number of rows inserted
    """
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    cols_sql = ", ".join(f'"{c}"' for c in columns)
    sql = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders});'

    values_batch = []
    for row in rows:
        values_batch.append(tuple(row.get(c) for c in columns))

    with conn.cursor() as cursor:
        cursor.executemany(sql, values_batch)
    conn.commit()

    count = len(values_batch)
    print(f"[+] Inserted {count} rows into '{table_name}'")
    return count


# ─── Schema Introspection ───────────────────────────────────────────────────

def get_table_schema(conn, table_name: str, schema: str = "public") -> List[Dict[str, Any]]:
    """
    Get column info for a table via information_schema.

    Args:
        conn: psycopg2 connection
        table_name: Table to inspect
        schema: Database schema (default: 'public')

    Returns:
        List of dicts: [{'name': 'ticker', 'type': 'text', ...}]
    """
    sql = """
        SELECT ordinal_position, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position;
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (schema, table_name))
        columns_info = []
        for row in cursor.fetchall():
            columns_info.append({
                "ordinal_position": row[0],
                "name": row[1],
                "type": row[2],
                "is_nullable": row[3],
                "default": row[4],
            })
    return columns_info


def get_all_tables(conn, schema: str = "public") -> List[str]:
    """
    Get all table names in the database.

    Args:
        conn: psycopg2 connection
        schema: Database schema (default: 'public')

    Returns:
        List of table name strings
    """
    sql = """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s
        ORDER BY table_name;
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (schema,))
        return [row[0] for row in cursor.fetchall()]


def get_sample_rows(conn, table_name: str, limit: int = 2, schema: str = "public") -> List[Dict[str, Any]]:
    """
    Fetch first N rows from a table as dicts.

    Args:
        conn: psycopg2 connection
        table_name: Table to sample
        limit: Number of rows to fetch (default: 2)
        schema: Database schema (default: 'public')

    Returns:
        List of row dicts
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT %s;', (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_row_count(conn, table_name: str) -> int:
    """Get total row count for a table."""
    with conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}";')
        return cursor.fetchone()[0]
