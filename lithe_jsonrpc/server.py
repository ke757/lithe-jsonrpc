"""Lithe — the main JSON-RPC server class.

FastAPI-inspired ergonomics for JSON-RPC 2.0 services.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .context import JsonRpcContext
from .errors import InternalError, LitheError
from .lifespan import Lifespan
from .middleware import MiddlewareStack
from .protocol import (
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    format_error,
    format_response,
    parse_request,
    to_json,
)
from .routing import MethodRegistry

logger = logging.getLogger(__name__)


class Lithe:
    """A JSON-RPC 2.0 server with FastAPI-style decorator syntax.

    Example::

        from lithe_jsonrpc import Lithe

        server = Lithe(name="MyService", version="1.0.0")

        @server.method()
        async def add(a: int, b: int) -> int:
            return a + b

        server.run(transport="stdio")
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
        """Process one raw JSON-RPC message. Returns response bytes or None (notification)."""
        try:
            parsed = parse_request(raw)
        except LitheError as exc:
            resp = format_error(exc.code, exc.error_message, None, exc.data)
            return to_json(resp).encode()

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
                batch_json = "[" + ",".join(to_json(r) for r in results) + "]"
                return batch_json.encode()
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
        return to_json(resp).encode()

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

    # ── Run ────────────────────────────────────────────────────────

    def run(
        self,
        transport: str = "stdio",
        **kwargs: Any,
    ) -> None:
        """Start the server with the specified transport.

        Args:
            transport: ``"stdio"`` or ``"websocket"``.
            **kwargs: Passed to the transport constructor
                (e.g. ``host``, ``port`` for WebSocket).
        """
        import anyio

        if transport == "stdio":
            anyio.run(self._run_stdio)
        elif transport == "websocket":
            import functools
            anyio.run(functools.partial(self._run_websocket, **kwargs))
        else:
            raise ValueError(
                f"Unknown transport '{transport}'. "
                f"Use 'stdio' or 'websocket'."
            )

    async def _run_stdio(self) -> None:
        """Run the server over stdio transport."""
        from .transport.stdio import StdioTransport

        lifespan_ctx = self._lifespan.build()
        if lifespan_ctx is not None:
            async with lifespan_ctx:
                await self._serve_stdio()
        else:
            await self._serve_stdio()

    async def _serve_stdio(self) -> None:
        """Internal: serve JSON-RPC over stdio (after lifespan startup)."""
        from .transport.stdio import StdioTransport

        async with StdioTransport() as t:
            logger.info(
                "lithe-jsonrpc '%s' running on stdio",
                self._name,
            )
            ctx = JsonRpcContext(t)
            handler = self._build_handler(ctx)
            while True:
                try:
                    raw = await t.recv()
                except EOFError:
                    break
                response = await self._process_message(raw, t, handler)
                if response is not None:
                    await t.send(response)

    async def _run_websocket(self, **kwargs: Any) -> None:
        """Run the server over WebSocket transport."""
        lifespan_ctx = self._lifespan.build()
        if lifespan_ctx is not None:
            async with lifespan_ctx:
                await self._serve_websocket(**kwargs)
        else:
            await self._serve_websocket(**kwargs)

    async def _serve_websocket(self, **kwargs: Any) -> None:
        """Internal: serve JSON-RPC over WebSocket (after lifespan startup)."""
        import uvicorn

        from .transport.websocket import create_asgi_app

        app = create_asgi_app(self)
        host = kwargs.get("host", "127.0.0.1")
        port = kwargs.get("port", 8000)

        config = uvicorn.Config(app, host=host, port=port, **kwargs)
        ws_server = uvicorn.Server(config)
        logger.info(
            "lithe-jsonrpc '%s' running on ws://%s:%d",
            self._name,
            host,
            port,
        )
        await ws_server.serve()


__all__ = ["Lithe"]
