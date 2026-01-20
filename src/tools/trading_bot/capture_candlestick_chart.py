import json
from typing import List, Optional
from datetime import date
from dateutil.relativedelta import relativedelta
# We need to handle bytea data, usually psycopg2 handles it with memoryview or bytes
import base64

from src.core.db import get_db_connection
from src.tools.utils.get_yfinance_data import get_yfinance_data
from src.tools.utils.chart_capture import capture_stock_chart
from ..base import DynamicTool, ToolParam

def makeTool(router):
    
    def func(unique_id):
        
        async def capture_candlestick_chart(tickers: List[str]):
            """
            Captures candlestick charts for given tickers and stores the image (BYTEA) in the DB.
            """
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # --- 1. Ensure Table Exists (with chart_image) ---
            try:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS technical_analysis (
                        technical_analysis_id SERIAL PRIMARY KEY,
                        stock_id INT REFERENCES stock(stock_id),
                        date DATE default CURRENT_DATE,
                        trend TEXT,
                        chart_pattern TEXT,
                        macd_12_26_9_macd FLOAT,
                        macd_12_26_9_signal FLOAT,
                        macd_12_26_9_histogram FLOAT,
                        rsi_14 FLOAT,
                        adx_14 FLOAT,
                        chart_image BYTEA,
                        unique (stock_id, date)
                    );
                """)
                conn.commit()
            except Exception as e:
                conn.rollback()
                yield f"❌ Database Error (Table Creation): {e}\n"
                return

            yield f"🚀 Started Chart Capture for {len(tickers)} tickers\n"

            results_summary = []
            
            for ticker in tickers:
                try:
                    yield f"🔄 Processing {ticker}...\n"
                    
                    # --- 2. Check/Add Stock in DB ---
                    cur.execute("SELECT stock_id FROM stock WHERE ticker = %s", (ticker,))
                    res = cur.fetchone()
                    
                    stock_id = None
                    if res:
                        stock_id = res[0]
                    else:
                        yield f"   🆕 Stock {ticker} not found in DB. Fetching info...\n"
                        stock_info_res = get_yfinance_data(ticker)
                        if not stock_info_res:
                             yield f"   ⚠️ Could not fetch info for {ticker}. Skipping.\n"
                             continue
                             
                        cur.execute("SELECT stock_id FROM stock WHERE ticker = %s", (ticker,))
                        res_retry = cur.fetchone()
                        if res_retry:
                            stock_id = res_retry[0]
                        else:
                             yield f"   ❌ Failed to insert {ticker} into stock table. Skipping.\n"
                             continue

                    # --- 3. Check for Existing Image ---
                    cur.execute(
                        """
                        SELECT technical_analysis_id
                        FROM technical_analysis 
                        WHERE stock_id = %s AND date = CURRENT_DATE AND chart_image IS NOT NULL
                        """,
                        (stock_id,)
                    )
                    existing_row = cur.fetchone()
                    
                    if existing_row:
                        yield f"   ℹ️ Chart image already exists for {ticker} (ID: {existing_row[0]}).\n"
                        # For now, we don't return the huge base64 string in summary to keep context small,
                        # but we confirm it's there.
                        results_summary.append({
                            "ticker": ticker,
                            "status": "cached",
                            "message": "Image available in DB"
                        })
                        continue

                    # --- 4. Capture Image ---
                    yield f"   📸 Capturing new screenshot...\n"
                    image_bytes = await capture_stock_chart(ticker)
                    
                    # --- 5. Insert/Update into DB ---
                    # Upsert: we might update an existing row (computed technicals earlier) or insert new
                    cur.execute("""
                        INSERT INTO technical_analysis (
                            stock_id, date, chart_image
                        ) VALUES (%s, %s, %s)
                        ON CONFLICT (stock_id, date) DO UPDATE SET
                            chart_image = EXCLUDED.chart_image;
                    """, (
                        stock_id, date.today(), 
                        image_bytes
                    ))
                    conn.commit()
                    
                    yield f"   ✅ Chart stored for {ticker} ({len(image_bytes)} bytes).\n"
                    results_summary.append({
                        "ticker": ticker,
                        "status": "captured",
                        "size": len(image_bytes)
                    })

                except Exception as loop_err:
                    conn.rollback()
                    yield f"   ❌ Error processing {ticker}: {loop_err}\n"

            conn.close()
            yield "\n✅ Chart Capture Complete.\n"
            yield json.dumps({"status": "success", "data": results_summary})


        return DynamicTool(
            name="capture_candlestick_chart",
            description="Captures candlestick chart screenshots and stores them in DB.",
            triggers=["Capture chart", "Get candlestick chart", "Screenshot stock"],
            function=capture_candlestick_chart,
            parameters=[
                ToolParam(name="tickers", type="list", required=True, description="List of stock tickers")
            ],
            endpoint="/capture-chart",
            router=router
        )

    return func
