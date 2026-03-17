"""WebSocket connection manager."""

from typing import List, Dict, Any
from fastapi import WebSocket


class WebSocketManager:
    """Manages WebSocket connections and broadcasts."""
    
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self.subscriptions: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from all registries."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        for topic in list(self.subscriptions.keys()):
            if websocket in self.subscriptions[topic]:
                self.subscriptions[topic].remove(websocket)
                if not self.subscriptions[topic]:
                    del self.subscriptions[topic]
    
    def subscribe(self, websocket: WebSocket, topic: str) -> None:
        """Subscribe a WebSocket to a topic."""
        if topic not in self.subscriptions:
            self.subscriptions[topic] = []
        if websocket not in self.subscriptions[topic]:
            self.subscriptions[topic].append(websocket)
    
    def unsubscribe(self, websocket: WebSocket, topic: str) -> None:
        """Unsubscribe a WebSocket from a topic."""
        if topic in self.subscriptions:
            if websocket in self.subscriptions[topic]:
                self.subscriptions[topic].remove(websocket)
    
    async def broadcast(self, message: str) -> None:
        """Broadcast a message to all connected WebSockets."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_to_topic(self, topic: str, message: str) -> None:
        """Broadcast a message to WebSockets subscribed to a topic."""
        if topic not in self.subscriptions:
            return
        
        disconnected = []
        for connection in self.subscriptions[topic]:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        """Send a message to a specific WebSocket."""
        await websocket.send_text(message)
    
    async def broadcast_json(self, data: Dict[str, Any]) -> None:
        """Broadcast JSON data to all connected WebSockets."""
        import json
        await self.broadcast(json.dumps(data))
    
    async def broadcast_json_to_topic(self, topic: str, data: Dict[str, Any]) -> None:
        """Broadcast JSON data to WebSockets subscribed to a topic."""
        import json
        await self.broadcast_to_topic(topic, json.dumps(data))
ws_manager = WebSocketManager()

