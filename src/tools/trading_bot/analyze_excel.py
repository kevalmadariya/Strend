"""
Tool: analyze_excel
===================
Analyzes Excel data with stock tickers, fetches historical price data,
and calculates high/low price comparisons, gains and reverse gains.
"""

import json
from datetime import datetime, timedelta
from src.tools.base import DynamicTool, ToolParam
from src.tools.utils.stock_analysis_util import analyze_stock_data


def makeTool(router):
    """Factory function for the Analyze Excel tool."""

    def func(unique_id):

        async def analyze_excel(json_data: str, date: str = None):
            """
            Analyze Excel data containing tickers, fetch stock data, and compute comparisons.
            """
            
            try:
                # Handle table name lookup (needs database connection)
                if isinstance(json_data, str) and not json_data.strip().startswith('{') and not json_data.strip().startswith('['):
                    from src.core.sqlite_manager import get_connection
                    conn = get_connection(unique_id)
                    cursor = conn.execute(f'SELECT * FROM "{json_data}"')
                    db_columns = [description[0] for description in cursor.description]
                    db_rows = [dict(zip(db_columns, row)) for row in cursor.fetchall()]
                    data = {"file": db_rows}
                    json_data = json.dumps(data)
                
                # Use the utility function for analysis
                result = analyze_stock_data(json_data, date)
                
                yield json.dumps(result)
                
            except Exception as e:
                yield json.dumps({
                    "status": "error", 
                    "error": f"Analysis failed: {str(e)}"
                })

        return DynamicTool(
            name="analyze_excel",
            description="Analyze Excel data with stock tickers by fetching historical price data, comparing highs/lows, and calculating gains and reverse gains. Input should be a JSON string with format: {\"file\": [{...}, ...], \"date\": \"YYYY-MM-DD\"}",
            function=analyze_excel,
            parameters=[
                ToolParam(
                    name="json_data",
                    type="string",
                    description="Table name (e.g., 'excel_data') or JSON string of the Excel data. Format: {\"file\": [{...}, ...]}",
                    required=True,
                ),
                ToolParam(
                    name="date",
                    type="string",
                    description="Date for historical analysis in YYYY-MM-DD format. Defaults to current date.",
                    required=False,
                ),
            ],
            endpoint="/analyze-excel",
            router=router,
        )

    return func