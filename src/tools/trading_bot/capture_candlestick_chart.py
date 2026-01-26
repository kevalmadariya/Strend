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

            def log(msg: str):
                print(msg, flush=True)
                return msg

            conn = get_db_connection()
            cur = conn.cursor()

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
                yield log(f"❌ Database Error (Table Creation): {e}\n")
                return

            yield log(f"🚀 Started Chart Capture for {len(tickers)} tickers\n")

            results_summary = []

            for ticker in tickers:
                try:
                    yield log(f"🔄 Processing {ticker}...\n")

                    cur.execute("SELECT stock_id FROM stock WHERE ticker = %s", (ticker,))
                    res = cur.fetchone()

                    if not res:
                        yield log(f"   🆕 Stock {ticker} not found. Fetching info...\n")
                        if not get_yfinance_data(ticker):
                            yield log(f"   ⚠️ Failed to fetch info for {ticker}. Skipping.\n")
                            continue

                        cur.execute("SELECT stock_id FROM stock WHERE ticker = %s", (ticker,))
                        res = cur.fetchone()
                        if not res:
                            yield log(f"   ❌ Insert failed for {ticker}. Skipping.\n")
                            continue

                    stock_id = res[0]

                    cur.execute("""
                        SELECT technical_analysis_id
                        FROM technical_analysis
                        WHERE stock_id = %s AND date = CURRENT_DATE AND chart_image IS NOT NULL
                    """, (stock_id,))
                    if cur.fetchone():
                        yield log(f"   ℹ️ Chart already exists for {ticker}\n")
                        continue

                    yield log(f"   📸 Capturing screenshot...\n")
                    image_bytes = await capture_stock_chart(ticker)

                    cur.execute("""
                        INSERT INTO technical_analysis (stock_id, date, chart_image)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (stock_id, date)
                        DO UPDATE SET chart_image = EXCLUDED.chart_image;
                    """, (stock_id, date.today(), image_bytes))

                    conn.commit()
                    yield log(f"   ✅ Chart stored for {ticker} ({len(image_bytes)} bytes)\n")

                except Exception as e:
                    conn.rollback()
                    yield log(f"   ❌ Error processing {ticker}: {e}\n")

            conn.close()
            yield log("✅ Chart Capture Complete.\n")
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
