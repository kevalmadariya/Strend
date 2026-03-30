import asyncio
import psycopg2
from datetime import date
from ..base import DynamicTool
from ..base import ToolParam
from src.tools.utils.news_scraper import scrape_news_from_groww
import re
from typing import Optional

def makeTool(router):
    """
    Factory function for the News Analysis Tool.
    """
    def func(unique_id):

        # --- Helper for DB Connection ---
        def get_db_connection():
            try:
                # Prioritize user's configured port (5433)
                return psycopg2.connect(
                    host="127.0.0.1",
                    port=5433,
                    user="postgres",
                    password="12345"
                )
            except Exception as e:
                print(f"⚠️ Connection to 5433 failed, trying 5434 (Docker)... ({e})")
                return psycopg2.connect(
                    host="127.0.0.1",
                    port=5434,
                    user="postgres",
                    password="StrongPassword_2024!"
                )

        def parse_ago(time_str):
            """Parses '1h ago', '23m ago', '1d ago' into minutes."""
            s = time_str.lower().strip()
            val = 0
            match = re.search(r'(\d+)', s)
            if match:
                val = int(match.group(1))
            
            if 'h' in s:
                val *= 60
            elif 'd' in s:
                val *= 1440
            # 'm' is default (minutes)
            return val

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
            yield f"Test: {unique_id}"
            
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

            yield f"🗞️ [ID: {unique_id}] Processing news for {len(all_tickers)} tickers: {all_tickers}"
            
            conn = None
            try:
                yield "🔄 [DB] Connecting to database..."
                conn = get_db_connection()
                cur = conn.cursor()

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
                            yield f"✅ [DB] Found {len(existing_news)} cached news items for {clean_ticker}."
                            results = []
                            for item in existing_news:
                                results.append({
                                    "ago_minutes": item[0],
                                    "news": item[1],
                                    "url": item[2],
                                    "date": str(item[3])
                                })
                            yield str(results)
                            continue

                        # 2. Scrape if not found
                        yield f"🔄 [Scraper] No cache found for {clean_ticker}. Scraping Groww..."
                        scraped_data = await scrape_news_from_groww(clean_ticker)
                        
                        if not scraped_data:
                            yield f"❌ No news found for {clean_ticker}."
                            continue

                        # 3. Store Results
                        yield f"💾 [DB] Saving {len(scraped_data)} items for {clean_ticker}..."
                        
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
                        yield f"✅ [DB] Successfully saved {saved_count} items for {clean_ticker}."
                        yield str(scraped_data)

                    except Exception as e_inner:
                        yield f"❌ Error processing {clean_ticker}: {str(e_inner)}"

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
            description="Get latest market news for a list of stocks from Groww",
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
