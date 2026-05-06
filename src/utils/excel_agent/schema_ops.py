"""
Schema Operations
==================
Single Responsibility: Schema inference, DDL (CREATE TABLE), data loading,
and schema introspection on SQLite databases.
Does NOT generate queries from natural language — that's query_builder's job.
"""

import sqlite3
from typing import List, Dict, Any, Optional


# ─── Type Inference ─────────────────────────────────────────────────────────

def _infer_single_type(value: Any) -> str:
    """Infer SQLite type from a single Python value."""
    if value is None:
        return "TEXT"  # Default to TEXT for null
    if isinstance(value, bool):
        return "INTEGER"
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
    Infer SQLite column types from the first N rows.
    
    Priority: REAL > INTEGER > TEXT (if mixed types found, pick the broadest).
    
    Args:
        rows: List of row dicts
        sample_size: Number of rows to inspect (default: 2)
        
    Returns:
        Dict mapping column_name → SQLite type ('TEXT', 'INTEGER', 'REAL')
    """
    if not rows:
        return {}

    sample = rows[:sample_size]
    columns = list(sample[0].keys())
    schema = {}

    type_priority = {"TEXT": 0, "INTEGER": 1, "REAL": 2}

    for col in columns:
        detected_types = set()
        for row in sample:
            val = row.get(col)
            detected_types.add(_infer_single_type(val))

        # If mixed numeric types, prefer REAL; if any TEXT, use TEXT
        if "TEXT" in detected_types and any(
            row.get(col) is not None and str(row.get(col, "")).strip() != ""
            for row in sample
        ):
            # Check if values that look like TEXT are actually non-numeric strings
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

def create_table(conn: sqlite3.Connection, table_name: str, schema: Dict[str, str]) -> None:
    """
    Create a table with the given schema.
    
    Args:
        conn: SQLite connection
        table_name: Name of the table to create
        schema: Dict mapping column_name → SQLite type
        
    Raises:
        ValueError: If schema is empty
    """
    if not schema:
        raise ValueError("Cannot create table with empty schema")

    columns_sql = ", ".join(
        f'"{col}" {col_type}' for col, col_type in schema.items()
    )

    sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns_sql});'
    conn.execute(sql)
    conn.commit()
    print(f"✅ Created table '{table_name}' with {len(schema)} columns")


# ─── Data Loading ────────────────────────────────────────────────────────────

def bulk_insert(conn: sqlite3.Connection, table_name: str, rows: List[Dict[str, Any]]) -> int:
    """
    Batch-insert all rows into the table.
    
    Args:
        conn: SQLite connection
        table_name: Target table name
        rows: List of row dicts
        
    Returns:
        Number of rows inserted
    """
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    cols_sql = ", ".join(f'"{c}"' for c in columns)
    sql = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders});'

    values_batch = []
    for row in rows:
        values_batch.append(tuple(row.get(c) for c in columns))

    conn.executemany(sql, values_batch)
    conn.commit()

    count = len(values_batch)
    print(f"✅ Inserted {count} rows into '{table_name}'")
    return count


# ─── Schema Introspection ───────────────────────────────────────────────────

def get_table_schema(conn: sqlite3.Connection, table_name: str) -> List[Dict[str, Any]]:
    """
    Get column info for a table via PRAGMA table_info.
    
    Args:
        conn: SQLite connection
        table_name: Table to inspect
        
    Returns:
        List of dicts: [{'cid': 0, 'name': 'ticker', 'type': 'TEXT', 'notnull': 0, ...}]
    """
    cursor = conn.execute(f'PRAGMA table_info("{table_name}");')
    columns_info = []
    for row in cursor.fetchall():
        columns_info.append({
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        })
    return columns_info


def get_all_tables(conn: sqlite3.Connection) -> List[str]:
    """
    Get all table names in the database.
    
    Returns:
        List of table name strings
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    return [row[0] for row in cursor.fetchall()]


def get_sample_rows(conn: sqlite3.Connection, table_name: str, limit: int = 2) -> List[Dict[str, Any]]:
    """
    Fetch first N rows from a table as dicts.
    
    Args:
        conn: SQLite connection
        table_name: Table to sample
        limit: Number of rows to fetch (default: 2)
        
    Returns:
        List of row dicts
    """
    cursor = conn.execute(f'SELECT * FROM "{table_name}" LIMIT ?;', (limit,))
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(columns, row)))
    return rows


def get_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Get total row count for a table."""
    cursor = conn.execute(f'SELECT COUNT(*) FROM "{table_name}";')
    return cursor.fetchone()[0]
