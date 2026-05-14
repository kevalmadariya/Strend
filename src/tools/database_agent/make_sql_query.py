
"""
Tool: make_sql_query
=====================
Thin wrapper -- delegates ALL logic to utils.
Takes a natural language query, generates SQL via LLM, validates, executes, returns JSON.
This is the PRIMARY workhorse tool for the Database Agent.

KEY DESIGN: The LLM generates SHORT SQL queries (SELECT, aggregation, filtering).
It NEVER generates per-row UPDATE statements.
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
            from src.utils.database_agent.schema_ops import get_table_schema, get_sample_rows, get_all_tables
            from src.utils.database_agent.query_builder import build_sql_from_query
            from src.utils.database_agent.validate_query import validate_query
            from src.utils.database_agent.query_executor import execute_auto_query, format_result_as_json
            from src.core.db import get_db_connection
            from langchain_groq import ChatGroq

            try:
                conn = get_db_connection()

                # Get all tables to provide context
                tables = get_all_tables(conn)
                if not tables:
                    conn.close()
                    return json.dumps({"status": "error", "error": "No tables found in database."})

                # Default to first table
                table_name = tables[0]
                schema = get_table_schema(conn, table_name)
                samples = get_sample_rows(conn, table_name, limit=3)

                # Build SQL via LLM (LLM injected here -- Dependency Inversion)
                llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)
                sql = build_sql_from_query(llm, user_query, schema, samples, table_name)

                print(f"[+] Generated SQL: {sql}")

                # Validate
                is_valid, err = validate_query(sql)
                if not is_valid:
                    conn.close()
                    return json.dumps({"status": "error", "error": f"Unsafe query blocked: {err}", "generated_sql": sql})

                # Execute
                result = execute_auto_query(conn, sql)
                conn.close()
                return format_result_as_json(result)

            except Exception as e:
                return json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="make_sql_query",
            description="Generate and execute a SHORT SQL query from a natural language question about the database data. For adding computed columns, use add_computed_column instead. For storing LLM analysis results, use store_llm_result instead.",
            trigger="Query data, filter records, search rows, find data, sort data, aggregate, calculate, compare, analyze database",
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
