"""
Tool: get_schema
=================
Thin wrapper — delegates to schema_ops util.
Returns table structure (columns, types) as JSON.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Get Schema tool."""

    def func(unique_id):

        async def get_schema(table_name: str = "excel_data"):
            """
            Get the schema (columns and types) of a table in the temp database.
            """
            from src.utils.excel_agent.schema_ops import (
                get_table_schema, get_all_tables, get_row_count
            )
            from src.core.sqlite_manager import get_connection

            try:
                conn = get_connection(unique_id)

                # If table_name is empty or "all", return all tables
                if not table_name or table_name.lower() == "all":
                    tables = get_all_tables(conn)
                    result = {}
                    for tbl in tables:
                        result[tbl] = {
                            "columns": get_table_schema(conn, tbl),
                            "row_count": get_row_count(conn, tbl),
                        }
                    yield json.dumps({
                        "status": "success",
                        "data": {
                            "tables": result
                        }
                    })
                    return

                # Get schema for specific table
                schema = get_table_schema(conn, table_name)
                row_count = get_row_count(conn, table_name)

                yield json.dumps({
                    "status": "success",
                    "data": {
                        "table": table_name,
                        "columns": schema,
                        "row_count": row_count,
                    }
                })

            except Exception as e:
                yield json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="get_schema",
            description="Get the database schema showing all columns, their types, and row counts",
            function=get_schema,
            parameters=[
                ToolParam(
                    name="table_name",
                    type="string",
                    description="Table name to inspect (default: 'excel_data'). Use 'all' to see all tables.",
                    required=False,
                ),
            ],
            endpoint="/get-schema",
            router=router,
        )

    return func
