import json
from typing import List
from src.core.db import get_db_connection
from datetime import date

from src.tools.utils.get_yfinance_data import get_yfinance_data
from ..base import DynamicTool, ToolParam

# Import your existing WebScraping logic
from src.tools.utils.webscraper import WebScaping 
from src.tools.utils.fetch_and_store_fundametals import fetch_and_store_fundamentals

def makeTool(router):

    def func(unique_id):

        async def get_fundamentals(tickers: List[str]):

            conn = get_db_connection()
            cur = conn.cursor()

            #for each stock check latest stock_id
            #for each latest stock_id and if date is within one month and fundametal_analysis exists skip
            tickers_to_fetch = []
            for ticker in tickers:
                cur.execute(
                    """
                    SELECT s.stock_id, fa.date
                    FROM stock s
                    LEFT JOIN fundamental_analysis fa ON s.stock_id = fa.stock_id
                    WHERE s.ticker = %s
                    ORDER BY fa.date DESC
                    LIMIT 1
                    """,
                    (ticker,)
                )
                row = cur.fetchone()
                if row:
                    stock_id, last_fa_date = row
                    if last_fa_date:
                        days_diff = (date.today() - last_fa_date).days
                        if days_diff <= 30:
                            print(f"ℹ️ Skipping {ticker}, recent fundamentals exist.")
                            continue
                tickers_to_fetch.append(ticker)


            return await fetch_and_store_fundamentals(
                tickers=tickers_to_fetch,
                unique_id=unique_id
            )

        return DynamicTool(
            name="get_fundamentals",
            description="Fetch fundamental analysis for tickers",
            triggers=["Get fundamental analysis", "Fetch stock fundamentals"],
            function=get_fundamentals,
            parameters=[
                ToolParam(name="tickers", type="list", required=True, description="List of stock tickers")
            ],
            endpoint="/get-fundamentals",
            router=router
        )

    return func
