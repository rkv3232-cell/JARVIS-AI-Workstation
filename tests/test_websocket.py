import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from backend.websocket_manager import WebSocketManager, ClientConnection

@pytest.mark.asyncio
async def test_websocket_manager_connect_and_broadcast():
    manager = WebSocketManager()
    
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.close = AsyncMock()

    client_id = "test_client_1"
    client = await manager.connect(mock_ws, client_id)

    assert client.client_id == client_id
    assert client.is_alive is True
    assert manager.get_active_count() == 1

    # Broadcast message
    await manager.broadcast("test_event", {"status": "ok"}, channel="all")
    
    # Wait for client's sender task to consume queue
    await asyncio.sleep(0.05)
    assert mock_ws.send_text.called

    # Disconnect
    await manager.disconnect(client_id)
    assert manager.get_active_count() == 0

@pytest.mark.asyncio
async def test_bounded_queue_slow_client_overflow():
    mock_ws = AsyncMock()
    client = ClientConnection(mock_ws, "slow_client", max_queue_size=3)

    # Fill queue to capacity
    for i in range(3):
        ok = await client.enqueue_message(f"msg_{i}")
        assert ok is True

    # When queue is full, oldest message is dropped to make room for newest real-time update
    ok_overflow = await client.enqueue_message("msg_overflow")
    assert ok_overflow is True
    assert client.queue.qsize() == 3
