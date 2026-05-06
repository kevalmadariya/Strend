"""
Excel Agent WebSocket Controller
==================================
Single Responsibility: WebSocket lifecycle for Excel Agent sessions.
Handles connect, file upload, query loop, and cleanup.
All business logic is delegated to utils.
"""

import json
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from src.core.manager import ConnectionManager
from src.core.sqlite_manager import create_temp_db, get_connection, destroy_temp_db, has_session
from src.utils.excel_agent.excel_parser import parse_excel_json, parse_excel_bytes
from src.utils.excel_agent.schema_ops import (
    infer_column_types, create_table, bulk_insert, get_table_schema, get_all_tables
)
from src.agent.bot import PlanningAgent

router = APIRouter()
manager = ConnectionManager()

# Track agent sessions for cleanup
_excel_agent_sessions = {}


def _make_session_id(user_id: int, conversation_id: int) -> str:
    """Generate a unique session ID for a user's conversation."""
    return f"excel_{user_id}_{conversation_id}"


def _get_next_table_name(session_id: str) -> str:
    """
    Determine the next table name for multi-Excel support.
    First upload → 'excel_data', second → 'excel_data_2', etc.
    """
    try:
        conn = get_connection(session_id)
        tables = get_all_tables(conn)
        excel_tables = [t for t in tables if t.startswith("excel_data")]
        if not excel_tables:
            return "excel_data"
        return f"excel_data_{len(excel_tables) + 1}"
    except KeyError:
        return "excel_data"


async def _handle_file_upload(websocket: WebSocket, session_id: str, data: dict) -> None:
    """
    Handle file upload message — parse, create table, insert data.
    Supports multiple uploads (multi-Excel comparison).
    """
    try:
        # Parse Excel data (delegates to utils)
        file_format = data.get("format", "json")

        if file_format == "bytes":
            # Binary upload (base64 encoded)
            import base64
            file_bytes = base64.b64decode(data["file"])
            columns, rows = parse_excel_bytes(file_bytes)
        else:
            # JSON upload (default)
            columns, rows = parse_excel_json(data)

        if not rows:
            await websocket.send_text(json.dumps({
                "status": "error",
                "error": "No data rows found in uploaded file"
            }))
            return

        # Infer schema and create table (delegates to utils)
        schema = infer_column_types(rows[:2])
        conn = get_connection(session_id)
        table_name = _get_next_table_name(session_id)
        create_table(conn, table_name, schema)
        count = bulk_insert(conn, table_name, rows)

        # Respond with schema summary
        await websocket.send_text(json.dumps({
            "status": "ready",
            "table": table_name,
            "columns": columns,
            "column_types": schema,
            "rows_loaded": count,
            "message": f"✅ Loaded {count} rows into '{table_name}' with {len(columns)} columns"
        }))

        print(f"[+] Excel loaded: {table_name} ({count} rows, {len(columns)} cols)")

    except Exception as e:
        await websocket.send_text(json.dumps({
            "status": "error",
            "error": f"Failed to process file: {str(e)}"
        }))
        print(f"[!] File upload error: {e}")


async def _handle_query(websocket: WebSocket, session_id: str, user_message: str) -> None:
    """
    Handle a query message — route through PlanningAgent.
    """
    if session_id not in _excel_agent_sessions:
        _excel_agent_sessions[session_id] = PlanningAgent(
            agent_name="excel_agent",
            unique_id=session_id
        )

    agent = _excel_agent_sessions[session_id]

    try:
        response = await agent.run(user_message)
        await websocket.send_text(response if isinstance(response, str) else json.dumps(response))
    except Exception as e:
        await websocket.send_text(json.dumps({
            "status": "error",
            "error": f"Agent error: {str(e)}"
        }))
        print(f"[!] Agent error: {e}")


@router.websocket("/ws/excel/{user_id}/{conversation_id}")
async def excel_websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    conversation_id: int,
):
    """
    WebSocket endpoint for Excel Agent.
    
    Lifecycle:
    1. On Connect → Create temp SQLite DB
    2. First message(s) → {"file": "...", "format": "json|bytes"} → parse & load
    3. Subsequent → {"query": "..."} → route through agent → return results
    4. On Disconnect → Destroy temp DB + cleanup agent session
    """
    session_id = _make_session_id(user_id, conversation_id)

    # ── CONNECT ──
    await manager.connect(websocket)
    create_temp_db(session_id)
    print(f"[*] Excel Agent: User #{user_id} connected (session: {session_id})")

    try:
        while True:
            # Receive message
            raw_message = await websocket.receive_text()

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                # If not JSON, treat as plain text query
                message = {"query": raw_message}

            # ── FILE UPLOAD ──
            if "file" in message:
                await _handle_file_upload(websocket, session_id, message)

            # ── QUERY ──
            elif "query" in message:
                await _handle_query(websocket, session_id, message["query"])

            # ── UNKNOWN ──
            else:
                await websocket.send_text(json.dumps({
                    "status": "error",
                    "error": "Unknown message format. Send {'file': '...'} or {'query': '...'}"
                }))

    except WebSocketDisconnect:
        # ── CLEANUP ──
        manager.disconnect(websocket)
        destroy_temp_db(session_id)
        _excel_agent_sessions.pop(session_id, None)
        print(f"[*] Excel Agent: User #{user_id} disconnected. DB cleaned up.")
