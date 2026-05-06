import yfinance as yf
import pandas_ta as ta
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Optional
import json

# Try importing talib
# try:
#     import talib
#     HAVE_TALIB = True
# except ImportError:
#     HAVE_TALIB = False
#     print("⚠️ TA-Lib not found. Chart patterns will be disabled.")

def normalize_ticker(ticker: str) -> str:
    """Normalize ticker to Yahoo Finance format (NSE)."""
    if "." not in ticker:
        return f"{ticker}.NS"
    return ticker

def calculate_trend(ticker: str, start_date: date, end_date: date) -> int:
    """Calculate trend using SMA 20/50 crossover."""
    print(f"📊 Fetching trend for {ticker}")
    ticker_ns = normalize_ticker(ticker)
    
    try:
        data = yf.download(ticker_ns, start=start_date, end=end_date, progress=False)

        if data.empty:
            print(f"⚠️ No data available for {ticker}. Returning Neutral=0.")
            return 0

        # Flatten MultiIndex safely
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = ['_'.join(col).strip() if col[1] else col[0] for col in data.columns.values]

        # Find close column dynamically
        close_col = next((c for c in data.columns if c.startswith('Close')), None)
        if not close_col:
            print(f"⚠️ Missing close column for {ticker}.")
            return 0

        # Moving averages
        data['SMA_20'] = ta.sma(data[close_col], length=20)
        data['SMA_50'] = ta.sma(data[close_col], length=50)

        data.dropna(subset=['SMA_20', 'SMA_50'], inplace=True)

        if data.empty:
            print(f"⚠️ Not enough data for SMAs for {ticker}.")
            return 0

        bullish = data['SMA_20'].iloc[-1] > data['SMA_50'].iloc[-1]
        trend = 1 if bullish else 0
        print(f"➡️ Trend for {ticker}: {'Bullish (1)' if bullish else 'Bearish (0)'}")
        return trend
        
    except Exception as e:
        print(f"❌ Error calculating trend for {ticker}: {e}")
        return 0

# def calculate_chart_patterns(ticker: str, start_date: date, end_date: date) -> Optional[str]:
#     """Calculate recent chart patterns using TA-Lib."""
#     if not HAVE_TALIB:
#         return "TA-Lib not installed"

#     print(f"📉 Fetching candlestick patterns for {ticker}")
#     ticker_ns = normalize_ticker(ticker)

#     try:
#         data = yf.download(ticker_ns, start=start_date, end=end_date, progress=False)

#         if data.empty:
#             return None

#         # Flatten MultiIndex safely
#         if isinstance(data.columns, pd.MultiIndex):
#             data.columns = ['_'.join(col).strip() if col[1] else col[0] for col in data.columns.values]

#         # Identify columns
#         open_col = next((c for c in data.columns if c.startswith('Open')), None)
#         high_col = next((c for c in data.columns if c.startswith('High')), None)
#         low_col = next((c for c in data.columns if c.startswith('Low')), None)
#         close_col = next((c for c in data.columns if c.startswith('Close')), None)

#         if not all([open_col, high_col, low_col, close_col]):
#             print(f"⚠️ Missing OHLC columns for {ticker}.")
#             return None

#         # Apply TA-LIB patterns
#         patterns_found = []
        
#         # Define pattern functions map for easier iteration/extension
#         pattern_funcs = {
#             'Bullish Engulfing': talib.CDLENGULFING,
#             'Morning Star': talib.CDLMORNINGSTAR,
#             '3 White Soldiers': talib.CDL3WHITESOLDIERS,
#             'Evening Star': talib.CDLEVENINGSTAR,
#             '3 Black Crows': talib.CDL3BLACKCROWS
#         }

#         any_pattern_detected = False
#         detected_patterns = []

#         for name, func in pattern_funcs.items():
#             res = func(data[open_col], data[high_col], data[low_col], data[close_col])
#             if res.iloc[-1] != 0:
#                 detected_patterns.append(name)
        
#         if not detected_patterns:
#             return None
            
#         return ", ".join(detected_patterns)

#     except Exception as e:
#         print(f"❌ Error calculating patterns for {ticker}: {e}")
#         return None

def calculate_indicators(ticker: str, start_date: date, end_date: date) -> Dict:
    """Calculate MACD, RSI, ADX."""
    print(f"📈 Fetching indicators for {ticker}")
    ticker_ns = normalize_ticker(ticker)
    
    indicators = {
        "macd": 0.0, "macd_signal": 0.0, "macd_hist": 0.0,
        "rsi": 0.0, "adx": 0.0
    }

    try:
        data = yf.download(ticker_ns, start=start_date, end=end_date, progress=False)
        if data.empty: return indicators

        # Flatten MultiIndex safely
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = ['_'.join(col).strip() if col[1] else col[0] for col in data.columns.values]

        close_col = next((c for c in data.columns if c.startswith('Close')), None)
        high_col = next((c for c in data.columns if c.startswith('High')), None)
        low_col = next((c for c in data.columns if c.startswith('Low')), None)
        
        if not all([close_col, high_col, low_col]): return indicators

        # MACD
        macd = ta.macd(data[close_col])
        if macd is not None and not macd.empty:
            indicators["macd"] = macd.iloc[-1, 0] # MACD_12_26_9
            indicators["macd_hist"] = macd.iloc[-1, 1] # MACDh_12_26_9
            indicators["macd_signal"] = macd.iloc[-1, 2] # MACDs_12_26_9

        # RSI
        rsi = ta.rsi(data[close_col], length=14)
        if rsi is not None and not rsi.empty:
            indicators["rsi"] = rsi.iloc[-1]

        # ADX
        adx = ta.adx(data[high_col], data[low_col], data[close_col], length=14)
        if adx is not None and not adx.empty:
            indicators["adx"] = adx.iloc[-1, 0] # ADX_14

        return indicators

    except Exception as e:
        print(f"❌ Error calculating indicators for {ticker}: {e}")
        return indicators

def calculate_roc(ticker: str, period: int = 12, interval: str = "5m") -> float:
    """
    Calculate Rate of Change (ROC) for a given ticker.
    ROC = ((Current Close - Close n periods ago) / Close n periods ago) * 100
    """
    print(f"📈 Calculating ROC for {ticker} (interval={interval}, period={period})")
    ticker_ns = normalize_ticker(ticker)
    
    try:
        # For 5m interval, we usually need just a few days of data
        # Fetching '5d' to be safe for a '12' period ROC on '5m' data
        data = yf.download(ticker_ns, period="5d", interval=interval, progress=False)
        
        if data.empty:
            return 0.0

        # Flatten MultiIndex safely
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = ['_'.join(col).strip() if col[1] else col[0] for col in data.columns.values]

        close_col = next((c for c in data.columns if c.startswith('Close')), None)
        if not close_col:
            return 0.0

        # pandas_ta roc
        roc_series = ta.roc(data[close_col], length=period)
        
        if roc_series is not None and not roc_series.empty:
            return float(roc_series.iloc[-1])
        
        return 0.0

    except Exception as e:
        print(f"❌ Error calculating ROC for {ticker}: {e}")
        return 0.0
