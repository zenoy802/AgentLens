from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])

PING_INTERVAL_SECONDS = 30.0
PONG_TIMEOUT_SECONDS = 30.0


class AnnotationBroadcaster:
    def __init__(self) -> None:
        self._channels: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, query_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._channels[query_id].add(ws)

    async def unsubscribe(self, query_id: int, ws: WebSocket) -> None:
        async with self._lock:
            clients = self._channels.get(query_id)
            if clients is None:
                return
            clients.discard(ws)
            if not clients:
                self._channels.pop(query_id, None)

    async def broadcast(self, query_id: int, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._channels.get(query_id, set()))

        stale_clients: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(message)
            except Exception:
                stale_clients.append(client)

        if not stale_clients:
            return

        async with self._lock:
            channel = self._channels.get(query_id)
            if channel is None:
                return
            for client in stale_clients:
                channel.discard(client)
            if not channel:
                self._channels.pop(query_id, None)


annotation_broadcaster = AnnotationBroadcaster()


@router.websocket("/ws/queries/{query_id}/annotations")
async def annotation_ws(websocket: WebSocket, query_id: int) -> None:
    await websocket.accept()
    await annotation_broadcaster.subscribe(query_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "query_id": query_id})
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=PING_INTERVAL_SECONDS,
                )
            except TimeoutError:
                if not await _send_ping_and_wait_for_pong(websocket):
                    break
                continue

            if isinstance(message, dict) and message.get("type") == "pong":
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await annotation_broadcaster.unsubscribe(query_id, websocket)


async def _send_ping_and_wait_for_pong(websocket: WebSocket) -> bool:
    try:
        await websocket.send_json({"type": "ping"})
        message = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=PONG_TIMEOUT_SECONDS,
        )
    except (TimeoutError, WebSocketDisconnect):
        await _close_websocket(websocket)
        return False
    if isinstance(message, dict) and message.get("type") == "pong":
        return True
    await _close_websocket(websocket)
    return False


async def _close_websocket(websocket: WebSocket) -> None:
    with suppress(RuntimeError):
        await websocket.close()
