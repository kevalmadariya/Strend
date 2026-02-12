from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import date as dt_date
from src.core.db import get_db_connection
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/conversation", tags=["Conversation"])

class ConversationCreate(BaseModel):
    agent_id: int
    title: str
    user_id: int
    date: Optional[dt_date] = None
    conversation_id: Optional[str | int] = None

class MessageCreate(BaseModel):
    conversation_id: int | str
    sender_type: str
    content: str

@router.post("/create")
def create_conversation(data: ConversationCreate):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Handle manual conversation_id insertion if provided
            if data.conversation_id:
                # Need to convert to string if it's an int, as DB expects TEXT
                cid = str(data.conversation_id)
                if data.date:
                    cur.execute(
                        """
                        INSERT INTO conversation (conversation_id, agent_id, title, user_id, date)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING conversation_id
                        """,
                        (cid, data.agent_id, data.title, data.user_id, data.date)
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO conversation (conversation_id, agent_id, title, user_id)
                        VALUES (%s, %s, %s, %s)
                        RETURNING conversation_id
                        """,
                        (cid, data.agent_id, data.title, data.user_id)
                    )
            else:
                if data.date:
                    cur.execute(
                        """
                        INSERT INTO conversation (agent_id, title, user_id, date)
                        VALUES (%s, %s, %s, %s)
                        RETURNING conversation_id
                        """,
                        (data.agent_id, data.title, data.user_id, data.date)
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO conversation (agent_id, title, user_id)
                        VALUES (%s, %s, %s)
                        RETURNING conversation_id
                        """,
                        (data.agent_id, data.title, data.user_id)
                    )
            
            conversation_id = cur.fetchone()[0]
            conn.commit()
            return {"conversation_id": conversation_id, "message": "Conversation created successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/message/save")
def save_conversation_message(data: MessageCreate):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_message (conversation_id, sender_type, content)
                VALUES (%s, %s, %s)
                RETURNING message_id
                """,
                (data.conversation_id, data.sender_type, data.content)
            )
            message_id = cur.fetchone()[0]
            conn.commit()
            return {"message": "Message saved successfully", "message_id": message_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/user/{user_id}")
def get_conversations_by_user(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM conversation WHERE user_id = %s ORDER BY date DESC, conversation_id DESC",
                (user_id,)
            )
            conversations = cur.fetchall()
            return conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/messages/{conversation_id}")
def get_messages_by_conversation(conversation_id: str):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM conversation_message WHERE conversation_id = %s ORDER BY created_at ASC",
                (conversation_id,)
            )
            messages = cur.fetchall()
            return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

class ConversationUpdate(BaseModel):
    conversation_id: int | str
    title: str

@router.put("/update")
def update_conversation(data: ConversationUpdate):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if conversation exists
            cur.execute("SELECT conversation_id FROM conversation WHERE conversation_id = %s", (data.conversation_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Conversation not found")

            cur.execute(
                """
                UPDATE conversation
                SET title = %s
                WHERE conversation_id = %s
                RETURNING conversation_id, title
                """,
                (data.title, data.conversation_id)
            )
            updated_conversation = cur.fetchone()
            conn.commit()
            return {"message": "Conversation updated successfully", "conversation_id": updated_conversation[0], "title": updated_conversation[1]}
    except HTTPException as e:
        raise e
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/delete/{conversation_id}")
def delete_conversation(conversation_id: str | int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if conversation exists
            cur.execute("SELECT conversation_id FROM conversation WHERE conversation_id = %s", (conversation_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            # Delete associated messages first to satisfy foreign key constraints (or rely on CASCADE which we added)
            # We can skip explicit delete since ON DELETE CASCADE is set, but updating table ref just in case logic changes
            # cur.execute("DELETE FROM conversation_message WHERE conversation_id = %s", (conversation_id,))
            
            # Delete the conversation (Cascade will handle messages)
            cur.execute("DELETE FROM conversation WHERE conversation_id = %s", (conversation_id,))
            
            conn.commit()
            return {"message": "Conversation and associated messages deleted successfully", "conversation_id": conversation_id}
    except HTTPException as e:
        raise e
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
