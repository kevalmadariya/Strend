from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from src.core.db import get_db_connection
from src.tools.utils.get_yfinance_data import get_yfinance_data
from datetime import date
import psycopg2

router = APIRouter()

class CreateWatchlistRequest(BaseModel):
    user_id: int
    name: str
    description: Optional[str] = None

class AddStockToWatchlistRequest(BaseModel):
    watchlist_id: int
    stock_ticker: str

@router.post("/watchlist", status_code=status.HTTP_201_CREATED)
def create_watchlist(data: CreateWatchlistRequest):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        # Insert into watchlist
        cur.execute(
            """
            INSERT INTO watchlist (user_id, name, description, date)
            VALUES (%s, %s, %s, %s)
            RETURNING watchlist_id, user_id, name, description, date
            """,
            (data.user_id, data.name, data.description, date.today())
        )
        
        new_watchlist = cur.fetchone()
        conn.commit()
        
        return {
            "watchlist_id": new_watchlist[0],
            "user_id": new_watchlist[1],
            "name": new_watchlist[2],
            "description": new_watchlist[3],
            "date": new_watchlist[4]
        }
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@router.get("/watchlist/user/{user_id}", status_code=status.HTTP_200_OK)
def get_watchlists_by_user(user_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT watchlist_id, user_id, name, description, date 
            FROM watchlist 
            WHERE user_id = %s
            ORDER BY watchlist_id DESC
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "watchlist_id": row[0],
                "user_id": row[1],
                "name": row[2],
                "description": row[3],
                "date": row[4]
            })
            
        return results

    except Exception as e:
        print(f"Error fetching watchlists for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.post("/watchlist/add_stock", status_code=status.HTTP_201_CREATED)
def add_stock_to_watchlist(data: AddStockToWatchlistRequest):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        # 1. Check if stock exists in DB for today
        # Note: get_yfinance_data normalizes ticker (e.g. adds .NS). 
        # We should probably adhere to that or check both?
        # get_yfinance_data logic: if "." not in ticker: return f"{ticker}.NS"
        # Since I'm using get_yfinance_data to fill the gap, I should probably rely on it or mimic its normalization if checking strictly.
        # But if the user passes "RELIANCE", get_yfinance will save "RELIANCE.NS".
        # So if I check "RELIANCE" in DB, I might miss "RELIANCE.NS".
        # Let's try to query with wildcard or just call get_yfinance_data if not strict match.
        # Actually, let's normalize it here to be safe and match get_yfinance_data behavior.
        
        normalized_ticker = data.stock_ticker
        if "." not in normalized_ticker:
            normalized_ticker = f"{normalized_ticker}.NS"
            
        cur.execute(
            "SELECT stock_id, price FROM stock WHERE ticker = %s AND date = %s",
            (normalized_ticker, date.today())
        )
        stock_record = cur.fetchone()
        
        stock_id = None
        price = None
        
        if stock_record:
            stock_id = stock_record[0]
            price = stock_record[1]
        else:
            # Not found, fetch from yfinance
            print(f"Stock {normalized_ticker} not in DB today. Fetching via yfinance...")
            # We must close cursor/conn here ?? No, get_yfinance_data makes its own connection. 
            # It should be fine as long as we don't lock tables in a way that blocks.
            # But get_yfinance_data uses the same DB.
            
            result = get_yfinance_data(data.stock_ticker) # pass original, it handles normalization
            
            if not result or result.get('status') != 'completed':
                raise HTTPException(status_code=404, detail=f"Stock {data.stock_ticker} could not be fetched")
                
            # Now query again
            # The result['results']['ticker'] should be the normalized one (without .NS?? or with?)
            # create_params in get_yfinance_data: "ticker": only_ticker (split(".")[0])
            # WAIT. 
            # In get_yfinance_data.py:
            # ticker_symbol = normalize_ticker(ticker_symbol) -> e.g. RELIANCE.NS
            # only_ticker = ticker_symbol.split(".")[0] -> RELIANCE
            # stock_data = { ... "ticker": only_ticker ... }
            # INSERT INTO stock (..., ticker, ...) VALUES (..., stock_data["ticker"], ...)
            # So it saves "RELIANCE" (without .NS) in the ticker column??
            # Let's re-read get_yfinance_data.py line 13 and 41.
            # Line 13: `only_ticker = ticker_symbol.split(".")[0]`
            # Line 41: `"ticker": only_ticker`
            # Line 95: `stock_data["ticker"]` is inserted.
            # So YES, it saves the ticker WITHOUT the suffix.
            
            # So my check above `normalized_ticker = f"{normalized_ticker}.NS"` and querying that might be WRONG if the DB stores it without suffix.
            # But line 5 of get_yfinance_data says: `if "." not in ticker: return f"{ticker}.NS"`.
            # That's for yfinance API call.
            # But the DB store is line 95: `only_ticker`.
            
            # So I should query for the ticker WITHOUT .NS or whatever `only_ticker` logic is.
            # Let's adjust logic:
            
            ticker_to_search = data.stock_ticker.split(".")[0]
            
            # Re-query with just the prefix
            cur.execute(
                "SELECT stock_id, price FROM stock WHERE ticker = %s AND date = %s",
                (ticker_to_search, date.today())
            )
            stock_record = cur.fetchone()

            if not stock_record:
                 # Try fetching
                 result = get_yfinance_data(data.stock_ticker)
                 if not result or result.get('status') != 'completed':
                     raise HTTPException(status_code=404, detail="Stock fetch failed")
                 
                 # The result contains the ticker used for insertion
                 inserted_ticker = result['results']['ticker']
                 
                 cur.execute(
                    "SELECT stock_id, price FROM stock WHERE ticker = %s AND date = %s",
                    (inserted_ticker, date.today())
                 )
                 stock_record = cur.fetchone()
                 if not stock_record:
                     raise HTTPException(status_code=500, detail="Stock saved but not found?")
            
            stock_id = stock_record[0]
            price = stock_record[1]

        # 2. Insert into watchlist_stocks
        try:
            cur.execute(
                """
                INSERT INTO watchlist_stocks (watchlist_id, stock_id, price_of_stock_when_added, date)
                VALUES (%s, %s, %s, %s)
                RETURNING watchlist_id, stock_id, price_of_stock_when_added
                """,
                (data.watchlist_id, stock_id, price, date.today())
            )
            inserted = cur.fetchone()
            
            # Fetch details for return
            cur.execute("SELECT name, ticker, percent_change FROM stock WHERE stock_id = %s", (stock_id,))
            stock_info = cur.fetchone()
            
            live_data_results = []
            if stock_info:
                live_data_results.append({
                    "stock_id": inserted[1],
                    "ticker": stock_info[1],
                    "name": stock_info[0],
                    "price": inserted[2],
                    "percent_change": stock_info[2],
                    "price_of_stock_when_added": inserted[2],
                    "date": date.today()
                })

            conn.commit()
            
            return {
                "message": "Stock added successfully",
                "watchlist_id": inserted[0],
                "stock_id": inserted[1],
                "price_of_stock_when_added": inserted[2],
                "live_data_results": live_data_results
            }
             
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Stock already in this watchlist")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur: cur.close()
        if conn: conn.close()

@router.get("/watchlist/{watchlist_id}/stocks", status_code=status.HTTP_200_OK)
def get_watchlist_stocks_live(watchlist_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        # 1. Get stock_id, ticker, price_when_added, and date associated with this watchlist
        cur.execute(
            """
            SELECT s.stock_id, s.ticker, ws.price_of_stock_when_added, ws.date
            FROM watchlist_stocks ws
            JOIN stock s ON ws.stock_id = s.stock_id
            WHERE ws.watchlist_id = %s
            """,
            (watchlist_id,)
        )
        rows = cur.fetchall()
        
        if not rows:
            return []
        
        live_data_results = []
        
        # 2. Fetch fresh data for each ticker from yfinance and merge
        for row in rows:
            stock_id = row[0]
            ticker = row[1]
            price_added = row[2]
            date_added = row[3]
            
            try:
                # print(f"Fetching live data for {ticker}...")
                result = get_yfinance_data(ticker)
                
                if result and result.get("status") == "completed":
                    data = result["results"]
                    # Merge specific fields
                    live_data_results.append({
                        "stock_id": stock_id,
                        "ticker": ticker,
                        "name": data.get("name"),
                        "price": data.get("price"),
                        "percent_change": data.get("percent_change"),
                        "price_of_stock_when_added": price_added,
                        "date": date_added
                    })
                else:
                    print(f"Failed to fetch live data for {ticker}. Skipping.")
                    # Optionally handle partial failures?
            except Exception as e:
                print(f"Error calling yfinance for {ticker}: {e}")
        
        return live_data_results

    except Exception as e:
        print(f"Error fetching watchlist stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.delete("/watchlist/{watchlist_id}", status_code=status.HTTP_200_OK)
def delete_watchlist(watchlist_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        # Check if watchlist exists
        cur.execute("SELECT 1 FROM watchlist WHERE watchlist_id = %s", (watchlist_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Watchlist not found")

        # 1. Delete associated stocks in watchlist_stocks
        cur.execute("DELETE FROM watchlist_stocks WHERE watchlist_id = %s", (watchlist_id,))
        
        # 2. Delete the watchlist itself
        cur.execute("DELETE FROM watchlist WHERE watchlist_id = %s", (watchlist_id,))
        
        conn.commit()
        return {"message": "Watchlist deleted successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error deleting watchlist {watchlist_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.delete("/watchlist/{watchlist_id}/stock/{stock_id}", status_code=status.HTTP_200_OK)
def remove_stock_from_watchlist(watchlist_id: int, stock_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cur = conn.cursor()
        
        cur.execute(
            """
            DELETE FROM watchlist_stocks 
            WHERE watchlist_id = %s AND stock_id = %s 
            RETURNING stock_id
            """,
            (watchlist_id, stock_id)
        )
        deleted = cur.fetchone()
        conn.commit()
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Stock not found in this watchlist")
            
        return {"message": "Stock removed from watchlist successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error removing stock {stock_id} from watchlist {watchlist_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

