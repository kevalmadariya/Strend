
"""
Query Executor
===============
Single Responsibility: Execute validated SQL on a PostgreSQL connection and
format results for WebSocket transport.
Does NOT validate queries — that's validate_query's job.
Does NOT generate queries — that's query_builder's job.
"""

import json
from typing import List, Dict, Any
from psycopg2.extras import RealDictCursor


def execute_read_query(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Execute a SELECT query and return results as list of dicts.

    Args:
        conn: psycopg2 connection
        sql: SQL SELECT statement
        params: Query parameters (for parameterized queries)

    Returns:
        List of row dicts

    Raises:
        psycopg2.Error: On SQL execution failure
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def execute_write_query(conn, sql: str, params: tuple = ()) -> Dict[str, Any]:
    """
    Execute an INSERT/UPDATE/DELETE query and return affected row count.

    Args:
        conn: psycopg2 connection
        sql: SQL write statement
        params: Query parameters

    Returns:
        Dict with 'affected_rows' count and 'status'

    Raises:
        psycopg2.Error: On SQL execution failure
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
    conn.commit()
    return {
        "status": "success",
        "affected_rows": cursor.rowcount,
    }


def execute_multi_query(conn, queries: List[str]) -> Dict[str, Any]:
    """
    Execute multiple statements in a single transaction.

    Used for compound operations like ALTER TABLE + UPDATE (computed columns).

    Args:
        conn: psycopg2 connection
        queries: List of SQL statements to execute sequentially

    Returns:
        Dict with summary of all operations

    Raises:
        psycopg2.Error: Rolls back entire transaction on any failure
    """
    results = []
    try:
        for sql in queries:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                results.append({
                    "sql": sql[:100],  # Truncate for readability
                    "affected_rows": cursor.rowcount,
                })
        conn.commit()
        return {
            "status": "success",
            "operations": len(queries),
            "details": results,
        }
    except Exception as e:
        conn.rollback()
        return {
            "status": "error",
            "error": str(e),
            "rolled_back": True,
        }


def execute_auto_query(conn, sql: str, params: tuple = ()) -> Any:
    """
    Automatically detect query type and execute accordingly.

    - SELECT -> returns list[dict] (rows)
    - INSERT/UPDATE/DELETE -> returns dict with affected_rows
    - ALTER -> returns dict with status

    Args:
        conn: psycopg2 connection
        sql: Any valid SQL statement
        params: Query parameters

    Returns:
        Query results (type depends on statement type)
    """
    upper = sql.strip().upper()

    if upper.startswith("SELECT"):
        return execute_read_query(conn, sql, params)
    else:
        return execute_write_query(conn, sql, params)


def format_result_as_json(result: Any) -> str:
    """
    Convert query result to JSON string for WebSocket transport.

    Handles:
    - list[dict] -> JSON array of objects
    - dict -> JSON object
    - other -> wraps in {"result": value}

    Args:
        result: Query result from any execute_* function

    Returns:
        JSON string
    """
    if isinstance(result, (list, dict)):
        return json.dumps(result, default=str, ensure_ascii=False)
    return json.dumps({"result": result}, default=str, ensure_ascii=False)
