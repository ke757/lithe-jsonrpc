"""lithe-jsonrpc — A FastAPI-inspired async JSON-RPC 2.0 framework.

Two hooks for building any transport pattern::

    from lithe_jsonrpc import Lithe
    import anyio

    server = Lithe(name="MyService")

    @server.method()
    async def add(a: int, b: int) -> int:
        return a + b

    async def _run():
        async with server.lifespans():               # hook 1 — startup/shutdown
            await server.run_connection(MyTransport())  # hook 2 — recv/process/send

    anyio.run(_run)
"""

from fast_depends import Depends as Depends

from .context import JsonRpcContext
from .errors import LitheError
from .routing import Router
from .server import Lithe

__version__ = "0.1.0"

__all__ = [
    "Lithe",
    "Router",
    "Depends",
    "JsonRpcContext",
    "LitheError",
    "__version__",
]
