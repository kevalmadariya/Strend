import json
from typing import List, Optional
from datetime import date
from src.core.db import get_db_connection
from ..base import DynamicTool, ToolParam
from src.tools.utils.chartink_scraper import fetch_chartink_data

# URL Mapping for Technical Analysis Methods
URL_MAPPING = {
    "MACD_Bullish": "https://chartink.com/screener/macd-bullish-crossover",
    "MACD_Bullish_RSI": "https://chartink.com/screener/rsi-crossed-above-60-macd-cross-over-macd-signal",
    "MACD_Bullish_ADX": "https://chartink.com/screener/macd-bullish-crossover-with-adx-25-adx-di-adx-di",
    "RSI_70_Above": "https://chartink.com/screener/rsi-above-70-2"
}

def makeTool(router):
    
    def func(unique_id):
        
        async def extract_stocks(method: str, query: str = None, total_pages: int = 3):
            """
            Extracts stocks using Chartink screener based on the method and stores them in the database.
            Yields data for frontend display to avoid context bloat.
            """
            
            # --- 1. Prepare Method Name ---
            db_method_name = method
            if query:
                cleaned_query = query.replace(" ", "_")[:50] 
                db_method_name = f"{method}_{cleaned_query}"

            # --- 2. Check Cache (Today's Data) ---
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                # Ensure table exists first
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS techincal_stocks (
                        method TEXT,
                        ticker  TEXT,
                        date DATE default CURRENT_DATE,
                        stock_name TEXT,
                        volume FLOAT,
                        price FLOAT,
                        percent_change FLOAT,
                        unique (method, ticker, date)
                    );
                """)
                
                cur.execute(
                    "SELECT ticker, stock_name, price, percent_change, volume FROM techincal_stocks WHERE method = %s AND date = CURRENT_DATE",
                    (db_method_name,)
                )
                existing_rows = cur.fetchall()
                
                if existing_rows:
                    print(f"ℹ️ Data for '{db_method_name}' already exists for today. Yielding cached data.")
                    result_list = []
                    for row in existing_rows:
                        result_list.append({
                            "ticker": row[0],
                            "stock_name": row[1],
                            "price": row[2],
                            "percent_change": row[3],
                            "volume": row[4]
                        })
                    # Yield the actual data as JSON string for the frontend
                    yield "Data found\n"
                    yield json.dumps({"status": "success", "data":result_list})
                    
                    # yield json.dumps(result_list, default=str)
                    conn.close()
                    return # Stop execution after yielding cache
                    
            except Exception as e:
                yield f"⚠️ Error checking existing data: {e}"
                # Don't return here, attempt to scrape if DB check just failed on read? 
                # Better safe to continue or stop? If DB is broken, scraping won't store. 
                # Let's clean up and try to proceed to scraping, but connection might be bad.
                print(f"DB Error: {e}")
            finally:
                conn.close()

            # --- 3. Validate URL ---
            url = URL_MAPPING.get(method)
            if not url:
                valid_methods = ", ".join(URL_MAPPING.keys())
                yield f"Error: Method '{method}' not found. Available methods: {valid_methods}"
                return

            yield f"Started scraping for method: {method}"
            
            # --- 4. Scrape Data ---
            try:
                # Fetch data
                headers, rows = await fetch_chartink_data(
                    url=url, 
                    query_text=query, 
                    total_pages=total_pages
                )
            except Exception as e:
                yield f"Error during scraping: {str(e)}"
                return
            
            if not rows:
                yield "No data extracted from the source."
                return
            
            # --- 5. Process & Insert Data ---
            conn = get_db_connection()
            cur = conn.cursor()
            
            fresh_data_list = []

            try:
                inserted_count = 0
                
                # Column Indexing
                idx_name = 1
                idx_symbol = 2
                idx_chg = 4
                idx_price = 5
                idx_vol = 6
                
                if headers:
                    h_lower = [h.lower().strip() for h in headers]
                    def find_idx(keywords):
                        for kw in keywords:
                            for i, h in enumerate(h_lower):
                                if kw in h: return i
                        return -1
                    
                    i_sym = find_idx(["symbol"])
                    if i_sym != -1: idx_symbol = i_sym
                    i_name = find_idx(["stock name", "name"])
                    if i_name != -1: idx_name = i_name
                    i_price = find_idx(["price", "close"])
                    if i_price != -1: idx_price = i_price
                    i_vol = find_idx(["volume"])
                    if i_vol != -1: idx_vol = i_vol
                    i_chg = find_idx(["% chg", "change", "chg"])
                    if i_chg != -1: idx_chg = i_chg

                for row in rows:
                    try:
                        max_idx = max(idx_symbol, idx_name, idx_price, idx_vol, idx_chg)
                        if len(row) <= max_idx:
                            continue

                        stock_name = row[idx_name]
                        ticker = row[idx_symbol]
                        
                        raw_chg = row[idx_chg].replace('%', '').replace(',', '').strip()
                        raw_price = row[idx_price].replace(',', '').strip()
                        raw_vol = row[idx_vol].replace(',', '').replace('"', '').strip()

                        def to_float(val):
                            try:
                                return float(val)
                            except ValueError:
                                return 0.0

                        percent_change = to_float(raw_chg)
                        price = to_float(raw_price)
                        volume = to_float(raw_vol)

                        # Store in list for memory return
                        fresh_data_list.append({
                            "ticker": ticker,
                            "stock_name": stock_name,
                            "price": price,
                            "percent_change": percent_change,
                            "volume": volume
                        })

                        # Upsert Data
                        cur.execute("""
                            INSERT INTO techincal_stocks (method, ticker, stock_name, volume, price, percent_change)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (method, ticker, date) DO UPDATE SET
                                stock_name = EXCLUDED.stock_name,
                                volume = EXCLUDED.volume,
                                price = EXCLUDED.price,
                                percent_change = EXCLUDED.percent_change;
                        """, (db_method_name, ticker, stock_name, volume, price, percent_change))
                        
                        inserted_count += 1
                        
                    except Exception as row_err:
                        # Log error but don't stop the whole process
                        print(f"Skipping row error: {row_err}")

                conn.commit()
                
                # yield status
                yield f"Success: Extracted and stored {inserted_count} stocks."
                
                # yield data for frontend
                yield json.dumps(fresh_data_list, default=str)
                
            except Exception as db_err:
                conn.rollback()
                yield f"Database Error during insertion: {str(db_err)}"
            finally:
                conn.close()

        return DynamicTool(
            name="extract_stocks_by_techincal_analysis",
            description="Extracts stocks by technical analysis. Yields JSON list of stocks.",
            triggers=["Extract technical stocks", "Run chartink scan"],
            function=extract_stocks,
            parameters=[
                ToolParam(name="method", type="string", required=True, description=f"Method: {list(URL_MAPPING.keys())}"),
                ToolParam(name="query", type="string", required=False, description="Custom query"),
                ToolParam(name="total_pages", type="integer", required=False, description="Pages (default: 3)")
            ],
            endpoint="/extract-stocks-technical",
            router=router
        )

    return func