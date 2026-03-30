import asyncio
from src.tools.utils.get_yfinance_data import get_yfinance_data
import yfinance as yf
import psycopg2
from ..base import DynamicTool
from ..base import ToolParam
from datetime import date
from typing import Optional

def makeTool(router):
    """
    Factory function for the Yahoo Finance Stock Tool.
    """
    def func(unique_id):
        
        async def scrape_stock_data(ticker: Optional[str] = None, text: Optional[str] = None):
            """
            Fetches live stock data using Yahoo Finance API and stores it in the DB.
            Supports multiple tickers separated by commas or extracted from text.
            """
            import re
            
            all_tickers = set()
            
            # Handle comma-separated list in 'ticker' param
            if ticker:
                for t in ticker.split(","):
                    if t.strip():
                        all_tickers.add(t.strip())
            
            # Extract tickers from text if provided
            if text:
                found_in_text = re.findall(r'\b[A-Z0-9]{3,}\b', text)
                for t in found_in_text:
                    if t not in ["AND", "FOR", "THE", "WITH", "ARE", "NOT", "YES", "CAN", "YOU", "BUT"]:
                        all_tickers.add(t)

            if not all_tickers:
                 return "⚠️ No valid tickers provided. Please specify tickers or mention them in the text."

            print(f"✅ [ID: {unique_id}] Fetching yfinance data for: {all_tickers}")
            
            results = []
            errors = []
            
            for t in all_tickers:
                clean_ticker = t.upper()
                if not clean_ticker.endswith(".NS") and not clean_ticker.endswith(".BO"):
                    clean_ticker += ".NS"
                
                try:
                    # --- STEP A: FETCH DATA ---
                    # Run synchronous yfinance code in a separate thread
                    stock_data = await asyncio.to_thread(get_yfinance_data, clean_ticker)
                    
                    # Immediate check: Did we get data?
                    if stock_data is None:
                        print(f"⚠️ No data found for {clean_ticker}")
                        errors.append(f"{t}: No data found")
                        continue

                    print(f"📊 Data Received for {t}: {stock_data}")
                    results.append(stock_data)

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"❌ Error processing {clean_ticker}: {str(e)}")
                    errors.append(f"{t}: Found Error ({str(e)})")

            # Construct summary
            summary = []
            if results:
                summary.append(f"✅ Successfully fetched {len(results)} stocks: {', '.join([r['ticker'] for r in results])}")
                summary.append(f"Details: {results}")
            
            if errors:
                summary.append(f"❌ Failed to fetch {len(errors)} stocks: {', '.join(errors)}")
            
            if not summary:
                 return "⚠️ No valid tickers provided or all failed."

            return "\n".join(summary)
    
        return DynamicTool(
            name="check_stock_price",
            description="Get live stock market data using Yahoo Finance",
            triggers=["Get stock details", "Fetch stock data"],
            function=scrape_stock_data,
            parameters=[
                ToolParam(name="ticker", type="string", description="Stock Ticker (comma separated)", required=False),
                ToolParam(name="text", type="string", description="Text containing stock tickers", required=False)
            ],
            endpoint="/check-stock",
            router=router
        )

    return func
