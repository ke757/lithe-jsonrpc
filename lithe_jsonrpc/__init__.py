"""lithe-jsonrpc — A FastAPI-inspired async JSON-RPC 2.0 framework.

Usage::

    from lithe_jsonrpc import Lithe, Depends

    server = Lithe(name="MyService")

    @server.method()
    async def add(a: int, b: int) -> int:
        return a + b

    server.run(transport="stdio")
"""

from fast_depends import Depends as Depends

from .context import JsonRpcContext
from .errors import LitheError
from .server import Lithe

__version__ = "0.1.0"

__all__ = [
    "Lithe",
    "Depends",
    "JsonRpcContext",
    "LitheError",
    "__version__",
]
