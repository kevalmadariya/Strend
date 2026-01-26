import json
from typing import List, Optional
from datetime import date
from dateutil.relativedelta import relativedelta
from src.core.db import get_db_connection
from src.tools.utils.get_yfinance_data import get_yfinance_data
from src.tools.utils.technical_analysis_utils import calculate_trend, calculate_chart_patterns, calculate_indicators
from ..base import DynamicTool, ToolParam

def makeTool(router):
    
    def func(unique_id):
        
        async def get_technical_analysis(tickers: List[str], type: str = "both"):
            """
            Calculates trend and chart patterns for given tickers and stores them in the database.
            Using yield for streaming response.
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

            yield f"🚀 Started Technical Analysis for {len(tickers)} tickers (Type: {type})\n"

            results_summary = []
            
            end_date = date.today()
            start_date = end_date - relativedelta(months=6)

            for ticker in tickers:
                try:
                    yield f"🔄 Processing {ticker}...\n"
                    
                    # --- 2. Check/Add Stock in DB ---
                    cur.execute("SELECT stock_id FROM stock WHERE ticker = %s AND date = CURRENT_DATE", (ticker,))
                    res = cur.fetchone()
                    
                    stock_id = None
                    if res:
                        stock_id = res[0]
                    else:
                        yield f"   🆕 Stock {ticker} not found in DB. Fetching info...\n"
                        # Use get_yfinance_data logic to add stock
                        stock_info_res = get_yfinance_data(ticker)
                        # if not stock_info_res: # If failed
                        #      yield f"   ⚠️ Could not fetch info for {ticker}. Skipping.\n"
                        #      continue
                             
                        # Check again
                        cur.execute("SELECT stock_id FROM stock WHERE ticker = %s AND date = CURRENT_DATE", (ticker,))
                        res_retry = cur.fetchone()
                        if res_retry:
                            stock_id = res_retry[0]
                        else:
                             yield f"   ❌ Failed to insert {ticker} into stock table. Skipping.\n"
                             continue

                    # --- 3. Check for Existing TA Data ---
                    cur.execute(
                        """
                        SELECT trend, chart_pattern, macd_12_26_9_macd, rsi_14, adx_14 
                        FROM technical_analysis 
                        WHERE stock_id = %s AND date = CURRENT_DATE
                        """,
                        (stock_id,)
                    )
                    existing_ta = cur.fetchone()
                    
                    if existing_ta:
                        yield f"   ℹ️ Data already exists for {ticker}. Retrieved from DB.\n"
                        results_summary.append({
                            "ticker": ticker,
                            "trend": existing_ta[0],
                            "chart_pattern": existing_ta[1],
                            "macd": existing_ta[2],
                            "rsi": existing_ta[3],
                            "adx": existing_ta[4],
                            "source": "cache"
                        })
                        continue

                    # --- 4. Calculate TA ---
                    trend_val = None
                    patterns_str = None
                    indicators = {"macd": 0.0, "macd_signal": 0.0, "macd_hist": 0.0, "rsi": 0.0, "adx": 0.0}

                    if type in ["trend", "both"]:
                        t_int = calculate_trend(ticker, start_date, end_date)
                        trend_val = "Bullish" if t_int == 1 else "Bearish"
                    
                    if type in ["chart_patterns", "both"]:
                         patterns_str = calculate_chart_patterns(ticker, start_date, end_date)
                    
                    # Always calc indicators for completeness if needed, or based on type?
                    # Request implies "tool should calculate both and store". 
                    # Table has columns for indicators, so we should calc them.
                    indicators = calculate_indicators(ticker, start_date, end_date)
                    
                    print("Trend:", trend_val)
                    print("Patterns:", patterns_str)
                    print("Indicators:")
                    print(indicators)
                    # --- 5. Insert into DB ---
                    cur.execute("""
                        INSERT INTO technical_analysis (
                            stock_id, date, trend, chart_pattern, 
                            macd_12_26_9_macd, macd_12_26_9_signal, macd_12_26_9_histogram, 
                            rsi_14, adx_14
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (stock_id, date) DO UPDATE SET
                            trend = EXCLUDED.trend,
                            chart_pattern = EXCLUDED.chart_pattern,
                            macd_12_26_9_macd = EXCLUDED.macd_12_26_9_macd,
                            macd_12_26_9_signal = EXCLUDED.macd_12_26_9_signal,
                            macd_12_26_9_histogram = EXCLUDED.macd_12_26_9_histogram,
                            rsi_14 = EXCLUDED.rsi_14,
                            adx_14 = EXCLUDED.adx_14;
                    """, (
                        stock_id, date.today(), 
                        trend_val, patterns_str,
                        float(indicators.get("macd")) if indicators.get("macd") is not None else None,
                        float(indicators.get("macd_signal")) if indicators.get("macd_signal") is not None else None,
                        float(indicators.get("macd_hist")) if indicators.get("macd_hist") is not None else None,
                        float(indicators.get("rsi")) if indicators.get("rsi") is not None else None,
                        float(indicators.get("adx")) if indicators.get("adx") is not None else None
                    ))
                    conn.commit()
                    
                    yield f"   ✅ Analysis stored for {ticker}.\n"
                    results_summary.append({
                        "ticker": ticker,
                        "trend": trend_val,
                        "chart_pattern": patterns_str,
                        "macd": float(indicators.get("macd")) if indicators.get("macd") is not None else None,
                        "rsi": float(indicators.get("rsi")) if indicators.get("rsi") is not None else None,
                        "adx": float(indicators.get("adx")) if indicators.get("adx") is not None else None,
                        "source": "calculated"
                    })

                except Exception as loop_err:
                    conn.rollback()
                    print("Error processing", ticker, loop_err)
                    yield f"   ❌ Error processing {ticker}: {loop_err}\n"

            conn.close()
            yield "\n✅ Analysis Complete.\n"
            yield json.dumps({"status": "success", "data": results_summary})


        return DynamicTool(
            name="get_technical_analysis",
            description="Calculates trend, chart patterns, and indicators for stocks. RSI, MACD, and ADX indicators for stocks.",
            triggers=["Get trend and patterns", "Analyze chart patterns","Get RSI MACD ADX", "Calculate indicators"],
            function=get_technical_analysis,
            parameters=[
                ToolParam(name="tickers", type="list", required=True, description="List of stock tickers (e.g. ['RELIANCE', 'TCS'])"),
                ToolParam(name="type", type="string", required=False, description="Analysis type: 'trend', 'chart_patterns', or 'both' (default 'both')")
            ],
            endpoint="/get-technical-analysis",
            router=router
        )

    return func
