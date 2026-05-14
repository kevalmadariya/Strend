"""
Tool: execute_query
====================
Thin wrapper — delegates to validate_query + query_executor utils.
Executes a raw SQL query after safety validation.
"""

import json
from ..base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Execute Query tool."""

    def func(unique_id):

        async def execute_query(query: str):
            """
            Validate and execute a raw SQL query on the temp database.
            """
            from src.utils.excel_agent.validate_query import validate_query
            from src.utils.excel_agent.query_executor import execute_auto_query, format_result_as_json
            from src.core.sqlite_manager import get_connection

            try:
                # Validate first
                is_valid, err = validate_query(query)
                if not is_valid:
                    yield json.dumps({"status": "error", "error": f"Query blocked: {err}"})
                    return

                # Execute
                conn = get_connection(unique_id)
                result = execute_auto_query(conn, query)
                yield json.dumps({
                    "status" : "success",
                    "data" : result
                })

            except Exception as e:
                yield json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="execute_query",
            description="Execute a raw SQL query directly on the database after safety validation",
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
