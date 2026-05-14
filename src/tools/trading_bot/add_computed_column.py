"""
Tool: add_computed_column
==========================
Thin wrapper — delegates to query_builder + validate_query + query_executor utils.
Adds a new column to the table computed from existing columns via a SQL expression.

KEY DESIGN: The LLM only generates a SQL EXPRESSION (e.g., "CASE WHEN x > 0 THEN 1 ELSE 0 END").
SQLite then applies this expression to ALL rows in a single UPDATE statement.
This avoids the LLM generating per-row UPDATE statements which is slow and error-prone.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Add Computed Column tool."""

    def func(unique_id):

        async def add_computed_column(column_name: str, formula: str):
            """
            Add a new computed column to the table using an LLM-generated SQL expression.
            The LLM generates ONLY the expression, not per-row data.
            e.g., column_name="ROC_change", formula="(col_10 - col_11) / 100"
            """
            from src.utils.excel_agent.schema_ops import (
                get_table_schema, get_all_tables, get_sample_rows
            )
            from src.utils.excel_agent.query_builder import build_computed_column_expression
            from src.utils.excel_agent.validate_query import validate_query
            from src.utils.excel_agent.query_executor import execute_multi_query
            from src.core.sqlite_manager import get_connection

            try:
                conn = get_connection(unique_id)

                tables = get_all_tables(conn)
                if not tables:
                    yield json.dumps({"status": "error", "error": "No tables found. Upload data first."})
                    return

                table_name = tables[0]
                schema = get_table_schema(conn, table_name)
                samples = get_sample_rows(conn, table_name, limit=3)

                # Get LLM to generate only the expression (use ChatNVIDIA with fallback to ChatGroq)
                import os
                api_key = os.getenv("NVIDIA_API_KEY") or "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"
                try:
                    from langchain_nvidia_ai_endpoints import ChatNVIDIA
                    llm = ChatNVIDIA(
                        model="meta/llama-3.3-70b-instruct",
                        api_key=api_key,
                        temperature=0,
                        max_tokens=512,  # Expression only — much smaller
                    )
                except Exception:
                    from langchain_groq import ChatGroq
                    llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)

                # LLM returns ONLY {expression, col_type} — no per-row data
                result = build_computed_column_expression(
                    llm, column_name, formula, schema, samples, table_name
                )

                expression = result["expression"]
                col_type = result.get("col_type", "REAL")

                # Build the two SQL statements from the expression
                alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {col_type};'
                update_sql = f'UPDATE "{table_name}" SET "{column_name}" = {expression};'

                sqls = [alter_sql, update_sql]
                print(f"[+] Computed column SQL: {sqls}")

                # Validate each statement
                for sql in sqls:
                    is_valid, err = validate_query(sql)
                    if not is_valid:
                        yield json.dumps({
                            "status": "error",
                            "error": f"Generated SQL blocked: {err}",
                            "generated_sql": sqls,
                        })
                        return

                # Execute all statements in transaction
                exec_result = execute_multi_query(conn, sqls)
                exec_result["column_name"] = column_name
                exec_result["formula"] = formula
                exec_result["expression"] = expression
                yield json.dumps({
                    "status": "success",
                    "data": exec_result
                })

            except Exception as e:
                yield json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="add_computed_column",
            description="Add a new column to the table computed from existing columns using a SQL expression. The LLM generates ONLY the formula expression, not per-row values.",
            function=add_computed_column,
            parameters=[
                ToolParam(
                    name="column_name",
                    type="string",
                    description="Name for the new column (e.g., 'ROC_change', 'is_inc')",
                    required=True,
                ),
                ToolParam(
                    name="formula",
                    type="string",
                    description="Natural language description of the formula (e.g., '(price - cost) / 100' or 'if ROC_change > 0 then 1 else 0')",
                    required=True,
                ),
            ],
            endpoint="/add-computed-column",
            router=router,
        )

    return func
