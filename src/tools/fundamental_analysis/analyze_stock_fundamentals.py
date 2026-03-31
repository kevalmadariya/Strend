from src.core.db import get_db_connection
from src.tools.utils.calculate_fundametal_score import calculate_fundamental_score
from src.tools.utils.fetch_and_store_fundametals import fetch_and_store_fundamentals
from ..base import DynamicTool
from ..base import ToolParam
import json

def makeTool(router):
    """
    Factory function for the Fundamental Analysis Tool.
    """
    def func(unique_id):
        # unique_id is passed from the agent context
        # db_connection and get_fundamentals are assumed to be available in scope
        
        async def analyze_stock_fundamentals(tickers: list[str]):
            """
            Fetches fundamental data for a list of tickers, calculates scores,
            stores results, and returns a summary.
            """
            print(f"📊 Analyzing Fundamentals for: {tickers} (Context: {unique_id})")

            results_summary = []
            conn = get_db_connection()
            cur = conn.cursor()

            # for each ticker find latest fundamental_analysis
            # if fundamental_analysis.id is present in the fundamental_results then skip that ticker

            for ticker in tickers:
                try:
                    print(f"📊 Analyzing Fundamentals for: {ticker} (Context: {unique_id})")

                    # -------------------------
                    # 0. Resolve stock_id
                    # -------------------------
                    cur.execute(
                        "SELECT stock_id FROM stock WHERE ticker = %s",
                        (ticker,)
                    )
                    stock_row = cur.fetchone()

                    if not stock_row:
                        print(f"❌ Stock {ticker} not found in DB.")
                        results_summary.append(
                            {"ticker": ticker, "status": "Error: Stock not found"}
                        )
                        continue

                    stock_id = stock_row[0] if isinstance(stock_row, (tuple, list)) else stock_row

                    # -------------------------
                    # 1. Get latest fundamental_analysis
                    # -------------------------
                    cur.execute("""
                        SELECT fundamental_analysis_id, industry, price, quickratio, peg,
                            sales_growth, roe, roce, profit_growth, cfo_pat_5_yr_avg,
                            debt_equity, interest_cover_ratio, market_cap, p_e, p_b,
                            div_yield, book_value_ttm, eps_ttm,
                            promoter_q1, pledge_q1, fiis_q1, diis_q1
                        FROM fundamental_analysis
                        WHERE stock_id = %s
                        ORDER BY date DESC
                        LIMIT 1
                    """, (stock_id,))

                    row = cur.fetchone()

                    # -------------------------
                    # 2. If missing, fetch fundamentals and retry
                    # -------------------------
                    if not row:
                        print(f"🔍 Data missing for {ticker}. Calling get_fundamentals...")
                        await fetch_and_store_fundamentals([ticker])

                        cur.execute("""
                            SELECT fundamental_analysis_id, industry, price, quickratio, peg,
                                sales_growth, roe, roce, profit_growth, cfo_pat_5_yr_avg,
                                debt_equity, interest_cover_ratio, market_cap, p_e, p_b,
                                div_yield, book_value_ttm, eps_ttm,
                                promoter_q1, pledge_q1, fiis_q1, diis_q1
                            FROM fundamental_analysis
                            WHERE stock_id = %s
                            ORDER BY date DESC
                            LIMIT 1
                        """, (stock_id,))

                        row = cur.fetchone()
                        if not row:
                            raise Exception(
                                f"Failed to retrieve or generate fundamental data for {ticker}"
                            )

                    analysis_id = row[0] if isinstance(row, (tuple, list)) else row

                    # -------------------------
                    # 2.5 Skip if already scored
                    # -------------------------
                    cur.execute(
                        "SELECT total_score,score_percentage,rating,risk_level FROM fundamental_results WHERE fundamental_analysis_id = %s",
                        (analysis_id,)
                    )
                    existing_score = cur.fetchone()
                    if existing_score:
                        print(f"⏭️ Skipping {ticker}, score already exists.")
                        results_summary.append(
                            {
                                "ticker": ticker, 
                                "risk_level": existing_score[3],
                                "rating": existing_score[2],
                                "scored_percentage": existing_score[1]
                            }
                        )
                        continue

                    # -------------------------
                    # 3. Build ratios dict
                    # -------------------------
                    ratios = {
                        'Industry': row[1],
                        'Price': row[2],
                        'QuickRatio': row[3],
                        'PEG': row[4],
                        'Sales Growth': row[5],
                        'ROE': row[6],
                        'ROCE': row[7],
                        'Profit Growth': row[8],
                        'CFO/PAT (5 Yr. Avg.)': row[9],
                        'Debt/Equity': row[10],
                        'Interest Cover Ratio': row[11],
                        'P/E': row[13],
                        'P/B': row[14],
                        'Div. Yield': row[15],
                        'Book Value (TTM)': row[16],
                        'EPS (TTM)': row[17],
                    }

                    holdings = {
                        "latest": {
                            "Promoters": row[18],
                            "Pledge": row[19],
                            "FIIs": row[20],
                            "DIIs": row[21],
                        }
                    }

                    # -------------------------
                    # 4. Scoring
                    # -------------------------
                    result = calculate_fundamental_score(ratios, {}, holdings, {})

                    total_score = result["total_score"]
                    score_percentage = result["score_percentage"]
                    rating = result["rating"]
                    risk_level = result["risk_level"]

                    earnings_yield_score = result["details"].get(
                        "Earnings Yield", {}
                    ).get("score_pct", 0)

                    profit_growth_score = result["details"].get(
                        "Profit Growth", {}
                    ).get("score_pct", 0)

                    sales_growth_score = result["details"].get(
                        "Sales Growth", {}
                    ).get("score_pct", 0)

                    pe_ratio_score = result["details"].get(
                        "P/E Ratio", {}
                    ).get("score_pct", 0)

                    debt_to_equity_score = result["details"].get(
                        "Debt-to-Equity", {}
                    ).get("score_pct", 0)

                    roe_dividend_score = result["details"].get(
                        "ROE & Dividend", {}
                    ).get("score_pct", 0)

                    promoter_dii_fii_holding_score = result["details"].get(
                        "Promoter/DII/FII Holding", {}
                    ).get("score_pct", 0)

                    # -------------------------
                    # 5. Store result
                    # -------------------------
                    cur.execute("""
                        INSERT INTO fundamental_results (
                            fundamental_analysis_id,
                            total_score,
                            score_percentage,
                            rating,
                            risk_level,
                            earnings_yield_score,
                            profit_growth_score,
                            sales_growth_score,
                            pe_ratio_score,
                            debt_to_equity_score,
                            roe_dividend_score,
                            promoter_dii_fii_holding_score
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        analysis_id,
                        total_score,
                        score_percentage,
                        rating,
                        risk_level,
                        earnings_yield_score,
                        profit_growth_score,
                        sales_growth_score,
                        pe_ratio_score,
                        debt_to_equity_score,
                        roe_dividend_score,
                        promoter_dii_fii_holding_score,
                    ))

                    conn.commit()

                    results_summary.append({
                        "ticker": ticker,
                        "risk_level": risk_level,
                        "rating": rating,
                        "scored_percentage" :score_percentage 
                    })
                

                except Exception as e:
                    print(f"❌ Error processing {ticker}: {e}")
                    conn.rollback()
                    results_summary.append(
                        {"ticker": ticker, "status": f"Error: {str(e)}"}
                    )

            cur.close()
            conn.close()

            yield "\n".join([
                f"Stock: {res['ticker']} | Risk: {res.get('risk_level', 'N/A')} | "
                f"Rating: {res.get('rating', 'N/A')} | Scored: {res.get('scored_percentage', 'N/A')}" 
                for res in results_summary
            ])

            yield "\n\n\n"
            
            yield json.dumps({
                "status": "success",
                "data": results_summary
            })

        return DynamicTool(
            name="analyze_stock_fundamentals",
            description="Calculate and store fundamental scores for a specific stock ticker.",
            triggers=["Calculate fundamental score", "Analyze stock quality", "Get stock rating"],
            function=analyze_stock_fundamentals,
            parameters=[
                ToolParam(
                    name="tickers", 
                    type="list", 
                    description="List of stock ticker symbols (e.g., ['RELIANCE', 'TCS'])", 
                    required=True
                )
            ],
            endpoint="/analyze-fundamentals",
            router=router
        )

    return func

