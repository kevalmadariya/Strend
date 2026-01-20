import asyncio
from src.tools.utils.get_yfinance_data import get_yfinance_data
import yfinance as yf
import psycopg2
from ..base import DynamicTool
from ..base import ToolParam
from datetime import date

def makeTool(router):
    """
    Factory function for the Yahoo Finance Stock Tool.
    """
    def func(unique_id):
        
        async def scrape_stock_data(ticker: str):
            """
            Fetches live stock data using Yahoo Finance API and stores it in the DB.
            """
            print(f"✅ [ID: {unique_id}] Fetching yfinance data for: {ticker}")
            
            # 1. Clean Ticker
            clean_ticker = ticker.upper().strip()
            if not clean_ticker.endswith(".NS") and not clean_ticker.endswith(".BO"):
                clean_ticker += ".NS"
            
            stock_data = None

            try:
                # --- STEP A: FETCH DATA ---
                # Run synchronous yfinance code in a separate thread
                stock_data = await asyncio.to_thread(get_yfinance_data, clean_ticker)
                
                # Immediate check: Did we get data?
                if stock_data is None:
                    print(f"⚠️ No data found for {clean_ticker}")
                    return f"❌ Could not retrieve data for {clean_ticker}. Check if the ticker is correct."

                print(f"📊 Data Received: {stock_data}")
                return stock_data

            except Exception as e:
                # This catches both YFinance errors AND Database errors
                import traceback
                traceback.print_exc() # Print full error trace to console
                return f"❌ Error processing {clean_ticker}: {str(e)}"

        return DynamicTool(
            name="check_stock_price",
            description="Get live stock market data using Yahoo Finance",
            triggers=["Get stock details", "Fetch stock data"],
            function=scrape_stock_data,
            parameters=[
                ToolParam(name="ticker", type="string", description="Stock Ticker", required=True)
            ],
            endpoint="/check-stock",
            router=router
        )

    return func
