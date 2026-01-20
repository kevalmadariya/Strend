import json
from typing import List
from ..base import DynamicTool, ToolParam
from ..db import get_db_session  # your DB session helper
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import date
import asyncio

# Import your existing WebScraping logic as a helper
from .webscraper import WebScaping  # make sure this is modularized


def makeTool(router):
    """
    Factory function for the get_fundamentals Tool.
    """

    def func(unique_id):
        """
        The outer function is called with agent unique_id.
        """

        async def get_fundamentals(tickers: List[str]):
            """
            Main function executed by the LLM when it calls this tool.
            """
            print(f"✅ Executing get_fundamentals for ID: {unique_id} with tickers: {tickers}")

            db = get_db_session()  # SQLAlchemy session or your DB helper
            results = {}

            for ticker in tickers:
                print(f"🔹 Processing ticker: {ticker}")

                # 1️⃣ Scrape the fundamental data
                ratios, charts, holdings, analysis = WebScaping(ticker, {}, {}, {}, {})

                # 2️⃣ Add stock details if not exists
                stock = db.query("SELECT stock_id FROM stock WHERE ticker=:ticker", {"ticker": ticker}).fetchone()
                if not stock:
                    stock_data = yf.Ticker(ticker).info
                    db.execute(
                        """
                        INSERT INTO stock (name, ticker, price)
                        VALUES (:name, :ticker, :price)
                        RETURNING stock_id
                        """,
                        {
                            "name": stock_data.get("shortName", ticker),
                            "ticker": ticker,
                            "price": ratios.get("Price", 0.0)
                        }
                    )
                    stock_id = db.fetchone()[0]
                else:
                    stock_id = stock[0]

                # 3️⃣ Insert fundamental analysis
                today = date.today()
                db.execute(
                    """
                    INSERT INTO fundamental_analysis (
                        stock_id, date, industry, description, sector, price, quickratio, peg,
                        sales_growth, roe, roce, profit_growth, cfo_pat_5_yr_avg, debt_equity,
                        interest_cover_ratio, strengths, limitations, promoter_q1, promoter_q2,
                        promoter_q3, promoter_q4, pledge_q1, pledge_q2, pledge_q3, pledge_q4,
                        fiis_q1, fiis_q2, fiis_q3, fiis_q4, diis_q1, diis_q2, diis_q3, diis_q4,
                        government_q1, government_q2, government_q3, government_q4,
                        public_q1, public_q2, public_q3, public_q4
                    )
                    VALUES (
                        :stock_id, :date, :industry, :description, :sector, :price, :quickratio, :peg,
                        :sales_growth, :roe, :roce, :profit_growth, :cfo_pat_5_yr_avg, :debt_equity,
                        :interest_cover_ratio, :strengths, :limitations, :promoter_q1, :promoter_q2,
                        :promoter_q3, :promoter_q4, :pledge_q1, :pledge_q2, :pledge_q3, :pledge_q4,
                        :fiis_q1, :fiis_q2, :fiis_q3, :fiis_q4, :diis_q1, :diis_q2, :diis_q3, :diis_q4,
                        :government_q1, :government_q2, :government_q3, :government_q4,
                        :public_q1, :public_q2, :public_q3, :public_q4
                    )
                    ON CONFLICT (stock_id, date) DO UPDATE
                    SET industry=:industry, description=:description, sector=:sector, price=:price
                    """,
                    {
                        "stock_id": stock_id,
                        "date": today,
                        "industry": ratios.get("Industry"),
                        "description": ratios.get("Description"),
                        "sector": ratios.get("Sector"),
                        "price": ratios.get("Price"),
                        "quickratio": ratios.get("QuickRatio"),
                        "peg": ratios.get("PEG"),
                        "sales_growth": charts.get("SalesGrowth", 0.0),
                        "roe": charts.get("ROE", 0.0),
                        "roce": charts.get("ROCE", 0.0),
                        "profit_growth": charts.get("ProfitGrowth", 0.0),
                        "cfo_pat_5_yr_avg": ratios.get("CFO_PAT_5_YR_AVG", 0.0),
                        "debt_equity": ratios.get("DebtEquity", 0.0),
                        "interest_cover_ratio": ratios.get("InterestCoverRatio", 0.0),
                        "strengths": str(analysis.get("Strength", [])),
                        "limitations": str(analysis.get("Limitation", [])),
                        "promoter_q1": holdings.get("PromoterQ1", 0.0),
                        "promoter_q2": holdings.get("PromoterQ2", 0.0),
                        "promoter_q3": holdings.get("PromoterQ3", 0.0),
                        "promoter_q4": holdings.get("PromoterQ4", 0.0),
                        "pledge_q1": holdings.get("PledgeQ1", 0.0),
                        "pledge_q2": holdings.get("PledgeQ2", 0.0),
                        "pledge_q3": holdings.get("PledgeQ3", 0.0),
                        "pledge_q4": holdings.get("PledgeQ4", 0.0),
                        "fiis_q1": holdings.get("FIIsQ1", 0.0),
                        "fiis_q2": holdings.get("FIIsQ2", 0.0),
                        "fiis_q3": holdings.get("FIIsQ3", 0.0),
                        "fiis_q4": holdings.get("FIIsQ4", 0.0),
                        "diis_q1": holdings.get("DIIsQ1", 0.0),
                        "diis_q2": holdings.get("DIIsQ2", 0.0),
                        "diis_q3": holdings.get("DIIsQ3", 0.0),
                        "diis_q4": holdings.get("DIIsQ4", 0.0),
                        "government_q1": holdings.get("GovernmentQ1", 0.0),
                        "government_q2": holdings.get("GovernmentQ2", 0.0),
                        "government_q3": holdings.get("GovernmentQ3", 0.0),
                        "government_q4": holdings.get("GovernmentQ4", 0.0),
                        "public_q1": holdings.get("PublicQ1", 0.0),
                        "public_q2": holdings.get("PublicQ2", 0.0),
                        "public_q3": holdings.get("PublicQ3", 0.0),
                        "public_q4": holdings.get("PublicQ4", 0.0),
                    },
                )

                db.commit()

                # 4️⃣ Save results for frontend
                results[ticker] = {
                    "ratios": ratios,
                    "charts": charts,
                    "holdings": holdings,
                    "analysis": analysis
                }

                yield json.dumps({
                    "ticker": ticker,
                    "status": "completed",
                    "data": results[ticker]
                })

            return results

        # 2. Return the DynamicTool definition
        return DynamicTool(
            name="get_fundamentals",
            description="Fetch fundamental analysis for a list of tickers, scrape data, store in DB, and return JSON",
            triggers=["Get fundamental analysis", "Fetch stock fundamentals"],
            function=get_fundamentals,
            parameters=[
                ToolParam(
                    name="tickers",
                    type="list",
                    description="List of stock tickers to fetch fundamentals for",
                    required=True
                )
            ],
            endpoint="/get-fundamentals",
            router=router
        )

    return func
