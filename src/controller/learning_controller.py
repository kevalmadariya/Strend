from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date
from src.core.db import get_db_connection
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/learning", tags=["Learning"])

class LearningCreate(BaseModel):
    user_id: int
    date: date
    learning: str
    exceptions: Optional[str] = None
    sentiment: int  # 1 for good, 0 for bad
    event: Optional[str] = None

@router.post("/create")
def create_learning(data: LearningCreate):
    conn = get_db_connection()
    try:
        print(f"DEBUG: Attempting to insert learning: {data}")
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learnings (user_id, date, learning, exceptions, sentiment, event)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING learning_id
                """,
                (data.user_id, data.date, data.learning, data.exceptions, data.sentiment, data.event)
            )
            learning_id = cur.fetchone()[0]
            conn.commit()
            print(f"DEBUG: Inserted learning with ID: {learning_id}")
            return {"message": "Learning inserted successfully", "learning_id": learning_id}
    except Exception as e:
        conn.rollback()
        print(f"ERROR: Failed to insert learning: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/get")
def get_learnings(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sentiment: Optional[int] = Query(None, description="1 for good, 0 for bad"),
    is_exception: Optional[bool] = Query(None, description="Filter by existence of exceptions")
):
    conn = get_db_connection()
    try:
        print(f"DEBUG: Fetching learnings with filters - start_date: {start_date}, end_date: {end_date}, sentiment: {sentiment}, is_exception: {is_exception}")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM learnings WHERE 1=1"
            params = []

            if start_date:
                query += " AND date >= %s"
                params.append(start_date)
            
            if end_date:
                query += " AND date <= %s"
                params.append(end_date)
            
            if sentiment is not None:
                query += " AND sentiment = %s"
                params.append(sentiment)
            
            if is_exception is not None:
                if is_exception:
                    query += " AND (exceptions IS NOT NULL AND exceptions != '')"
                else:
                    query += " AND (exceptions IS NULL OR exceptions = '')"

            query += " ORDER BY date DESC"
            
            print(f"DEBUG: Executing query: {query} with params: {params}")
            cur.execute(query, tuple(params))
            learnings = cur.fetchall()
            print(f"DEBUG: Found {len(learnings)} learnings")
            return learnings
    except Exception as e:
        print(f"ERROR: Failed to fetch learnings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
