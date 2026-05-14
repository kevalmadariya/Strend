"""
Tool: store_llm_result
========================
NEW TOOL: When the LLM needs to produce per-row analytical data (classifications, 
scores, tags) that CANNOT be expressed as a simple SQL expression, this tool:

1. Takes the LLM's analysis as a JSON array of {key: value, result_col: value}
2. Stores it in a small LOOKUP TABLE (e.g., llm_results_<name>)
3. JOINs the lookup table back to the main data table
4. Adds the result as a new column on the main table via UPDATE...FROM

This way the LLM only sends the UNIQUE values (e.g., 50 tickers, not 1000 rows),
and SQLite handles the JOIN/distribution efficiently.
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
            
            Example: LLM classifies each ticker as 'bullish'/'bearish'.
            Instead of generating 1000 UPDATE statements, it sends:
            [{"ticker": "RELIANCE", "signal": "bullish"}, {"ticker": "TCS", "signal": "bearish"}, ...]
            
            This creates a lookup table and joins it to add the column.
            """
            from src.utils.excel_agent.schema_ops import (
                get_all_tables, get_table_schema, get_row_count
            )
            from src.utils.excel_agent.validate_query import validate_query, sanitize_table_name
            from src.core.sqlite_manager import get_connection

            try:
                conn = get_connection(unique_id)

                tables = get_all_tables(conn)
                if not tables:
                    yield json.dumps({"status": "error", "error": "No tables found. Upload data first."})
                    return

                main_table = tables[0]

                # Parse the result data
                try:
                    data = json.loads(result_data) if isinstance(result_data, str) else result_data
                except json.JSONDecodeError as e:
                    yield json.dumps({"status": "error", "error": f"Invalid JSON: {e}"})
                    return

                if not isinstance(data, list) or not data:
                    yield json.dumps({"status": "error", "error": "result_data must be a non-empty JSON array"})
                    return

                # Sanitize names
                safe_result_col = sanitize_table_name(result_column)
                lookup_table = f"llm_lookup_{safe_result_col}"

                # Validate key_column exists in main table
                schema = get_table_schema(conn, main_table)
                col_names = [c["name"] for c in schema]
                if key_column not in col_names:
                    yield json.dumps({
                        "status": "error",
                        "error": f"Key column '{key_column}' not found in table '{main_table}'. Available: {col_names}"
                    })
                    return

                # Step 1: Create lookup table
                drop_sql = f'DROP TABLE IF EXISTS "{lookup_table}";'
                create_sql = (
                    f'CREATE TABLE "{lookup_table}" ('
                    f'"{key_column}" TEXT, '
                    f'"{safe_result_col}" {result_type}'
                    f');'
                )

                # Drop existing lookup if any (safe — it's our lookup, not user data)
                try:
                    conn.execute(drop_sql)
                except Exception:
                    pass

                conn.execute(create_sql)

                # Step 2: Bulk insert lookup data
                insert_sql = f'INSERT INTO "{lookup_table}" ("{key_column}", "{safe_result_col}") VALUES (?, ?);'
                rows_to_insert = []
                for item in data:
                    key_val = item.get(key_column)
                    result_val = item.get(result_column, item.get(safe_result_col))
                    if key_val is not None:
                        rows_to_insert.append((str(key_val), result_val))

                conn.executemany(insert_sql, rows_to_insert)
                conn.commit()

                print(f"[+] Inserted {len(rows_to_insert)} rows into lookup table '{lookup_table}'")

                # Step 3: Add column to main table if not exists
                if safe_result_col not in col_names:
                    alter_sql = f'ALTER TABLE "{main_table}" ADD COLUMN "{safe_result_col}" {result_type};'
                    try:
                        conn.execute(alter_sql)
                        conn.commit()
                    except Exception as e:
                        # Column might already exist
                        if "duplicate column" not in str(e).lower():
                            raise

                # Step 4: UPDATE main table FROM lookup table via JOIN
                update_sql = (
                    f'UPDATE "{main_table}" SET "{safe_result_col}" = '
                    f'(SELECT L."{safe_result_col}" FROM "{lookup_table}" L '
                    f'WHERE L."{key_column}" = "{main_table}"."{key_column}" LIMIT 1);'
                )

                is_valid, err = validate_query(update_sql)
                if not is_valid:
                    yield json.dumps({"status": "error", "error": f"Update query blocked: {err}", "generated_sql": update_sql})
                    return

                cursor = conn.execute(update_sql)
                conn.commit()

                main_count = get_row_count(conn, main_table)

                yield json.dumps({
                    "status": "success",
                    "data": {
                        "lookup_table": lookup_table,
                        "lookup_rows": len(rows_to_insert),
                        "main_table": main_table,
                        "main_rows_updated": cursor.rowcount,
                        "main_total_rows": main_count,
                        "column_added": safe_result_col,
                        "key_column": key_column,
                    }
                })

            except Exception as e:
                yield json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="store_llm_result",
            description=(
                "Store LLM-generated per-row analysis results (classifications, scores, tags) "
                "into a lookup table and JOIN it back to the main data table. "
                "Use this when you need to add per-row analytical data that cannot be expressed as a SQL expression. "
                "Send ONLY unique key-value pairs, not all rows. "
                "Example: [{\"ticker\": \"RELIANCE\", \"signal\": \"bullish\"}, ...]"
            ),
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
                    description="Column name to JOIN on (must exist in main table, e.g., 'ticker', 'symbol', 'name')",
                    required=True,
                ),
                ToolParam(
                    name="result_column",
                    type="string",
                    description="Name for the new result column (e.g., 'signal', 'category', 'score')",
                    required=True,
                ),
                ToolParam(
                    name="result_type",
                    type="string",
                    description="SQLite type for the result column: TEXT, INTEGER, or REAL (default: TEXT)",
                    required=False,
                ),
            ],
            endpoint="/store-llm-result",
            router=router,
        )

    return func
