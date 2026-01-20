import json
from typing import List
from datetime import date

from src.core.db import get_db_connection
from src.tools.utils.get_yfinance_data import get_yfinance_data
from src.tools.utils.webscraper import WebScaping


async def fetch_and_store_fundamentals(
    tickers: List[str],
    unique_id: str | None = None
):
    """
    Shared business logic for fetching + storing fundamentals.
    Can be called by multiple tools.
    """

    print(f"✅ Fetching fundamentals | Context={unique_id} | Tickers={tickers}")

    results = {}
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            print("🟢 DB connection opened")

            for ticker in tickers:
                print(f"\n🔹 Processing ticker: {ticker}")

                # 1️⃣ Scrape data
                try:
                    ratios, charts, holdings_raw, analysis = WebScaping(
                        ticker, {}, {}, {}, {}
                    )
                    if not ratios:
                        print(f"❌ Empty scrape for {ticker}")
                        continue
                except Exception as e:
                    print(f"❌ Scraping failed for {ticker}: {e}")
                    continue

                # 2️⃣ Check stock
                cur.execute(
                    "SELECT stock_id FROM stock WHERE ticker = %s",
                    (ticker,)
                )
                row = cur.fetchone()
                stock_id = row[0] if row else None

                # 3️⃣ Insert stock if missing
                if not stock_id:
                    try:
                        get_yfinance_data(ticker)
                        cur.execute(
                            "SELECT stock_id FROM stock WHERE ticker = %s",
                            (ticker,)
                        )
                        stock_id = cur.fetchone()[0]
                    except Exception as e:
                        print(f"❌ Stock insert failed for {ticker}: {e}")
                        continue

                # 4️⃣ Map holdings
                quarters = ["Sep 2025", "Jun 2025", "Mar 2025", "Dec 2024"]
                holdings = {}

                for i, q in enumerate(quarters, start=1):
                    qd = holdings_raw.get(q, {})
                    holdings[f"promoter_q{i}"] = qd.get("Promoter", 0.0)
                    holdings[f"pledge_q{i}"] = qd.get("Pledge", 0.0)
                    holdings[f"fiis_q{i}"] = qd.get("FIIs", 0.0)
                    holdings[f"diis_q{i}"] = qd.get("DIIs", 0.0)
                    holdings[f"government_q{i}"] = qd.get("Government", 0.0)
                    holdings[f"public_q{i}"] = qd.get("Public", 0.0)

                # 5️⃣ Upsert fundamentals
                today = date.today()
                strengths_json = json.dumps(analysis.get("Strength", []))
                limitations_json = json.dumps(analysis.get("Limitation", []))

                cur.execute(
                    """
                    INSERT INTO fundamental_analysis (
                        stock_id, date, industry, description, sector, price,
                        quickratio, peg, sales_growth, roe, roce, profit_growth,
                        cfo_pat_5_yr_avg, debt_equity, interest_cover_ratio,
                        strengths, limitations,
                        promoter_q1, promoter_q2, promoter_q3, promoter_q4,
                        pledge_q1, pledge_q2, pledge_q3, pledge_q4,
                        fiis_q1, fiis_q2, fiis_q3, fiis_q4,
                        diis_q1, diis_q2, diis_q3, diis_q4,
                        government_q1, government_q2, government_q3, government_q4,
                        public_q1, public_q2, public_q3, public_q4,
                        market_cap, enterprise_value, no_of_shares,
                        p_e, p_b, div_yield, book_value_ttm,
                        cash, debt, promoter_holding, eps_ttm
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s)
                    ON CONFLICT (stock_id, date) DO UPDATE
                    SET price = EXCLUDED.price,
                        quickratio = EXCLUDED.quickratio,
                        strengths = EXCLUDED.strengths,
                        limitations = EXCLUDED.limitations
                    """,
                    (
                        stock_id, today,
                        ratios.get("Industry"), ratios.get("Description"),
                        ratios.get("Sector"), ratios.get("Price"),
                        ratios.get("QuickRatio"), ratios.get("PEG"),
                        ratios.get("Sales Growth", 0.0),
                        ratios.get("ROE", 0.0), ratios.get("ROCE", 0.0),
                        ratios.get("Profit Growth", 0.0),
                        ratios.get("CFO/PAT (5 Yr. Avg.)", 0.0),
                        ratios.get("Debt/Equity", 0.0),
                        ratios.get("Interest Cover Ratio", 0.0),
                        strengths_json, limitations_json,
                        holdings["promoter_q1"], holdings["promoter_q2"],
                        holdings["promoter_q3"], holdings["promoter_q4"],
                        holdings["pledge_q1"], holdings["pledge_q2"],
                        holdings["pledge_q3"], holdings["pledge_q4"],
                        holdings["fiis_q1"], holdings["fiis_q2"],
                        holdings["fiis_q3"], holdings["fiis_q4"],
                        holdings["diis_q1"], holdings["diis_q2"],
                        holdings["diis_q3"], holdings["diis_q4"],
                        holdings["government_q1"], holdings["government_q2"],
                        holdings["government_q3"], holdings["government_q4"],
                        holdings["public_q1"], holdings["public_q2"],
                        holdings["public_q3"], holdings["public_q4"],
                        ratios.get("Market Cap"),
                        ratios.get("Enterprise Value"),
                        ratios.get("No. of Shares"),
                        ratios.get("P/E"), ratios.get("P/B"),
                        ratios.get("Div. Yield"),
                        ratios.get("Book Value (TTM)"),
                        ratios.get("CASH"), ratios.get("DEBT"),
                        ratios.get("Promoter Holding"),
                        ratios.get("EPS (TTM)")
                    )
                )

                results[ticker] = ratios

            conn.commit()
            print("💾 DB commit successful")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        print("🔴 DB connection closed")

    return {"status": "success", "data": results}
