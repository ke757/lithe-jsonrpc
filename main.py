"""lithe-jsonrpc demo server.

Run with:
    python main.py              # stdio transport (default)
    python main.py --ws         # WebSocket transport on ws://127.0.0.1:8000
"""

import sys

from lithe_jsonrpc import Lithe, Depends, JsonRpcContext

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
    if "--ws" in sys.argv:
        server.run(transport="websocket", host="127.0.0.1", port=8000)
    else:
        server.run(transport="stdio")
