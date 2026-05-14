
"""
Tool: store_llm_result
========================
Store LLM-generated per-row analysis results into a lookup table and JOIN
back to the main data table. Used when the LLM needs to classify/tag/score
each row but can't express it as a simple SQL expression.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Store LLM Result tool."""

    def func(unique_id):

        async def store_llm_result(
            result_data: str,
            key_column: str,
            result_column: str,
            result_type: str = "TEXT"
        ):
            """
            Store LLM-generated per-row results into a lookup table and
            JOIN back to the main table.
            """
            from src.utils.database_agent.schema_ops import (
                get_all_tables, get_table_schema, get_row_count
            )
            from src.utils.database_agent.validate_query import validate_query, sanitize_table_name
            from src.core.db import get_db_connection

            try:
                conn = get_db_connection()

                tables = get_all_tables(conn)
                if not tables:
                    conn.close()
                    return json.dumps({"status": "error", "error": "No tables found."})

                main_table = tables[0]

                # Parse the result data
                try:
                    data = json.loads(result_data) if isinstance(result_data, str) else result_data
                except json.JSONDecodeError as e:
                    conn.close()
                    return json.dumps({"status": "error", "error": f"Invalid JSON: {e}"})

                if not isinstance(data, list) or not data:
                    conn.close()
                    return json.dumps({"status": "error", "error": "result_data must be a non-empty JSON array"})

                # Sanitize names
                safe_result_col = sanitize_table_name(result_column)
                lookup_table = f"llm_lookup_{safe_result_col}"

                # Validate key_column exists in main table
                schema = get_table_schema(conn, main_table)
                col_names = [c["name"] for c in schema]
                if key_column not in col_names:
                    conn.close()
                    return json.dumps({
                        "status": "error",
                        "error": f"Key column '{key_column}' not found in table '{main_table}'. Available: {col_names}"
                    })

                # Step 1: Create lookup table
                with conn.cursor() as cursor:
                    try:
                        cursor.execute(f'DROP TABLE IF EXISTS "{lookup_table}";')
                    except Exception:
                        pass

                    cursor.execute(
                        f'CREATE TABLE "{lookup_table}" ('
                        f'"{key_column}" TEXT, '
                        f'"{safe_result_col}" {result_type}'
                        f');'
                    )
                conn.commit()

                # Step 2: Bulk insert lookup data
                insert_sql = f'INSERT INTO "{lookup_table}" ("{key_column}", "{safe_result_col}") VALUES (%s, %s);'
                rows_to_insert = []
                for item in data:
                    key_val = item.get(key_column)
                    result_val = item.get(result_column, item.get(safe_result_col))
                    if key_val is not None:
                        rows_to_insert.append((str(key_val), result_val))

                with conn.cursor() as cursor:
                    cursor.executemany(insert_sql, rows_to_insert)
                conn.commit()

                # Step 3: Add column to main table if not exists
                if safe_result_col not in col_names:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(f'ALTER TABLE "{main_table}" ADD COLUMN "{safe_result_col}" {result_type};')
                        conn.commit()
                    except Exception as e:
                        if "duplicate column" not in str(e).lower():
                            raise

                # Step 4: UPDATE main table via subquery JOIN
                update_sql = (
                    f'UPDATE "{main_table}" SET "{safe_result_col}" = '
                    f'(SELECT L."{safe_result_col}" FROM "{lookup_table}" L '
                    f'WHERE L."{key_column}" = "{main_table}"."{key_column}" LIMIT 1);'
                )

                is_valid, err = validate_query(update_sql)
                if not is_valid:
                    conn.close()
                    return json.dumps({"status": "error", "error": f"Update query blocked: {err}"})

                with conn.cursor() as cursor:
                    cursor.execute(update_sql)
                conn.commit()

                return json.dumps({
                    "status": "success",
                    "data": {
                        "lookup_table": lookup_table,
                        "lookup_rows": len(rows_to_insert),
                        "main_table": main_table,
                        "column_added": safe_result_col,
                    }
                })

            except Exception as e:
                return json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="store_llm_result",
            description=(
                "Store LLM-generated per-row analysis results (classifications, scores, tags) "
                "into a lookup table and JOIN it back to the main data table. "
                "Use this when you need to add per-row analytical data that cannot be expressed as a SQL expression. "
                "Send ONLY unique key-value pairs, not all rows."
            ),
            trigger="Classify rows, tag data, score entries, categorize, label, assign per-row values from LLM analysis",
            function=store_llm_result,
            parameters=[
                ToolParam(
                    name="result_data",
                    type="string",
                    description='JSON array of objects with key-value pairs. e.g., [{"ticker": "RELIANCE", "signal": "bullish"}, ...]',
                    required=True,
                ),
                ToolParam(
                    name="key_column",
                    type="string",
                    description="Column name to JOIN on (must exist in main table)",
                    required=True,
                ),
                ToolParam(
                    name="result_column",
                    type="string",
                    description="Name for the new result column (e.g., 'signal', 'category')",
                    required=True,
                ),
                ToolParam(
                    name="result_type",
                    type="string",
                    description="PostgreSQL type: TEXT, INTEGER, or REAL (default: TEXT)",
                    required=False,
                ),
            ],
            endpoint="/store-llm-result",
            router=router,
        )

    return func
