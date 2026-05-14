"""
Tool: make_sql_query
=====================
Thin wrapper — delegates ALL logic to utils.
Takes a natural language query, generates SQL via LLM, validates, executes, returns JSON.
This is the PRIMARY workhorse tool for the Excel Agent.

KEY DESIGN: The LLM generates SHORT SQL queries (SELECT, aggregation, filtering).
It NEVER generates per-row UPDATE statements. For computed columns, use add_computed_column.
For storing LLM analysis, use store_llm_result.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Make SQL Query tool."""

    def func(unique_id):

        async def make_sql_query(user_query: str):
            """
            Convert natural language query to SQL, validate, execute, and return results.
            """
            from src.utils.excel_agent.schema_ops import get_table_schema, get_sample_rows, get_all_tables
            from src.utils.excel_agent.query_builder import build_sql_from_query
            from src.utils.excel_agent.validate_query import validate_query
            from src.utils.excel_agent.query_executor import execute_auto_query, format_result_as_json
            from src.core.sqlite_manager import get_connection

            try:
                conn = get_connection(unique_id)

                # Get all tables to provide context
                tables = get_all_tables(conn)
                if not tables:
                    yield json.dumps({"status": "error", "error": "No tables found in database. Upload data first."})
                    return

                # Default to first table
                table_name = tables[0]
                schema = get_table_schema(conn, table_name)
                samples = get_sample_rows(conn, table_name, limit=3)

                # Build SQL via LLM (use ChatNVIDIA with fallback to ChatGroq)
                import os
                api_key = os.getenv("NVIDIA_API_KEY") or "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"
                try:
                    from langchain_nvidia_ai_endpoints import ChatNVIDIA
                    llm = ChatNVIDIA(
                        model="meta/llama-3.3-70b-instruct",
                        api_key=api_key,
                        temperature=0,
                        max_tokens=512,  # Short queries only — no per-row data
                    )
                except Exception:
                    from langchain_groq import ChatGroq
                    llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)

                sql = build_sql_from_query(llm, user_query, schema, samples, table_name)

                print(f"[+] Generated SQL: {sql}")

                # Validate
                is_valid, err = validate_query(sql)
                if not is_valid:
                    yield json.dumps({"status": "error", "error": f"Unsafe query blocked: {err}", "generated_sql": sql})
                    return

                # Execute
                result = execute_auto_query(conn, sql)
                yield json.dumps({
                    "status" : "success",
                    "data" : result
                })

            except Exception as e:
                yield json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="make_sql_query",
            description="Generate and execute a SHORT SQL query from a natural language question about the data. For adding computed columns, use add_computed_column instead. For storing LLM analysis results, use store_llm_result instead.",
            function=make_sql_query,
            parameters=[
                ToolParam(
                    name="user_query",
                    type="string",
                    description="Natural language question about the data (e.g., 'show all rows where price > 100')",
                    required=True,
                ),
            ],
            endpoint="/make-sql-query",
            router=router,
        )

    return func
