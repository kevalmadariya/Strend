"""
Tool: make_sql_query
=====================
Thin wrapper — delegates ALL logic to utils.
Takes a natural language query, generates SQL via LLM, validates, executes, returns JSON.
This is the PRIMARY workhorse tool for the Excel Agent.
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
            from langchain_groq import ChatGroq

            try:
                conn = get_connection(unique_id)

                # Get all tables to provide context
                tables = get_all_tables(conn)
                if not tables:
                    return json.dumps({"status": "error", "error": "No tables found in database. Upload data first."})

                # Default to first table
                table_name = tables[0]
                schema = get_table_schema(conn, table_name)
                samples = get_sample_rows(conn, table_name)

                # Build SQL via LLM (LLM injected here — Dependency Inversion)
                llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)
                sql = build_sql_from_query(llm, user_query, schema, samples, table_name)

                print(f"🔍 Generated SQL: {sql}")

                # Validate
                is_valid, err = validate_query(sql)
                if not is_valid:
                    return json.dumps({"status": "error", "error": f"Unsafe query blocked: {err}", "generated_sql": sql})

                # Execute
                result = execute_auto_query(conn, sql)
                return format_result_as_json(result)

            except Exception as e:
                return json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="make_sql_query",
            description="Generate and execute SQL query from a natural language question about the data",
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
