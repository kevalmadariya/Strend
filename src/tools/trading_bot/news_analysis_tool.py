import asyncio
import psycopg2
from datetime import date
from ..base import DynamicTool
from ..base import ToolParam
from src.tools.utils.news_scraper import scrape_news_from_groww
import re
from typing import Optional
from src.core.db import get_db_connection
import json

def makeTool(router):
    """
    Factory function for the News Analysis Tool.
    """
    def func(unique_id):

        # --- Helper for DB Connection ---
        # def get_db_connection():
        #     import os
        #     from dotenv import load_dotenv
        #     load_dotenv()
            
        #     try:
        #         return psycopg2.connect(
        #             host=os.getenv("DB_HOST", "127.0.0.1"),
        #             port=os.getenv("DB_PORT", "5433"),
        #             user=os.getenv("DB_USER", "postgres"),
        #             password=os.getenv("DB_PASSWORD", "12345")
        #         )
        #     except Exception as e:
        #         # Fallback purely as per previous logic, but ideally everything should be in .env
        #         print(f"⚠️ Primary DB connection failed: {e}")
        #         raise e

        def parse_ago(time_str):
            """Parses '1h ago', '23m ago', '1d ago', '2w ago' into minutes."""
            s = time_str.lower().strip()
            val = 0
            
            if 'a day' in s:
                return 1440
            
            match = re.search(r'(\d+)', s)
            if match:
                val = int(match.group(1))
            
            # Logic for time units
            if 'w' in s:            # Weeks
                val *= 10080
            elif 'd' in s:          # Days
                val *= 1440
            elif 'h' in s:          # Hours
                val *= 60
            elif 'months' in s:
                val *= 43200
            elif 'years' in s:
                val *= 525600
            # 'm' is default (minutes)
            
            return val
        
        def re_parse_ago(num:int):
            if num < 60:
                return f"{num} min ago"
            elif num < 1440:
                return f"{num // 60} hour ago"
            elif num < 10080:
                return f"{num // 1440} day ago"
            elif num < 525600:
                return f"{num // 10080} week ago"
            else:
                return f"{num // 525600} year ago"
        
        def get_or_create_stock_id(cur, ticker):
            """
            Checks if stock exists for today. If not, creates a minimal entry.
            Returns stock_id.
            """
            cur.execute("SELECT stock_id FROM stock WHERE ticker = %s AND date = %s", (ticker, date.today()))
            res = cur.fetchone()
            if res:
                return res[0]
            
            print(f"🆕 [DB] Stock {ticker} not found for today. Creating placeholder...")
            cur.execute("""
                INSERT INTO stock (ticker, date, name) 
                VALUES (%s, %s, %s) 
                RETURNING stock_id
            """, (ticker, date.today(), ticker))
            return cur.fetchone()[0]

        async def analyze_news(tickers: Optional[list[str]] = None, text: Optional[str] = None):
            """
            Checks DB for news for multiple tickers. Yields updates and results.
            """
            
            all_tickers = set()

            # Ensure tickers is a list (handling single string case if LLM messes up)
            if tickers:
                if isinstance(tickers, str):
                    if "," in tickers:
                        ts = [t.strip() for t in tickers.split(',')]
                        all_tickers.update(ts)
                    else:
                        all_tickers.add(tickers)
                else:
                    all_tickers.update(tickers)
            
            # Extract tickers from text if provided
            if text:
                found_in_text = re.findall(r'\b[A-Z0-9]{3,}\b', text)
                for t in found_in_text:
                     if t not in ["AND", "FOR", "THE", "WITH", "ARE", "NOT", "YES", "CAN", "YOU", "BUT"]:
                        all_tickers.add(t)

            if not all_tickers:
                 yield "⚠️ No tickers provided. Please specify tickers in the list or mention them in the text."
                 return

            yield f"🗞️ Processing news for {len(all_tickers)} tickers: {all_tickers}\n"
            
            conn = None
            try:
                yield "🔄 [DB] Connecting to database..."
                conn = get_db_connection()
                cur = conn.cursor()
                results = []
                for ticker in all_tickers:
                    clean_ticker = ticker.upper().strip()
                    if "." in clean_ticker:
                        clean_ticker = clean_ticker.split(".")[0]
                    
                    yield f"\n--- 🔍 Analyzing: {clean_ticker} ---"

                    try:
                        # 1. Check DB
                        cur.execute("SELECT stock_id FROM stock WHERE ticker = %s AND date = %s", (clean_ticker, date.today()))
                        stock_res = cur.fetchone()
                        
                        existing_news = []
                        if stock_res:
                            stock_id = stock_res[0]
                            cur.execute("""
                                SELECT ago, news, url, date FROM news_analysis 
                                WHERE stock_id = %s AND date = %s
                                ORDER BY ago ASC
                            """, (stock_id, date.today()))
                            existing_news = cur.fetchall()

                        if existing_news:
                            yield f"{re_parse_ago(existing_news[0][0])} min ago : {existing_news[0][1]} \n"
                            for item in existing_news:
                                results.append({
                                    "ticker": clean_ticker,
                                    "ago_minutes": re_parse_ago(item[0]),
                                    "news": item[1],
                                    "url": item[2],
                                    "date": str(item[3])
                                })
                            
                            continue

                        # 2. Scrape if not found
                        yield f"🔄 [Scraper] No cache found for {clean_ticker}\n"
                        scraped_data = await scrape_news_from_groww(clean_ticker)
                        
                        if not scraped_data:
                            yield f"❌ No news found for {clean_ticker}.\n"
                            continue

                        
                        stock_id = get_or_create_stock_id(cur, clean_ticker)
                        
                        saved_count = 0
                        for item in scraped_data:
                            ago_val = parse_ago(item['time_str'])
                            try:
                                cur.execute("""
                                    INSERT INTO news_analysis (stock_id, date, ago, news, url)
                                    VALUES (%s, %s, %s, %s, %s)
                                    ON CONFLICT (stock_id, date, ago) DO NOTHING
                                """, (stock_id, date.today(), ago_val, item['news'], item['url']))
                                saved_count += 1
                            except Exception as e:
                                print(f"⚠️ [DB] Insert Error: {e}")
                        
                        conn.commit()
                        
                        # Standardize scraped data to match results format
                        for item in scraped_data:
                            results.append({
                                "ticker": clean_ticker,
                                "ago_minutes": item['time_str'],
                                "news": item['news'],
                                "url": item['url'],
                                "date": str(date.today())
                            })

                    except Exception as e_inner:
                        yield f"❌ Error processing {clean_ticker}: {str(e_inner)}"
                
                yield "\n\n"
                
                yield json.dumps({
                    "status": "success",
                    "data": results
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                if conn:
                    conn.rollback()
                yield f"❌ Critical Error: {str(e)}"
            finally:
                if conn:
                    conn.close()

        return DynamicTool(
            name="news_analysis_tool",
            description="Get latest market news for a list of stocks,related to stocks only",
            triggers=["Get news", "Check stock news", "Analyze news"],
            function=analyze_news,
            parameters=[
                ToolParam(
                    name="tickers",
                    type="array",
                    description="List of Stock Tickers (e.g. ['RELIANCE', 'TCS'])",
                    required=False,
                    items={"type": "string"}
                ),
                ToolParam(name="text", type="string", description="Text containing stock tickers", required=False)
            ],
            endpoint="/news-analysis",
            router=router
        )

    return func
