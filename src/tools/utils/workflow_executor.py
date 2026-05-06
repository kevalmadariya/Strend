"""
Workflow Executor
=================
Runs an entire workflow pipeline in a **separate process**.
Each step receives the stock list from the previous step (pipeline pattern).
The workflow order is defined by the user in the POST payload.

Supported steps:
  - stock_pick    → Scrape stocks from Chartink
  - filter        → Apply volume/price/%chg filters
  - technical_analysis → Compute trend/MACD/RSI/ADX and filter
  - fundamental_analysis → Compute fundamental score and filter
  - news_analysis → Scrape news and filter by recency
  - email         → Send results via email (PDF or Excel)
"""

import os
import sys
import re
import asyncio
import logging
import traceback
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# Ensure project root is on sys.path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("workflow_executor")

# ─── Chartink method → URL mapping ───────────────────────────────────────────
CHARTINK_METHOD_URLS = {
    "macd_bullish": "https://chartink.com/screener/macd-bullish-crossover",
    "macd_bullish_rsi": "https://chartink.com/screener/macd-bullish-crossover-with-rsi",
    "macd_bullish_adx": "https://chartink.com/screener/macd-bullish-crossover-with-adx",
    "rsi_70_above": "https://chartink.com/screener/rsi-above-70",
    "simple": "https://chartink.com/screener/macd-bearish-or-bullish-crossover",
    "macd_bearish_bullish": "https://chartink.com/screener/macd-bearish-or-bullish-crossover",
}

# Recent news patterns (reused from strategy_scheduler)
RECENT_NEWS_PATTERNS = [
    r"\d+\s*sec(?:s|ond|onds)?\s*ago",
    r"\d+\s*min(?:s|ute|utes)?\s*ago",
    r"\d+\s*hour(?:s)?\s*ago",
    r"a\s+min(?:ute)?\s+ago",
    r"a\s+sec(?:ond)?\s+ago",
    r"an?\s+hour\s+ago",
    r"just\s*now",
    r"a\s+day\s+ago",
    r"1\s+day\s+ago",
    r"today",
]


def _is_recent_news(time_str: str) -> bool:
    """Check if a time string indicates recent / today's news."""
    time_lower = time_str.lower().strip()
    return any(re.search(p, time_lower) for p in RECENT_NEWS_PATTERNS)


def _parse_number(value) -> float:
    """Safely parse a formatted number string."""
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(value))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def _find_column_index(headers: list, *keywords: str) -> int:
    """Find column index by keyword match."""
    for i, header in enumerate(headers):
        h = header.lower().strip()
        for kw in keywords:
            if kw.lower() in h:
                return i
    return -1


# =============================================================================
# STEP: stock_pick
# =============================================================================

async def _step_stock_pick(params: Dict, current_stocks: List[Dict]) -> List[Dict]:
    """
    Scrape stocks from Chartink OR use a provided stock_list.

    params:
        stock_list: str  — comma-separated tickers (optional)
        method: str      — one of CHARTINK_METHOD_URLS keys
        no_of_stocks: int — total stocks desired (pages = no_of_stocks / 20)
        query: str       — custom Chartink query text (optional)
    """
    from src.tools.utils.chartink_scraper import fetch_chartink_data

    stock_list_str = params.get("stock_list", "").strip()
    method = params.get("method", "macd_bearish_bullish")
    no_of_stocks = int(params.get("no_of_stocks", 60))
    query = params.get("query", "")

    pages = max(1, no_of_stocks // 20)

    # If user provided a static stock list, skip chartink scraping
    if stock_list_str:
        tickers = [t.strip().upper() for t in stock_list_str.split(",") if t.strip()]
        logger.info(f"📋 stock_pick: Using provided stock list ({len(tickers)} tickers)")
        
        from src.tools.utils.get_yfinance_data import get_yfinance_data

        async def _fetch_single(ticker: str):
            try:
                res = await asyncio.to_thread(get_yfinance_data, ticker)
                if res and res.get("results"):
                    return res["results"]
            except Exception as e:
                logger.warning(f"⚠️ Failed to fetch yfinance data for {ticker}: {e}")
            return {"ticker": ticker, "name": ticker, "price": 0, "volume": 0, "percent_change": 0}

        # Fetch data for all tickers in parallel
        tasks = [_fetch_single(t) for t in tickers]
        stocks = await asyncio.gather(*tasks)
        return stocks

    # Otherwise, scrape from Chartink
    url = CHARTINK_METHOD_URLS.get(method, CHARTINK_METHOD_URLS["macd_bearish_bullish"])
    logger.info(f"🌐 stock_pick: Scraping Chartink method='{method}' pages={pages}")

    try:
        headers, all_rows = await fetch_chartink_data(
            url=url,
            query_text=query if query else None,
            total_pages=pages,
        )
    except Exception as e:
        logger.error(f"❌ Chartink scraping failed: {e}")
        return []

    if not headers or not all_rows:
        logger.warning("⚠️ No data returned from Chartink")
        return []

    # Parse rows into stock dicts
    name_idx = _find_column_index(headers, "stock", "name", "company")
    ticker_idx = _find_column_index(headers, "symbol", "ticker", "nsecode")
    price_idx = _find_column_index(headers, "close", "price", "ltp")
    volume_idx = _find_column_index(headers, "volume", "vol")
    chg_idx = _find_column_index(headers, "change", "%chg", "chg")

    # Fallbacks
    if name_idx == -1 and len(headers) > 1: name_idx = 1
    if ticker_idx == -1 and len(headers) > 2: ticker_idx = 2
    if price_idx == -1 and len(headers) > 3: price_idx = 3
    if volume_idx == -1 and len(headers) > 4: volume_idx = 4

    stocks = []
    for row in all_rows:
        try:
            stocks.append({
                "name": row[name_idx].strip() if name_idx < len(row) else "Unknown",
                "ticker": row[ticker_idx].strip() if ticker_idx < len(row) else "",
                "price": _parse_number(row[price_idx]) if price_idx < len(row) else 0,
                "volume": _parse_number(row[volume_idx]) if volume_idx < len(row) else 0,
                "percent_change": _parse_number(row[chg_idx]) if chg_idx >= 0 and chg_idx < len(row) else 0,
            })
        except (IndexError, ValueError) as e:
            logger.debug(f"Row parse error: {e}")
            continue

    logger.info(f"✅ stock_pick: Got {len(stocks)} stocks from Chartink")
    return stocks


# =============================================================================
# STEP: filter
# =============================================================================

async def _step_filter(params: Dict, current_stocks: List[Dict]) -> List[Dict]:
    """
    Apply volume/price/%chg filters.

    params:
        filters: List[Dict]  — [{"field":"volume","operator":"greater","value":50000}, ...]
    """
    from src.tools.utils.workflow_filter_utils import apply_stock_filters

    filters = params.get("filters", [])
    return apply_stock_filters(current_stocks, filters)


# =============================================================================
# STEP: technical_analysis
# =============================================================================

async def _step_technical_analysis(params: Dict, current_stocks: List[Dict]) -> List[Dict]:
    """
    Calculate trend & indicators for each stock, then filter.

    params:
        filters: List[Dict] — [{"field":"trend","operator":"equals","value":1}, ...]
    """
    from src.tools.utils.technical_analysis_utils import calculate_trend, calculate_indicators
    from src.tools.utils.workflow_filter_utils import apply_technical_filters

    months = int(os.getenv("ANALYSIS_MONTHS", "6"))
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)

    filters = params.get("filters", [])

    enriched = []
    for stock in current_stocks:
        ticker = stock.get("ticker", "")
        if not ticker:
            continue
        try:
            trend = await asyncio.to_thread(calculate_trend, ticker, start_date, end_date)
            indicators = await asyncio.to_thread(calculate_indicators, ticker, start_date, end_date)
            stock["trend"] = trend
            stock["indicators"] = indicators
            enriched.append(stock)
        except Exception as e:
            logger.warning(f"⚠️ Technical analysis failed for {ticker}: {e}")
            stock["trend"] = 0
            stock["indicators"] = {"macd": 0, "macd_signal": 0, "macd_hist": 0, "rsi": 0, "adx": 0}
            enriched.append(stock)

    return apply_technical_filters(enriched, filters)


# =============================================================================
# STEP: fundamental_analysis
# =============================================================================

async def _step_fundamental_analysis(params: Dict, current_stocks: List[Dict]) -> List[Dict]:
    """
    Calculate fundamental score for each stock, then filter.

    params:
        filters: List[Dict] — [{"field":"score","operator":"greater","value":60}, ...]
    """
    from src.tools.utils.webscraper import WebScaping
    from src.tools.utils.calculate_fundametal_score import calculate_fundamental_score
    from src.tools.utils.workflow_filter_utils import apply_fundamental_filters

    filters = params.get("filters", [])

    for stock in current_stocks:
        ticker = stock.get("ticker", "")
        if not ticker:
            continue
        try:
            ratios, charts, holdings_raw, analysis = await asyncio.to_thread(
                WebScaping, ticker, {}, {}, {}, {}
            )
            if not ratios:
                stock["fundamental_data"] = {"score_percentage": 0, "rating": "N/A"}
                continue

            # Build holdings dict for score calculation
            holdings = {}
            if holdings_raw:
                for q_name, q_data in holdings_raw.items():
                    holdings[q_name] = q_data

            score_result = calculate_fundamental_score(ratios, charts, holdings, analysis)
            stock["fundamental_data"] = score_result
        except Exception as e:
            logger.warning(f"⚠️ Fundamental analysis failed for {ticker}: {e}")
            stock["fundamental_data"] = {"score_percentage": 0, "rating": "N/A"}

    return apply_fundamental_filters(current_stocks, filters)


# =============================================================================
# STEP: news_analysis
# =============================================================================

async def _step_news_analysis(params: Dict, current_stocks: List[Dict]) -> List[Dict]:
    """
    Scrape news for each stock and filter by recency.

    params:
        filters: List[Dict] — [{"field":"recent","operator":"equals","value":true}, ...]
    """
    from src.tools.utils.news_scraper import scrape_news_from_groww
    from src.tools.utils.workflow_filter_utils import apply_news_filters

    filters = params.get("filters", [])

    for stock in current_stocks:
        ticker = stock.get("ticker", "")
        if not ticker:
            continue
        try:
            logger.info(f"📰 Scraping news for: {ticker}")
            news_items = await scrape_news_from_groww(ticker)
            recent = [n for n in news_items if _is_recent_news(n.get("time_str", ""))]
            stock["news"] = news_items
            stock["recent_news"] = recent
            stock["has_recent_news"] = len(recent) > 0
        except Exception as e:
            logger.warning(f"⚠️ News scraping failed for {ticker}: {e}")
            stock["news"] = []
            stock["recent_news"] = []
            stock["has_recent_news"] = False

    return apply_news_filters(current_stocks, filters)


# =============================================================================
# STEP: email
# =============================================================================

async def _step_email(params: Dict, current_stocks: List[Dict], user_email: str) -> List[Dict]:
    """
    Send results via email as PDF or Excel.

    params:
        email: str   — recipient email (defaults to user's email)
        format: str  — "pdf" or "excel"
    """
    from src.tools.utils.email_utils import (
        make_workflow_html,
        html_to_pdf,
        stocks_to_excel,
        send_mail,
    )

    recipient = params.get("email", user_email) or user_email
    fmt = params.get("format", "pdf").lower().strip()
    title = params.get("title", "Strend Workflow Report")

    logger.info(f"📧 email step: Sending {fmt} report to {recipient}")

    html_content = make_workflow_html(current_stocks, title=title)

    attachment_path = None
    try:
        if fmt == "pdf":
            attachment_path = html_to_pdf(html_content, title=title)
        elif fmt == "excel":
            attachment_path = stocks_to_excel(current_stocks, title=title)
        else:
            logger.warning(f"⚠️ Unknown format '{fmt}', defaulting to PDF")
            attachment_path = html_to_pdf(html_content, title=title)
    except Exception as e:
        logger.error(f"❌ Failed to generate {fmt} attachment: {e}")

    # Send the email
    subject = f"📊 {title} — {date.today().isoformat()}"
    send_mail(
        recipient=recipient,
        subject=subject,
        body=html_content,
        attachment_path=attachment_path,
    )

    # Cleanup temp file
    if attachment_path and os.path.exists(attachment_path):
        try:
            os.remove(attachment_path)
        except OSError:
            pass

    return current_stocks


# =============================================================================
# Step dispatcher
# =============================================================================

STEP_HANDLERS = {
    "stock_pick": _step_stock_pick,
    "filter": _step_filter,
    "technical_analysis": _step_technical_analysis,
    "fundamental_analysis": _step_fundamental_analysis,
    "news_analysis": _step_news_analysis,
    "email": _step_email,
}


# =============================================================================
# Notification helper (stores in DB)
# =============================================================================

def _store_notification(user_id: int, message: str, stock_tickers: List[str]):
    """Store workflow completion notification in the notification table."""
    from src.core.db import get_db_connection

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if stock_tickers:
            for ticker in stock_tickers:
                # Look up stock_id for this ticker
                cur.execute(
                    "SELECT stock_id FROM stock WHERE ticker = %s ORDER BY date DESC LIMIT 1",
                    (ticker,)
                )
                row = cur.fetchone()
                stock_id = row[0] if row else None

                cur.execute(
                    """
                    INSERT INTO notification (stock_id, date, notification, user_id)
                    VALUES (%s, CURRENT_DATE, %s, %s)
                    ON CONFLICT (stock_id, date, user_id, watchlist_id) DO NOTHING
                    """,
                    (stock_id, message, user_id)
                )
        else:
            # No stocks — just store a general notification
            cur.execute(
                """
                INSERT INTO notification (stock_id, date, notification, user_id)
                VALUES (NULL, CURRENT_DATE, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (message, user_id)
            )

        conn.commit()
        logger.info(f"🔔 Notification stored for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to store notification: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


# =============================================================================
# Main executor — entry point for the child process
# =============================================================================

def run_workflow_process(workflow_steps: List[Dict], user_id: int, user_email: str):
    """
    Entry point for multiprocessing.Process.
    Sets up its own event loop and runs the async pipeline.
    This runs in a SEPARATE process — no FastAPI, no uvicorn.
    """
    # Setup logging for the child process
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [WORKFLOW-PID-%(process)d] %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    child_logger = logging.getLogger("workflow_executor")
    child_logger.info(f"🚀 Workflow process started | user_id={user_id} | steps={len(workflow_steps)}")

    # On Windows, use ProactorEventLoop for Playwright compatibility
    if os.getenv("ENVIRONMENT_OS", sys.platform) == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(_execute_pipeline(workflow_steps, user_id, user_email))
    except Exception as e:
        child_logger.error(f"❌ Workflow process crashed: {e}\n{traceback.format_exc()}")
        # _store_notification(
        #     user_id,
        #     f"❌ Workflow failed: {str(e)[:200]}",
        #     []
        # )
    finally:
        loop.close()
        child_logger.info("🏁 Workflow process finished")


async def _execute_pipeline(workflow_steps: List[Dict], user_id: int, user_email: str):
    """Execute the workflow steps in order, passing stock list between steps."""
    current_stocks: List[Dict] = []

    total_steps = len(workflow_steps)
    for idx, step_config in enumerate(workflow_steps, 1):
        step_name = step_config.get("step", "").lower().strip()
        params = step_config.get("params", {})

        logger.info(f"\n{'='*60}")
        logger.info(f"📌 Step {idx}/{total_steps}: {step_name}")
        logger.info(f"   Params: {params}")
        logger.info(f"   Input stocks: {len(current_stocks)}")
        logger.info(f"{'='*60}")

        handler = STEP_HANDLERS.get(step_name)
        if not handler:
            logger.warning(f"⚠️ Unknown step '{step_name}', skipping")
            continue

        try:
            if step_name == "email":
                current_stocks = await handler(params, current_stocks, user_email)
            else:
                current_stocks = await handler(params, current_stocks)
        except Exception as e:
            logger.error(f"❌ Step '{step_name}' failed: {e}\n{traceback.format_exc()}")
            # Continue with whatever stocks we have

        logger.info(f"   Output stocks: {len(current_stocks)}")

    # ─── Store completion notification ────────────────────────────────────
    surviving_tickers = [s.get("ticker", "") for s in current_stocks if s.get("ticker")]
    summary = (
        f"✅ Workflow completed — {total_steps} step(s) executed. "
        f"{len(current_stocks)} stock(s) survived the pipeline: "
        f"{', '.join(surviving_tickers[:10])}"
        f"{'...' if len(surviving_tickers) > 10 else ''}"
    )
    logger.info(summary)
    # _store_notification(user_id, summary, surviving_tickers[:20])
