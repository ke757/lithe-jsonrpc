"""Lifespan support — startup and shutdown hooks.

FastAPI-style: an async context manager that yields after startup
and runs cleanup after the server stops.

Example::

    @server.lifespan
    async def lifespan():
        await init_db()
        yield
        await close_db()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, Callable


class Lifespan:
    """Manages server lifecycle hooks.

    Accepts an async generator function::

        async def lifespan():
            # startup
            yield
            # shutdown
    """

    def __init__(self) -> None:
        self._func: Callable[..., Any] | None = None

    def register(self, func: Callable[..., Any]) -> None:
        """Register a lifespan generator function."""
        self._func = func

    def build(self) -> AsyncContextManager[None] | None:
        """Return an async context manager for the lifespan, or None."""
        if self._func is None:
            return None

        @asynccontextmanager
        async def _ctx():
            gen = self._func()
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                raise RuntimeError(
                    "Lifespan function must include a 'yield' statement"
                ) from None
            try:
                yield
            finally:
                try:
                    await gen.__anext__()
                except StopAsyncIteration:
                    pass
                else:
                    raise RuntimeError(
                        "Lifespan function must have exactly one 'yield'"
                    )

        return _ctx()
