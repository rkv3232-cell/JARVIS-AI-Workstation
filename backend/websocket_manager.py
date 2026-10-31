import asyncio
import json
import time
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from .security import redact_secrets

class ClientConnection:
    """
    Encapsulates a connected WebSocket client with a bounded outgoing queue,
    per-client lock, heartbeat tracker, and event subscriptions.
    """
    def __init__(self, websocket: WebSocket, client_id: str, max_queue_size: int = 50):
        self.websocket = websocket
        self.client_id = client_id
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.lock = asyncio.Lock()
        self.is_alive = True
        self.last_pong = time.time()
        self.subscribed_channels: Set[str] = {"all", "telemetry", "voice_state", "trading", "research", "system"}
        self._sender_task: Optional[asyncio.Task] = None

    async def start_sender(self):
        """Dedicated background sender loop reading bounded queue."""
        try:
            while self.is_alive:
                msg_json = await self.queue.get()
                async with self.lock:
                    try:
                        await self.websocket.send_text(msg_json)
                    except Exception as e:
                        print(f"[WS Client {self.client_id}] Send failed: {e}")
                        self.is_alive = False
                        break
                self.queue.task_done()
        except asyncio.CancelledError:
            pass

    async def enqueue_message(self, message_str: str) -> bool:
        """
        Attempts to enqueue a message. If the client is slow and queue is full,
        drops older messages or marks client dead to prevent server memory bloat.
        """
        if not self.is_alive:
            return False
        try:
            if self.queue.full():
                # Pop oldest message to make room for newest real-time update
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    pass
            self.queue.put_nowait(message_str)
            return True
        except asyncio.QueueFull:
            print(f"[WS Manager] Client {self.client_id} queue overflow; marking disconnected.")
            self.is_alive = False
            return False

class WebSocketManager:
    """
    Production-grade WebSocket manager providing:
    - Per-client locks preventing concurrent write collisions
    - Bounded per-client queues preventing slow-client OOM
    - Heartbeat ping/pong health monitor
    - Topic-based broadcast routing
    """
    def __init__(self):
        self._clients: Dict[str, ClientConnection] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, client_id: str) -> ClientConnection:
        await websocket.accept()
        client = ClientConnection(websocket, client_id)
        async with self._lock:
            self._clients[client_id] = client
            client._sender_task = asyncio.create_task(client.start_sender())
        return client

    async def disconnect(self, client_id: str):
        async with self._lock:
            client = self._clients.pop(client_id, None)
            if client:
                client.is_alive = False
                if client._sender_task:
                    client._sender_task.cancel()
                try:
                    await client.websocket.close()
                except Exception:
                    pass

    async def broadcast(self, event: str, payload: Any, channel: str = "all"):
        """
        Thread-safe & async broadcast of events to subscribed and alive clients.
        Automatically removes dead/slow clients.
        """
        msg = {
            "event": event,
            "channel": channel,
            "timestamp": time.time(),
            "payload": redact_secrets(payload)
        }
        msg_str = json.dumps(msg, ensure_ascii=False)

        dead_ids = []
        async with self._lock:
            for cid, client in list(self._clients.items()):
                if not client.is_alive:
                    dead_ids.append(cid)
                    continue
                if channel == "all" or channel in client.subscribed_channels:
                    ok = await client.enqueue_message(msg_str)
                    if not ok:
                        dead_ids.append(cid)

        if dead_ids:
            for cid in dead_ids:
                await self.disconnect(cid)

    async def send_personal_message(self, client_id: str, event: str, payload: Any):
        msg = {
            "event": event,
            "timestamp": time.time(),
            "payload": redact_secrets(payload)
        }
        msg_str = json.dumps(msg, ensure_ascii=False)
        async with self._lock:
            client = self._clients.get(client_id)
            if client and client.is_alive:
                await client.enqueue_message(msg_str)

    def get_active_count(self) -> int:
        return len([c for c in self._clients.values() if c.is_alive])

    async def start_heartbeat(self, interval_seconds: int = 20):
        """Sends periodic ping frames to identify and purge dead connections."""
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                ping_msg = json.dumps({"event": "ping", "timestamp": time.time()})
                dead_ids = []
                async with self._lock:
                    for cid, client in list(self._clients.items()):
                        if not client.is_alive:
                            dead_ids.append(cid)
                            continue
                        try:
                            await client.enqueue_message(ping_msg)
                        except Exception:
                            dead_ids.append(cid)
                for cid in dead_ids:
                    await self.disconnect(cid)
        except asyncio.CancelledError:
            pass

ws_manager = WebSocketManager()
