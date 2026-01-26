from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List
from src.core.db import get_db_connection
import psycopg2

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
