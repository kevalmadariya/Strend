"""
WebSocket endpoint for frontend clients to receive strategy alert notifications.
Clients connect to /ws/notifications and receive real-time push alerts 
whenever the strategy scheduler finds stocks with recent news.
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.core.notification_manager import notification_manager

logger = logging.getLogger("notification_controller")

router = APIRouter()


@router.websocket("/ws/notifications")
async def notification_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for receiving strategy alert notifications.
    
    Frontend connects here and listens for messages of the form:
    {
        "type": "strategy_alert",
        "stock_name": "...",
        "ticker": "...",
        "price": 123.45,
        "volume": 500000,
        "news": [{"headline": "...", "time": "...", "url": "..."}],
        "schedule_slot": "slot_1_0934",
        "timestamp": "2026-04-03T09:34:00"
    }
    """
    await notification_manager.connect(websocket)

    try:
        while True:
            # Keep connection alive — client only receives, but we read to detect disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        notification_manager.disconnect(websocket)
        logger.info("Notification client disconnected gracefully.")
    except Exception as e:
        logger.error(f"Notification WebSocket error: {e}")
        notification_manager.disconnect(websocket)
