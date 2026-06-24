"""Lithe — the main JSON-RPC server class.

FastAPI-inspired ergonomics for JSON-RPC 2.0 services.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from .context import JsonRpcContext
from .errors import InternalError, LitheError
from .transport.base import Transport
from .lifespan import Lifespan
from .middleware import MiddlewareStack
from .protocol import (
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    format_error,
    format_response,
    parse_message,
    parse_request,
    to_json,
)
from .routing import MethodRegistry, Router

logger = logging.getLogger(__name__)


class Lithe:
    """A JSON-RPC 2.0 server with FastAPI-style decorator syntax.

    Example::

        from lithe_jsonrpc import Lithe

        server = Lithe(name="MyService", version="1.0.0")

        @server.method()
        async def add(a: int, b: int) -> int:
            return a + b

        server.serve(StdioTransport())
    """

    def __init__(
        self,
        name: str = "lithe-jsonrpc",
        version: str | None = None,
    ) -> None:
        self._name = name
        self._version = version
        self._registry = MethodRegistry()
        self._middleware = MiddlewareStack()
        self._lifespan = Lifespan()

    # ── Decorators ─────────────────────────────────────────────────

    def middleware(self, func: Callable[..., Any] | None = None) -> Any:
        """Decorator: register a middleware.

        Usage::

            @server.middleware
            async def log_requests(request, context, call_next):
                logger.info(f"-> {request.method}")
                response = await call_next(request)
                logger.info(f"<- {request.method}")
                return response

        Middleware runs in registration order, wrapping the handler.
        Each middleware receives ``(request, context, call_next)``.
        """
        if func is not None:
            self._middleware.add(func)
            return func

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            self._middleware.add(f)
            return f

        return decorator

    def lifespan(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator: register a lifespan (startup/shutdown) function.

        Usage::

            @server.lifespan
            async def lifespan():
                await init_db()
                yield
                await close_db()

        The function must be an async generator with exactly one ``yield``.
        Code before the yield runs at startup; code after runs at shutdown.
        """
        self._lifespan.register(func)
        return func

    def method(self, name: str | None = None) -> Callable[..., Any]:
        """Decorator: register a JSON-RPC method.

        Usage::

            @server.method()
            async def add(a: int, b: int) -> int:
                return a + b

            @server.method(name="user.create")
            async def create_user(name: str, email: str) -> dict:
                return {"id": 1, "name": name, "email": email}

        Args:
            name: JSON-RPC method name. Defaults to the function name.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            method_name = name or func.__name__
            self._registry.register(method_name, func)
            return func

        return decorator

    def include_router(self, router: Router, prefix: str = "") -> None:
        """Mount all methods from a :class:`Router` with an optional prefix.

        Example::

            from devices.routes import router as device_router
            server.include_router(device_router, prefix="device.")

        Args:
            router: A :class:`Router` instance with registered methods.
            prefix: Optional string prepended to every method name
                (e.g. ``"device."`` turns ``connect`` → ``device.connect``).
        """
        self._registry.include(router.registry, prefix)

    # ── Dispatch ───────────────────────────────────────────────────

    async def _handle_request(
        self,
        request: JsonRpcRequest,
        context: JsonRpcContext,
    ) -> JsonRpcResponse | JsonRpcErrorResponse:
        """Process a single request and return a response."""
        try:
            result = await self._registry.dispatch(
                request.method, request.params, context
            )
            return format_response(result, request.id)
        except LitheError as exc:
            return format_error(exc.code, exc.error_message, request.id, exc.data)
        except Exception as exc:
            logger.exception("Unhandled exception in method '%s'", request.method)
            return format_error(
                InternalError.code,
                InternalError.message,
                request.id,
                data=str(exc),
            )

    def _build_handler(
        self, ctx: JsonRpcContext
    ) -> Callable[[JsonRpcRequest], Any]:
        """Build the middleware-wrapped request handler for a connection."""
        async def core_handler(request: JsonRpcRequest) -> Any:
            return await self._handle_request(request, ctx)

        return self._middleware.build(core_handler, ctx)

    async def _process_message(
        self,
        raw: bytes,
        transport,
        handler: Callable[[JsonRpcRequest], Any] | None = None,
    ) -> bytes | None:
        """Process one raw JSON-RPC message. Returns response bytes or None (notification).

        使用 ``transport.codec`` 进行序列化/反序列化。
        """
        codec = transport.codec

        try:
            parsed = parse_message(raw, codec)
        except LitheError as exc:
            resp = format_error(exc.code, exc.error_message, None, exc.data)
            return codec.encode(resp.model_dump(exclude_none=True))

        if isinstance(parsed, list):
            # Batch request
            results = []
            for req in parsed:
                ctx = JsonRpcContext(transport, method=req.method, request_id=req.id)
                if req.is_notification:
                    # Fire-and-forget — no response collected
                    await self._handle_notification(req, ctx)
                else:
                    if handler is not None:
                        results.append(await handler(req))
                    else:
                        results.append(await self._handle_request(req, ctx))
            if results:
                return codec.encode(
                    [r.model_dump(exclude_none=True) for r in results]
                )
            return None  # All were notifications

        # Single request
        ctx = JsonRpcContext(transport, method=parsed.method, request_id=parsed.id)
        if parsed.is_notification:
            await self._handle_notification(parsed, ctx)
            return None

        if handler is not None:
            resp = await handler(parsed)
        else:
            resp = await self._handle_request(parsed, ctx)
        return codec.encode(resp.model_dump(exclude_none=True))

    async def _handle_notification(
        self,
        request: JsonRpcRequest,
        context: JsonRpcContext,
    ) -> None:
        """Handle a notification (fire-and-forget, no response)."""
        try:
            await self._registry.dispatch(
                request.method, request.params, context
            )
        except LitheError:
            # Notifications don't produce error responses per spec
            pass
        except Exception:
            logger.exception("Unhandled exception in notification '%s'", request.method)

    # ── Connection loop ────────────────────────────────────────────
    #
    # The framework exposes exactly two hooks for building async serve
    # loops.  Users combine them with ``anyio.run`` to create whatever
    # transport pattern they need (single-connection, multi-connection,
    # HTTP-based, etc.).

    @asynccontextmanager
    async def lifespans(self) -> AsyncIterator[None]:
        """Async context manager that runs startup/shutdown hooks.

        Usage::

            async with server.lifespans():
                # startup has completed
                await run_my_server()
            # shutdown hooks have run

        Hook 1 of 2.  Combine with :meth:`run_connection` to build
        custom serve loops for multi-connection transports.
        """
        ctx = self._lifespan.build()
        if ctx is not None:
            async with ctx:
                yield
        else:
            yield

    async def run_connection(self, transport: Transport) -> None:
        """Run the JSON-RPC message loop on a single open transport.

        Blocks until the transport signals EOF.  Usage::

            # Per-connection (WebSocket):
            async def ws_endpoint(websocket):
                transport = WebSocketTransport(websocket)
                await server.run_connection(transport)

            # Single-connection (stdio), combined with lifespans():
            async def _run():
                async with server.lifespans():
                    await server.run_connection(StdioTransport())
            anyio.run(_run)

        Hook 2 of 2.  Combine with :meth:`lifespans` to build custom
        serve loops for any transport model.
        """
        async with transport:
            logger.info(
                "lithe-jsonrpc '%s' running on %s",
                self._name,
                transport.transport_type,
            )
            ctx = JsonRpcContext(transport)
            handler = self._build_handler(ctx)
            while True:
                try:
                    raw = await transport.recv()
                except EOFError:
                    break
                response = await self._process_message(raw, transport, handler)
                if response is not None:
                    await transport.send(response)

    # ── Hook integration ────────────────────────────────────────────────────

    def framework(self) -> Connection:
        """Create a :class:`Connection` context manager.

        Usage::

            import anyio

            async def _run():
                async with server.connect() as conn:
                    await conn.serve(StdioTransport())

            anyio.run(_run)

        :meth:`Connection.serve` accepts a transport argument and can be
        called multiple times — useful for multi-connection transports
        (e.g. WebSocket) where a new transport is created per connection.
        """
        return Connection(self)



class Connection:
    """Async context manager for a JSON-RPC serve session.

    Created by :meth:`Lithe.connect`.  On enter, lifespan startup hooks
    run.  Call :meth:`serve` with a transport to start a message loop.
    On exit, shutdown hooks run.

    Single-connection (stdio)::

        async with server.connect() as conn:
            await conn.serve(StdioTransport())

    Multi-connection (WebSocket)::

        async with server.connect() as conn:
            # per connection:
            await conn.serve(WebSocketTransport(websocket))
    """

    __slots__ = ("_server", "_lifespan")

    def __init__(self, server: Lithe) -> None:
        self._server = server

    async def __aenter__(self) -> Connection:
        self._lifespan = self._server.lifespans()
        await self._lifespan.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._lifespan.__aexit__(*args)

    async def run_turn(self, transport: Transport) -> None:
        """Run the JSON-RPC message loop on *transport* (block until EOF).

        May be called multiple times with different transports — each
        call handles one connection.
        """
        await self._server.run_connection(transport)


__all__ = ["Connection", "Lithe"]
