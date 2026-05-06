"""
Tool: add_computed_column
==========================
Thin wrapper — delegates to query_builder + validate_query + query_executor utils.
Adds a new column to the table computed from existing columns via a formula.
"""

import json
from src.tools.base import DynamicTool, ToolParam


def makeTool(router):
    """Factory function for the Add Computed Column tool."""

    def func(unique_id):

        async def add_computed_column(column_name: str, formula: str):
            """
            Add a new computed column to the table using an LLM-generated formula.
            e.g., column_name="ROC_change", formula="(col_10 - col_11) / 100"
            """
            from src.utils.excel_agent.schema_ops import get_table_schema, get_all_tables
            from src.utils.excel_agent.query_builder import build_computed_column_sql
            from src.utils.excel_agent.validate_query import validate_query
            from src.utils.excel_agent.query_executor import execute_multi_query
            from src.core.sqlite_manager import get_connection
            from langchain_groq import ChatGroq

            try:
                conn = get_connection(unique_id)

                tables = get_all_tables(conn)
                if not tables:
                    return json.dumps({"status": "error", "error": "No tables found. Upload data first."})

                table_name = tables[0]
                schema = get_table_schema(conn, table_name)

                # Generate ALTER + UPDATE SQL via LLM
                llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)
                sqls = build_computed_column_sql(llm, column_name, formula, schema, table_name)

                print(f"🔧 Computed column SQL: {sqls}")

                # Validate each statement
                for sql in sqls:
                    is_valid, err = validate_query(sql)
                    if not is_valid:
                        return json.dumps({
                            "status": "error",
                            "error": f"Generated SQL blocked: {err}",
                            "generated_sql": sqls,
                        })

                # Execute all statements in transaction
                result = execute_multi_query(conn, sqls)
                result["column_name"] = column_name
                result["formula"] = formula
                return json.dumps(result)

            except Exception as e:
                return json.dumps({"status": "error", "error": str(e)})

        return DynamicTool(
            name="add_computed_column",
            description="Add a new column to the table computed from existing columns using a formula",
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
