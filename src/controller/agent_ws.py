from fastapi import WebSocket, WebSocketDisconnect
from src.core.manager import ConnectionManager
from .invoke_agent import invoke_agent, cleanup_agent_session
from src.database.agent import find_agent_by_name
from src.database.conversation import find_conversation_by_id
from src.database.user import find_user_by_id
from fastapi import APIRouter
import json

router = APIRouter()
manager = ConnectionManager()


@router.websocket("/ws/{user_id}/{agent_name}/{module}/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    agent_name: str,
    module: str,
    conversation_id: int
):
    print("Client connected")
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

    try:
        while True:
            # Receive user message
            user_message = await websocket.receive_text()

            # 🔥 Invoke agent
            agent_response =await invoke_agent(
                user_id=user_id,
                agent_name=agent_name,
                conversation_id=conversation_id,
                user_message=user_message
            )

            # Send response back ONLY to this client
            # await websocket.send_text(agent_response)
            await websocket.send_text(json.dumps(agent_response, default=str))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        cleanup_agent_session(user_id, agent_name, conversation_id)
        print(f"Client #{user_id} disconnected")
