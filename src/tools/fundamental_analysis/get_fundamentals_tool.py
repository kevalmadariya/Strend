import json
from typing import List, Optional
from src.core.db import get_db_connection
from datetime import date

from src.tools.utils.get_yfinance_data import get_yfinance_data
from ..base import DynamicTool, ToolParam

# Import your existing WebScraping logic
from src.tools.utils.webscraper import WebScaping 
from src.tools.utils.fetch_and_store_fundametals import fetch_and_store_fundamentals

def makeTool(router):

    def func(unique_id):

        async def get_fundamentals(tickers: Optional[List[str]] = None, text: Optional[str] = None):
            import re

            all_tickers = set(tickers) if tickers else set()
            
            # Extract tickers from text if provided
            if text:
                # Regex to find potential tickers: UPPERCASE words with length >= 3
                found_in_text = re.findall(r'\b[A-Z0-9]{3,}\b', text)
                for t in found_in_text:
                    if t not in ["AND", "FOR", "THE", "WITH", "ARE", "NOT", "YES", "CAN", "YOU", "BUT"]:
                        all_tickers.add(t)

            if not all_tickers:
                 yield "⚠️ No tickers provided. Please specify tickers in the list or mention them in the text.\n"
                 return

            print(f"🚀 Getting fundamentals for: {all_tickers}")
            conn = get_db_connection()
            cur = conn.cursor()
            
            final_results = {}
            tickers_to_fetch = []
            
            for ticker in all_tickers:
                # Check for recent data
                cur.execute("""
                    SELECT 
                        fa.date, 
                        fa.industry, fa.description, fa.sector, fa.price, 
                        fa.quickratio, fa.peg, fa.sales_growth, fa.roe, fa.roce, fa.profit_growth, 
                        fa.cfo_pat_5_yr_avg, fa.debt_equity, fa.interest_cover_ratio,
                        fa.market_cap, fa.enterprise_value, fa.no_of_shares, fa.p_e, fa.p_b, 
                        fa.div_yield, fa.book_value_ttm, fa.cash, fa.debt, fa.promoter_holding, fa.eps_ttm 
                    FROM stock s
                    JOIN fundamental_analysis fa ON s.stock_id = fa.stock_id
                    WHERE s.ticker = %s
                    ORDER BY fa.date DESC
                    LIMIT 1
                """, (ticker,))
                
                row = cur.fetchone()
                
                is_cached = False
                if row:
                    last_fa_date = row[0]
                    if last_fa_date:
                        days_diff = (date.today() - last_fa_date).days
                        if days_diff <= 30:
                            # Reconstruct the ratios dict (matching fetch_and_store_fundamentals structure)
                            ratios = {
                                "Industry": row[1],
                                "Description": row[2],
                                "Sector": row[3],
                                "Price": float(row[4]) if row[4] is not None else 0.0,
                                "QuickRatio": float(row[5]) if row[5] is not None else None,
                                "PEG": float(row[6]) if row[6] is not None else None,
                                "Sales Growth": float(row[7]) if row[7] is not None else 0.0,
                                "ROE": float(row[8]) if row[8] is not None else 0.0,
                                "ROCE": float(row[9]) if row[9] is not None else 0.0,
                                "Profit Growth": float(row[10]) if row[10] is not None else 0.0,
                                "CFO/PAT (5 Yr. Avg.)": float(row[11]) if row[11] is not None else 0.0,
                                "Debt/Equity": float(row[12]) if row[12] is not None else 0.0,
                                "Interest Cover Ratio": float(row[13]) if row[13] is not None else 0.0,
                                "Market Cap": float(row[14]) if row[14] is not None else 0.0,
                                "Enterprise Value": float(row[15]) if row[15] is not None else 0.0,
                                "No. of Shares": float(row[16]) if row[16] is not None else 0.0,
                                "P/E": float(row[17]) if row[17] is not None else 0.0,
                                "P/B": float(row[18]) if row[18] is not None else 0.0,
                                "Div. Yield": float(row[19]) if row[19] is not None else 0.0,
                                "Book Value (TTM)": float(row[20]) if row[20] is not None else 0.0,
                                "CASH": float(row[21]) if row[21] is not None else 0.0,
                                "DEBT": float(row[22]) if row[22] is not None else 0.0,
                                "Promoter Holding": float(row[23]) if row[23] is not None else 0.0,
                                "EPS (TTM)": float(row[24]) if row[24] is not None else 0.0
                            }
                            final_results[ticker] = ratios
                            yield f"   ✅ Found cached fundamentals for {ticker} (Last updated: {last_fa_date})\n"
                            is_cached = True
            
                if not is_cached:
                    tickers_to_fetch.append(ticker)
            
            conn.close()

            if tickers_to_fetch:
                yield f"   🔄 Fetching fresh fundamentals for: {', '.join(tickers_to_fetch)}\n"
                fresh_data = await fetch_and_store_fundamentals(tickers_to_fetch, unique_id)
                if fresh_data and "data" in fresh_data:
                    final_results.update(fresh_data["data"])
            
            yield json.dumps({"status": "success", "data": final_results})

        return DynamicTool(
            name="get_fundamentals",
            description="Fetch fundamental analysis for tickers",
            triggers=["Get fundamental analysis", "Fetch stock fundamentals"],
            function=get_fundamentals,
            parameters=[
                ToolParam(name="tickers", type="list", required=False, description="List of stock tickers"),
                ToolParam(name="text", type="string", required=False, description="Text containing stock tickers (e.g. 'Fundamentals of RELIANCE')")
            ],
            endpoint="/get-fundamentals",
            router=router
        )

    return func
