from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from src.core.db import get_db_connection
import psycopg2
import yfinance as yf
from datetime import datetime, timedelta

router = APIRouter()

class StockBatchRequest(BaseModel):
    stock_ids: List[int]

def fetch_stock_record(cur, stock_id: int):
    # Helper to fetch a single stock record
    cur.execute(
        """
        SELECT stock_id, name, ticker, price, volume, percent_change, 
               close, high, open, low, date 
        FROM stock 
        WHERE stock_id = %s
        """,
        (stock_id,)
    )
    return cur.fetchone()

def map_stock_row(row):
    if not row:
        return None
    return {
        "stock_id": row[0],
        "name": row[1],
        "ticker": row[2],
        "price": row[3],
        "volume": row[4],
        "percent_change": row[5],
        "close": row[6],
        "high": row[7],
        "open": row[8],
        "low": row[9],
        "date": row[10]
    }

@router.get("/stock/details", status_code=status.HTTP_200_OK)
def get_live_stock_details(ticker: str):
    """
    Fetches live stock data for a given ticker symbol using yfinance.
    """
    try:
        clean_ticker = ticker.upper()
        if "." not in clean_ticker and not clean_ticker.startswith("^"):
            clean_ticker = f"{clean_ticker}.NS"
        
        stock = yf.Ticker(clean_ticker)
        # Using period="2d" ensures we can calculate percentage change accurately
        hist = stock.history(period="2d")
        
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data found for ticker: {ticker}")
        
        latest_day = hist.iloc[-1]
        info = stock.info
        
        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or latest_day['Close']
        open_price = latest_day['Open']
        high_price = latest_day['High']
        low_price = latest_day['Low']
        close_price = info.get("previousClose") or info.get("regularMarketPreviousClose")
        volume = latest_day['Volume']
        
        # Calculate percentage change if not in info
        percent_change = info.get("regularMarketChangePercent")
        if percent_change is None:
            if len(hist) > 1:
                prev_close = hist.iloc[-2]['Close']
                percent_change = ((current_price - prev_close) / prev_close) * 100
            else:
                percent_change = ((current_price - open_price) / open_price) * 100

        return {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "price": float(current_price),
            "open": float(open_price),
            "high": float(high_price),
            "low": float(low_price),
            "close": float(close_price) if close_price else float(latest_day['Close']),
            "volume": int(volume),
            "percent_change": float(percent_change)
        }
    except Exception as e:
        print(f"Error fetching live stock details for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stock/batch", status_code=status.HTTP_200_OK)
def get_stocks_batch(data: StockBatchRequest):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        stock_ids = tuple(data.stock_ids)
        if not stock_ids:
            return []
            
        cur.execute(
            """
            SELECT stock_id, name, ticker, price, volume, percent_change, 
                   close, high, open, low, date 
            FROM stock 
            WHERE stock_id IN %s
            """,
            (stock_ids,)
        )
        rows = cur.fetchall()
        
        results = [map_stock_row(row) for row in rows]
        return results

    except Exception as e:
        print(f"Error fetching batch stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.get("/stock/prev-day-details", status_code=status.HTTP_200_OK)
def get_prev_day_stock_details(ticker: str):
    """
    Fetches stock data for the previous trading day for a given ticker symbol.
    Skips Saturdays and Sundays as the market is closed.
    """
    try:
        clean_ticker = ticker.upper()
        if "." not in clean_ticker and not clean_ticker.startswith("^"):
            clean_ticker = f"{clean_ticker}.NS"
        
        stock = yf.Ticker(clean_ticker)
        # Fetch more days to ensure we have at least two previous trading days
        hist = stock.history(period="5d")
        
        if len(hist) < 2:
            raise HTTPException(status_code=404, detail=f"Insufficient historical data for ticker: {ticker}")
        
        # If market is currently open, hist[-1] is today. The "previous day" is hist[-2].
        # If market is closed (e.g., it's Sunday), hist[-1] is Friday (the last day the market was open).
        # The user wants "details of prev day". If today is Monday, they want Friday.
        # If today is Sunday, they want Friday? Or the day before Friday?
        # Usually, "prev day" means the last COMPLETED trading day before the most recent one.
        # However, if we are on a weekend, the "last trading day" is Friday. 
        # Let's assume they want the most recent COMPLETED trading session that is not "today".
        
        # To be safe, let's check the date of the last entry.
        last_trading_date = hist.index[-1].date()
        today = datetime.now().date()
        
        if last_trading_date == today:
            target_idx = -2
        else:
            target_idx = -1

        if abs(target_idx) > len(hist):
             raise HTTPException(status_code=404, detail="Not enough historical data to determine previous day.")

        prev_day = hist.iloc[target_idx]
        # We need the day before the target day to calculate percentage change
        if abs(target_idx - 1) <= len(hist):
            day_before_prev = hist.iloc[target_idx - 1]
            p_close = prev_day['Close']
            p_prev_close = day_before_prev['Close']
            percent_change = ((p_close - p_prev_close) / p_prev_close) * 100
        else:
            p_close = prev_day['Close']
            percent_change = ((p_close - prev_day['Open']) / prev_day['Open']) * 100

        return {
            "ticker": ticker.upper(),
            "date": hist.index[target_idx].strftime('%Y-%m-%d'),
            "price": float(p_close),
            "open": float(prev_day['Open']),
            "high": float(prev_day['High']),
            "low": float(prev_day['Low']),
            "close": float(p_close),
            "volume": int(prev_day['Volume']),
            "percent_change": float(percent_change)
        }
    except Exception as e:
        print(f"Error fetching previous day stock details for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stock/{stock_id}", status_code=status.HTTP_200_OK)
def get_stock_details(stock_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        row = fetch_stock_record(cur, stock_id)
        
        if not row:
            raise HTTPException(status_code=404, detail="Stock not found")
            
        return map_stock_row(row)

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error fetching stock {stock_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

