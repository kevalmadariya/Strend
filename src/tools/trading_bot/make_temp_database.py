"""
Tool: make_temp_database
=========================
Thin wrapper — delegates ALL logic to utils.
Parses Excel JSON data, infers schema, creates table, and bulk inserts.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Make Temp Database tool."""

    def func(unique_id):

        async def make_temp_database(json_data: str):
            """
            Parse Excel JSON, create table schema, and load all data.
            Returns schema summary.
            """
            from src.utils.excel_agent.excel_parser import parse_excel_json
            from src.utils.excel_agent.schema_ops import (
                infer_column_types, create_table, bulk_insert
            )
            from src.core.sqlite_manager import get_connection

            # Parse the incoming JSON
            try:
                data = json.loads(json_data) if isinstance(json_data, str) else json_data
            except json.JSONDecodeError as e:
                return json.dumps({"status": "error", "error": f"Invalid JSON: {e}"})

            # Delegate to utils
            try:
                columns, rows = parse_excel_json(data)
                schema = infer_column_types(rows[:2])
                conn = get_connection(unique_id)
                create_table(conn, "excel_data", schema)
                count = bulk_insert(conn, "excel_data", rows)

                return json.dumps({
                    "status": "success",
                    "table": "excel_data",
                    "columns": columns,
                    "column_types": schema,
                    "rows_inserted": count,
                })
            except Exception as e:
                return json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="make_temp_database",
            description="Load Excel/CSV JSON data into a temporary SQLite database table",
            function=make_temp_database,
            parameters=[
                ToolParam(
                    name="json_data",
                    type="string",
                    description="JSON string of the Excel data. Format: {\"file\": [{...}, ...]}",
                    required=True,
                ),
            ],
            endpoint="/make-temp-database",
            router=router,
        )

    return func
