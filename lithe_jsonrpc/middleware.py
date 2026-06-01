"""Middleware stack — request/response interceptors.

FastAPI-style: each middleware is an async callable that receives a
``JsonRpcRequest``, ``JsonRpcContext``, and a ``call_next`` function,
and returns a response.

Example::

    @server.middleware
    async def log_requests(request, context, call_next):
        logger.info(f\"-> {request.method}\")
        response = await call_next(request)
        logger.info(f\"<- {request.method}\")
        return response
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from .context import JsonRpcContext
from .protocol import JsonRpcErrorResponse, JsonRpcRequest, JsonRpcResponse


class NextCall(Protocol):
    """Protocol for the ``call_next`` parameter passed to middleware."""

    async def __call__(self, request: JsonRpcRequest) -> Any: ...


#: Middleware signature: (request, context, call_next) → response
MiddlewareFunc = Callable[
    [JsonRpcRequest, JsonRpcContext, NextCall],
    Awaitable[JsonRpcResponse | JsonRpcErrorResponse],
]

#: Inner handler: (request) → response
HandlerFunc = Callable[
    [JsonRpcRequest],
    Awaitable[JsonRpcResponse | JsonRpcErrorResponse],
]


class MiddlewareStack:
    """An ordered stack of middleware wrapping an inner handler.

    Each middleware calls ``call_next(request)`` to invoke the next layer.
    """

    def __init__(self) -> None:
        self._middlewares: list[MiddlewareFunc] = []

    def add(self, middleware: MiddlewareFunc) -> None:
        """Register a middleware. Executed in registration order."""
        self._middlewares.append(middleware)

    def build(self, handler: HandlerFunc, context: JsonRpcContext) -> HandlerFunc:
        """Wrap the terminal handler with the middleware chain.

        Returns a single callable that represents the full stack.
        """
        wrapped = handler

        for mw in reversed(self._middlewares):

            def _make(
                next_handler: HandlerFunc,
                mw: MiddlewareFunc,
                ctx: JsonRpcContext,
            ) -> HandlerFunc:
                async def _call(request: JsonRpcRequest) -> Any:
                    return await mw(request, ctx, next_handler)

                return _call

            wrapped = _make(wrapped, mw, context)

        return wrapped


__all__ = ["MiddlewareStack", "MiddlewareFunc", "NextCall"]
