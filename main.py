"""lithe-jsonrpc demo server — demonstrates the transport-agnostic API.

Run with::

    python main.py              # stdio transport

The demo includes a minimal ``StdioTransport`` inline to show how to
implement the :class:`Transport` ABC. Real applications should import
their transport from the application layer (e.g. ``app.transports``).
"""

import sys

import anyio

from lithe_jsonrpc import Lithe, Depends, JsonRpcContext
from lithe_jsonrpc.transport import Transport


# ── Minimal transport for demo purposes ──────────────────────────────

class DemoStdioTransport(Transport):
    """Minimal newline-delimited stdio transport for the demo.

    Real applications should put transports in the app layer and
    customise the framing to their needs.
    """

    def __init__(self) -> None:
        self._stdin: anyio.AsyncFile[str] | None = None
        self._stdout: anyio.AsyncFile[bytes] | None = None

    async def connect(self) -> None:
        self._stdin = anyio.wrap_file(sys.stdin)
        self._stdout = anyio.wrap_file(sys.stdout.buffer)

    async def disconnect(self) -> None:
        if self._stdin is not None:
            await self._stdin.aclose()
        if self._stdout is not None:
            await self._stdout.aclose()

    async def send(self, message: bytes) -> None:
        assert self._stdout is not None
        await self._stdout.write(message + b"\n")
        await self._stdout.flush()

    async def recv(self) -> bytes:
        assert self._stdin is not None
        line = await self._stdin.readline()
        if not line:
            raise EOFError("stdin closed")
        return line.strip().encode()

    @property
    def transport_type(self) -> str:
        return "demo-stdio"

# ── Server ──────────────────────────────────────────────────────────

server = Lithe(name="DemoService", version="0.1.0")


# ── Lifespan ────────────────────────────────────────────────────────

@server.lifespan
async def lifespan():
    print("[lifespan] Starting up...")
    yield
    print("[lifespan] Shutting down...")


# ── Middleware ──────────────────────────────────────────────────────

@server.middleware
async def log_requests(request, context, call_next):
    print(f"[mw] -> {request.method} (id={request.id})")
    response = await call_next(request)
    print(f"[mw] <- {request.method}")
    return response


# ── Simple RPC methods ──────────────────────────────────────────────

@server.method()
async def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.method()
async def ping() -> str:
    """Health check."""
    return "pong"


# ── Method with dependency injection ────────────────────────────────

async def get_greeting() -> str:
    return "Hello"


@server.method(name="greet")
async def greet_user(name: str, greeting: str = Depends(get_greeting)) -> str:
    """Greet a user by name."""
    return f"{greeting}, {name}!"


# ── Method with context (server→client push) ───────────────────────

@server.method()
async def echo(msg: str, ctx: JsonRpcContext) -> str:
    """Echo a message, and also push a notification back."""
    await ctx.notify("echo_ack", {"original": msg})
    return f"echo: {msg}"


# ── Method list (non-standard, convenience) ─────────────────────────

@server.method(name="system.listMethods")
async def list_methods() -> list[str]:
    """List all available methods."""
    return list(server._registry._methods.keys())


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    server.serve(DemoStdioTransport())
