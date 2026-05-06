"""
Global Notification Manager for broadcasting strategy alerts to connected frontend clients.
Uses WebSocket connections to push real-time notifications.
"""

import json
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger("notification_manager")


class NotificationManager:
    """
    Singleton-style notification manager.
    Frontend clients connect via /ws/notifications and receive strategy alerts.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register a new notification client."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔔 Notification client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected client."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"🔕 Notification client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a JSON message to all connected notification clients."""
        if not self.active_connections:
            logger.info("📭 No notification clients connected, skipping broadcast.")
            return

        payload = json.dumps(message, default=str)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"⚠️ Failed to send notification to a client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

        active_count = len(self.active_connections)
        logger.info(f"📤 Broadcast sent to {active_count} client(s)")

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a message to a specific client."""
        try:
            payload = json.dumps(message, default=str)
            await websocket.send_text(payload)
        except Exception as e:
            logger.warning(f"⚠️ Failed to send to specific client: {e}")
            self.disconnect(websocket)


# Global singleton instance — imported by scheduler and controller
notification_manager = NotificationManager()
