"""WebSocket transport — ASGI application for JSON-RPC over WebSocket.

Uses ``starlette`` for ASGI WebSocket support. Each WebSocket connection
gets its own message loop with its own middleware stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from .base import Transport

if TYPE_CHECKING:
    from ..server import Lithe


class WebSocketTransport(Transport):
    """JSON-RPC transport over a single WebSocket connection."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def connect(self) -> None:
        await self._ws.accept()

    async def disconnect(self) -> None:
        if self._ws.client_state.name != "DISCONNECTED":
            try:
                await self._ws.close()
            except Exception:
                pass

    async def send(self, message: bytes) -> None:
        """Send a JSON-RPC message over the WebSocket (text frame)."""
        await self._ws.send_text(message.decode())

    async def recv(self) -> bytes:
        """Receive a JSON-RPC message over the WebSocket.

        Raises ``EOFError`` when the client disconnects.
        """
        try:
            data = await self._ws.receive_text()
            return data.encode()
        except Exception:
            raise EOFError("WebSocket disconnected")

    @property
    def transport_type(self) -> str:
        return "websocket"


async def _websocket_endpoint(ws: WebSocket, server: Lithe) -> None:
    """Handle a single WebSocket connection's JSON-RPC message loop."""
    transport = WebSocketTransport(ws)
    async with transport:
        from ..context import JsonRpcContext

        ctx = JsonRpcContext(transport)
        handler = server._build_handler(ctx)

        while True:
            try:
                raw = await transport.recv()
            except EOFError:
                break
            response = await server._process_message(raw, transport, handler)
            if response is not None:
                await transport.send(response)


def create_asgi_app(server: Lithe) -> Starlette:
    """Build an ASGI Starlette app that bridges WebSocket connections to the server."""

    async def endpoint(ws: WebSocket) -> None:
        await _websocket_endpoint(ws, server)

    return Starlette(routes=[WebSocketRoute("/", endpoint)])

