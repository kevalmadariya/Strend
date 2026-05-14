from fastapi import WebSocket, WebSocketDisconnect
from src.core.manager import ConnectionManager
from .invoke_agent import invoke_agent, cleanup_agent_session, initialize_agent_session
from src.database.agent import find_agent_by_name
from src.database.conversation import find_conversation_by_id
from src.database.user import find_user_by_id
from fastapi import APIRouter
import json
from src.core.security import verify_token
from fastapi import HTTPException
from src.controller.conversation_controller import save_conversation_message, MessageCreate

router = APIRouter()
manager = ConnectionManager()


def _auto_load_excel_data(conversation_id: str, json_data_str: str) -> str:
    """
    Auto-load Excel JSON data into the temp database when the frontend
    sends it alongside a chat message. Returns a status summary string.
    """
    from src.core.sqlite_manager import has_session, create_temp_db, get_connection
    from src.utils.excel_agent.excel_parser import parse_excel_json
    from src.utils.excel_agent.schema_ops import (
        infer_column_types, create_table, bulk_insert, get_all_tables
    )

    try:
        data = json.loads(json_data_str) if isinstance(json_data_str, str) else json_data_str
        columns, rows = parse_excel_json(data)
        schema = infer_column_types(rows[:2])

        if not has_session(conversation_id):
            create_temp_db(conversation_id)
        conn = get_connection(conversation_id)

        tables = get_all_tables(conn)
        excel_tables = [t for t in tables if t.startswith("excel_data")]
        table_name = "excel_data" if not excel_tables else f"excel_data_{len(excel_tables) + 1}"

        create_table(conn, table_name, schema)
        count = bulk_insert(conn, table_name, rows)

        col_list = ", ".join(columns)
        return (
            f"[DATA ALREADY LOADED] {count} rows loaded into table '{table_name}'. "
            f"Columns: {col_list}. "
            f"You can now query this data directly using execute_query or add_computed_column tools. "
            f"Do NOT call make_temp_database — data is already in the database."
        )
    except Exception as e:
        return f"[DATA LOAD FAILED] Could not auto-load Excel data: {e}"


@router.websocket("/ws/{user_id}/{agent_name}/{module}/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    agent_name: str,
    module: str,
    conversation_id: str,
    token: str = None
):
    print("Client connected")
    
    # Verify JWT Token
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return
        
    try:
        verify_token(token)
    except HTTPException as e:
        await websocket.close(code=1008, reason="Invalid authentication token")
        return
    except Exception as e:
        await websocket.close(code=1008, reason="Token verification failed")
        return

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------
    user = find_user_by_id(user_id)
    print(user)
    if not user:
        await websocket.close(code=1008)
        return

    agent = find_agent_by_name(agent_name)
    print(agent)
    if not agent:
        await websocket.close(code=1008)
        return

    conversation = find_conversation_by_id(conversation_id)
    print(conversation)
    if not conversation:
        await websocket.close(code=1008)
        return

    # ------------------------------------------------------------------
    # CONNECT
    # ------------------------------------------------------------------
    await manager.connect(websocket)
    print(f"Client #{user_id} connected to agent {agent_name}")

    # Initialize Agent Immediately on Connection
    initialize_agent_session(user_id, agent_name, conversation_id)
    
    try:
        while True:
            # Receive user message
            user_message = await websocket.receive_text()
            user_message_json = json.loads(user_message)

            save_conversation_message(MessageCreate(conversation_id=conversation_id, sender_type="user", content=user_message_json["text"]))

            # ----------------------------------------------------------
            # AUTO-LOAD EXCEL DATA if json_data is present
            # ----------------------------------------------------------
            data_context = ""
            json_data = user_message_json.get("json_data")
            if json_data:
                data_context = _auto_load_excel_data(conversation_id, json_data)
                print(f"[+] Auto-loaded Excel data for conversation {conversation_id}")

            # Build the message for the agent: user text + data context
            agent_input = user_message_json["text"]
            if data_context:
                agent_input = f"{agent_input}\n\n{data_context}"

            # Invoke agent
            full_content = ""

            async for chunk in invoke_agent(
                user_id=user_id,
                agent_name=agent_name,
                conversation_id=conversation_id,
                user_message=agent_input
            ):
                # Send response back ONLY to this client
                content_piece = str(chunk)
                full_content += content_piece
                await websocket.send_text(content_piece)
            save_conversation_message(MessageCreate(conversation_id=conversation_id, sender_type="agent", content=full_content))

            # ----------------------------------------------------------
            # SEND UPDATED TABLE DATA back to frontend if DB exists
            # ----------------------------------------------------------
            from src.core.sqlite_manager import has_session as _has_session, get_connection as _get_conn
            if _has_session(conversation_id):
                try:
                    _conn = _get_conn(conversation_id)
                    from src.utils.excel_agent.schema_ops import get_all_tables, get_row_count
                    _tables = get_all_tables(_conn)
                    if _tables:
                        table_name = _tables[0]
                        # Limit to 500 rows for performance
                        _MAX_TABLE_ROWS = 500
                        total_rows = get_row_count(_conn, table_name)
                        cursor = _conn.execute(f'SELECT * FROM "{table_name}" LIMIT {_MAX_TABLE_ROWS}')
                        columns = [desc[0] for desc in cursor.description]
                        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                        await websocket.send_text(json.dumps({
                            "status": "success",
                            "type": "table_data",
                            "table": table_name,
                            "columns": columns,
                            "data": rows,
                            "row_count": len(rows),
                            "total_rows": total_rows,
                            "truncated": total_rows > _MAX_TABLE_ROWS,
                        }, default=str, ensure_ascii=False))
                        print(f"[+] Sent table data ({len(rows)}/{total_rows} rows, {len(columns)} cols) to frontend")
                except Exception as e:
                    print(f"[!] Failed to send table data: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # Clean up temp DB on disconnect
        from src.core.sqlite_manager import has_session, destroy_temp_db
        if has_session(conversation_id):
            destroy_temp_db(conversation_id)
        cleanup_agent_session(user_id, agent_name, conversation_id)
        print(f"Client #{user_id} disconnected")

