
"""
Tool: execute_query
====================
Thin wrapper -- delegates to validate_query + query_executor utils.
Executes a raw SQL query after safety validation on PostgreSQL.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Execute Query tool."""

    def func(unique_id):

        async def execute_query(query: str):
            """
            Validate and execute a raw SQL query on the PostgreSQL database.
            """
            from src.utils.database_agent.validate_query import validate_query
            from src.utils.database_agent.query_executor import execute_auto_query, format_result_as_json
            from src.core.db import get_db_connection

            try:
                # Validate first
                is_valid, err = validate_query(query)
                if not is_valid:
                    return json.dumps({"status": "error", "error": f"Query blocked: {err}"})

                # Execute
                conn = get_db_connection()
                result = execute_auto_query(conn, query)
                conn.close()
                return format_result_as_json(result)

            except Exception as e:
                return json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="execute_query",
            description="Execute a raw SQL query directly on the PostgreSQL database after safety validation",
            trigger="Execute SQL query directly on database, run raw SQL, execute custom query",
            function=execute_query,
            parameters=[
                ToolParam(
                    name="query",
                    type="string",
                    description="Raw SQL query to execute (will be validated for safety before execution)",
                    required=True,
                ),
            ],
            endpoint="/execute-query",
            router=router,
        )

    return func
