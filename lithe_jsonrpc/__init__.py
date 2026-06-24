"""lithe-jsonrpc — A FastAPI-inspired async JSON-RPC 2.0 framework.

Context manager for single-connection transports::

    import anyio
    from lithe_jsonrpc import Lithe

    server = Lithe(name="MyService")

    @server.method()
    async def add(a: int, b: int) -> int:
        return a + b

    async def _run():
        async with server.connect() as conn:
            await conn.serve(MyTransport())

    anyio.run(_run)

Multi-connection (WebSocket) — same pattern, serve() called per connection::

    async with server.connect() as conn:
        # per WebSocket connection:
        await conn.serve(WebSocketTransport(websocket))

Two raw hooks are also available for custom loops::

    async with server.lifespans():                # hook 1
        await server.run_connection(transport)    # hook 2
"""

from fast_depends import Depends as Depends

from .codec import Codec, JsonCodec, MsgPackCodec
from .context import JsonRpcContext
from .errors import LitheError
from .routing import Router
from .server import Connection, Lithe

__version__ = "0.1.0"

__all__ = [
    "Codec",
    "JsonCodec",
    "MsgPackCodec",
    "Connection",
    "Lithe",
    "Router",
    "Depends",
    "JsonRpcContext",
    "LitheError",
    "__version__",
]
