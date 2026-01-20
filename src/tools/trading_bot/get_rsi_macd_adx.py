import json
from typing import List, Optional
from datetime import date
from dateutil.relativedelta import relativedelta
from src.core.db import get_db_connection
from src.tools.utils.get_yfinance_data import get_yfinance_data
from src.tools.utils.technical_analysis_utils import calculate_indicators
from ..base import DynamicTool, ToolParam

def makeTool(router):
    
    def func(unique_id):
        
        async def get_rsi_macd_adx(tickers: List[str]):
            """
            Calculates RSI, MACD, and ADX for given tickers and stores them in the technical_analysis table.
            """
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # --- 1. Ensure Table Exists ---
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
                        unique (stock_id, date)
                    );
                """)
                conn.commit()
            except Exception as e:
                conn.rollback()
                yield f"❌ Database Error (Table Creation): {e}\n"
                return

            yield f"🚀 Started RSI/MACD/ADX Analysis for {len(tickers)} tickers\n"

            results_summary = []
            
            end_date = date.today()
            start_date = end_date - relativedelta(months=6)

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

                    # --- 3. Check for Existing Indicators ---
                    cur.execute(
                        """
                        SELECT macd_12_26_9_macd, rsi_14, adx_14 
                        FROM technical_analysis 
                        WHERE stock_id = %s AND date = CURRENT_DATE
                        """,
                        (stock_id,)
                    )
                    existing_ta = cur.fetchone()
                    
                    # Note: We only check if ALL 3 are present (or just the row exists?)
                    # If the row exists but these are NULL (maybe trend was calculated but not indicators?), we should update.
                    # But if they are not null, we skip.
                    if existing_ta and all(x is not None for x in existing_ta):
                        yield f"   ℹ️ Data already exists for {ticker}. Retrieved from DB.\n"
                        results_summary.append({
                            "ticker": ticker,
                            "macd": existing_ta[0],
                            "rsi": existing_ta[1],
                            "adx": existing_ta[2],
                            "source": "cache"
                        })
                        continue

                    # --- 4. Calculate Indicators ---
                    indicators = calculate_indicators(ticker, start_date, end_date)
                    
                    # --- 5. Insert/Update into DB ---
                    # We use upsert to preserve existing trend/patterns if they were calculated separately
                    cur.execute("""
                        INSERT INTO technical_analysis (
                            stock_id, date, 
                            macd_12_26_9_macd, macd_12_26_9_signal, macd_12_26_9_histogram, 
                            rsi_14, adx_14
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (stock_id, date) DO UPDATE SET
                            macd_12_26_9_macd = EXCLUDED.macd_12_26_9_macd,
                            macd_12_26_9_signal = EXCLUDED.macd_12_26_9_signal,
                            macd_12_26_9_histogram = EXCLUDED.macd_12_26_9_histogram,
                            rsi_14 = EXCLUDED.rsi_14,
                            adx_14 = EXCLUDED.adx_14;
                    """, (
                        stock_id, date.today(), 
                        indicators.get("macd"), indicators.get("macd_signal"), indicators.get("macd_hist"),
                        indicators.get("rsi"), indicators.get("adx")
                    ))
                    conn.commit()
                    
                    yield f"   ✅ Indicators stored for {ticker}.\n"
                    results_summary.append({
                        "ticker": ticker,
                        "macd": indicators.get("macd"),
                        "rsi": indicators.get("rsi"),
                        "adx": indicators.get("adx"),
                        "source": "calculated"
                    })

                except Exception as loop_err:
                    conn.rollback()
                    yield f"   ❌ Error processing {ticker}: {loop_err}\n"

            conn.close()
            yield "\n✅ Analysis Complete.\n"
            yield json.dumps({"status": "success", "data": results_summary})


        return DynamicTool(
            name="get_rsi_macd_adx",
            description="Calculates RSI, MACD, and ADX indicators for stocks.",
            triggers=["Get RSI MACD ADX", "Calculate indicators"],
            function=get_rsi_macd_adx,
            parameters=[
                ToolParam(name="tickers", type="list", required=True, description="List of stock tickers")
            ],
            endpoint="/get-rsi-macd-adx",
            router=router
        )

    return func
