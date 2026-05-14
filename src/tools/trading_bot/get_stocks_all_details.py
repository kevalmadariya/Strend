import json
import yfinance as yf
import pandas as pd
from datetime import timedelta, datetime
from typing import List, Optional
import re

from ..base import DynamicTool, ToolParam


def makeTool(router):
    def func(unique_id):

        async def fetch_stock_data_tool(
            tickers: Optional[List[str]] = None,
            from_date: Optional[str] = None,
            to_date: Optional[str] = None,
            particular_dates: Optional[List[str]] = None,
            duration: Optional[str] = None,
            timeframe: Optional[str] = None,
            text: Optional[str] = None
        ):
            # 🔹 Extract tickers from text
            all_tickers = set(tickers) if tickers else set()

            if text:
                found = re.findall(r'\b[A-Z0-9\.]{3,}\b', text)
                for t in found:
                    if t not in ["AND", "FOR", "THE", "WITH"]:
                        all_tickers.add(t)

            if not all_tickers:
                yield "[!] No tickers provided.\n"
                return

            tf_map = {
                '1min': '1m', '2min': '2m', '15min': '15m',
                '1day': '1d', '1mon': '1mo', '1year': '1y','15m' : '15m' 
            }
            print("timeframe:", timeframe)
            interval = tf_map.get(timeframe, '1d') if timeframe else '1d'

            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=1)

            # 🔹 Date handling
            if from_date and to_date:
                start_dt = pd.to_datetime(from_date)
                end_dt = pd.to_datetime(to_date)

            elif duration:
                amount = int(re.search(r'\d+', duration).group())
                unit = duration.lower()

                if 'min' in unit:
                    start_dt = end_dt - timedelta(minutes=amount)
                elif 'h' in unit:
                    start_dt = end_dt - timedelta(hours=amount)
                elif 'd' in unit:
                    start_dt = end_dt - timedelta(days=amount)
                elif 'm' in unit:
                    start_dt = end_dt - timedelta(days=amount * 30)
                elif 'y' in unit:
                    start_dt = end_dt - timedelta(days=amount * 365)

            elif particular_dates:
                p_dates = [pd.to_datetime(d) for d in particular_dates]
                start_dt = min(p_dates)
                end_dt = max(p_dates) + timedelta(days=1)

            # 🔹 Intraday restriction
            if interval in ['1m', '2m', '15m']:
                if (datetime.now() - start_dt).days > 60:
                    yield "[!] Intraday data only available for last ~60 days.\n"
                    return

            results = {}

            for ticker in all_tickers:
                ticker_symbol = ticker if "." in ticker else f"{ticker}.NS"

                yield f"[..] Fetching data for {ticker_symbol}...for this timeframe {interval}\n"

                try:
                    stocks = yf.download(
                        ticker_symbol,
                        start=start_dt,
                        end=end_dt + timedelta(days=1),
                        interval=interval,
                        group_by='ticker',
                        auto_adjust=False,
                        progress=False
                    )
                    
                    print("stock data")
                    print(stocks)
                    print(stocks.columns)
                    if stocks.empty:
                        yield f"[!] No data found for {ticker_symbol}\n"
                        results[ticker_symbol] = []
                        continue

                    # 🔹 Fix MultiIndex
                    if isinstance(stocks.columns, pd.MultiIndex):
                        # Level 0 is Ticker, Level 1 is the metric (Open, High, etc.)
                        stocks.columns = stocks.columns.get_level_values(1)

                    # 🔹 Add Ticker column
                    stocks['Ticker'] = ticker_symbol

                    stocks = stocks.dropna().reset_index()

                    # 🔹 Rename Date/Datetime to Datetime and convert to string
                    if 'Date' in stocks.columns:
                        stocks = stocks.rename(columns={'Date': 'Datetime'})
                    
                    if 'Datetime' in stocks.columns:
                        stocks['Datetime'] = stocks['Datetime'].astype(str)

                    # 🔹 Add Price column (as an alias for Close)
                    if 'Close' in stocks.columns:
                        stocks['Price'] = stocks['Close']

                    # 🔹 Ensure columns match user request where possible
                    if 'Adj Close' in stocks.columns:
                        stocks['Adj CLose'] = stocks['Adj Close'] # Matching user's specific casing if intended

                    results[ticker_symbol] = stocks.to_dict(orient='records')

                    yield f"[+] Done: {ticker_symbol} ({len(stocks)} rows)\n"

                except Exception as e:
                    yield f"[!] Error for {ticker_symbol}: {e}\n"

            yield json.dumps({
                "status": "success",
                "data": results
            })

        return DynamicTool(
            name="fetch_stock_data",
            description="Fetch stock OHLC data with support for timeframe (1m, 15m, 1d), date ranges, durations, and specific dates.",
            triggers=["fetch stock", "get stock data", "ohlc data", "intraday data"],
            function=fetch_stock_data_tool,
            parameters=[
                ToolParam(name="tickers", type="list", required=True, description="List of stock tickers"),
                ToolParam(name="text", type="string", required=False, description="Text containing tickers"),
                ToolParam(name="from_date", type="string", required=False, description="Start date (YYYY-MM-DD)"),
                ToolParam(name="to_date", type="string", required=False, description="End date (YYYY-MM-DD)"),
                ToolParam(name="particular_dates", type="array", required=False, description="Specific dates list"),
                ToolParam(name="duration", type="string", required=False, description="Duration (e.g. 5d, 1mo, 2h)"),
                ToolParam(name="timeframe", type="string", required=False, description="Timeframe (1min, 15min, 1day)")
            ],
            endpoint="/fetch-stock-data",
            router=router
        )

    return func