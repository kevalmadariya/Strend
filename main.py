def main():
    print("Hello from strend!")

from datetime import date
from src.database.generic import insert_one
from fastapi import FastAPI, WebSocket, WebSocketDisconnect,APIRouter
from typing import List
from src.controller.agent_ws import router
from src.core.manager import ConnectionManager

app = FastAPI()
manager = ConnectionManager()


# @app.websocket("/ws/{user_id}/{agent_name}/{module}/{conversation_id}")
# async def websocket_endpoint(websocket: WebSocket, user_id: int, agent_name: str, module: str, conversation_id: int):
#     print(f"Client #{user_id} connected")
#     await manager.connect(websocket)
#     try:
#         while True:
#             # Wait for message from client
#             data = await websocket.receive_text()
            
#             # Broadcast message to everyone
#             await manager.broadcast(f"Client #{user_id} says: {data}")
            
#     except WebSocketDisconnect:
#         manager.disconnect(websocket)
#         await manager.broadcast(f"Client #{user_id} left the chat")
        
@app.get("/add_database")
def add_database():
    user_id = insert_one(
        table='"user"',   # quoted because it's reserved
        data={
            "name": "John Doe",
            "email_id": "john@example.com"
        },
        returning="user_id"
    )
    agent_id = insert_one(
        table="agent",
        data={
            "template": "trading_bot",
            "user_id": user_id
        },
        returning="agent_id"
    )
    conversation_id = insert_one(
        table="conversation",
        data={
            "agent_id": agent_id,
            "title": "Market discussion",
            "user_id": user_id,
            "date": date.today()
        },
        returning="conversation_id"
    )
    print("Inserted conversation_id:", conversation_id)
    print("Inserted agent_id:", agent_id)
    print("Inserted user_id:", user_id)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
