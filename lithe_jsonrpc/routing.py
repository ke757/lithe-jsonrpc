"""Method registry and routing for JSON-RPC method dispatch.

Uses ``fast-depends`` for dependency injection, type coercion, and
Pydantic validation — the same engine that powers FastAPI.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints

from fast_depends import inject

from .context import JsonRpcContext
from .errors import InvalidParamsError, MethodNotFoundError


class RpcMethod:
    """A registered JSON-RPC method handler.

    The user function is wrapped with ``@inject`` from ``fast-depends``,
    which provides:

    * **Depends** resolution (``Depends(get_db)``)
    * **Type coercion** (``\"42\"`` → ``42``)
    * **Pydantic validation** (complex model params)

    ``JsonRpcContext`` is detected by type annotation and injected
    automatically on each call.
    """

    __slots__ = (
        "name",
        "func",
        "description",
        "_param_names",
        "_context_param_name",
    )

    def __init__(self, name: str, func: Callable[..., Any]) -> None:
        self.name = name
        self.description = inspect.getdoc(func) or ""
        self._param_names: list[str] = []
        self._context_param_name: str | None = None

        # Wrap with fast-depends @inject for Depends resolution + validation
        injected = inject(func)

        # Preserve the original function identity for nicer tracebacks
        injected.__name__ = func.__name__
        injected.__qualname__ = func.__qualname__

        self.func = injected
        self._inspect_signature(func)

    def _inspect_signature(self, func: Callable[..., Any]) -> None:
        """Record parameter metadata for positional-param mapping and context injection."""
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}
        sig = inspect.signature(func)
        for param in sig.parameters.values():
            annotation = hints.get(param.name, param.annotation)
            if annotation is JsonRpcContext:
                self._context_param_name = param.name
            else:
                self._param_names.append(param.name)

    async def call(self, params: Any, context: JsonRpcContext) -> Any:
        """Validate params and invoke the handler.

        Args:
            params: The ``params`` field from a JSON-RPC request
                    (dict for named params, list for positional).
            context: Per-request context object, injected if declared.

        Returns:
            The handler's return value (unwrapped — caller serialises).
        """
        # Build kwargs from JSON-RPC params
        kwargs: dict[str, Any] = {}

        if isinstance(params, list):
            # Positional params → map to parameter names by order
            if len(params) > len(self._param_names):
                raise InvalidParamsError(
                    f"Too many positional arguments: "
                    f"expected at most {len(self._param_names)}, got {len(params)}"
                )
            kwargs = dict(zip(self._param_names, params))
        elif isinstance(params, dict):
            kwargs = dict(params)
        elif params is not None:
            raise InvalidParamsError(
                "params must be a list (positional) or object (named)"
            )

        # Inject JsonRpcContext if the handler declares it
        if self._context_param_name is not None:
            kwargs[self._context_param_name] = context

        # fast-depends @inject handles Depends resolution, type coercion, validation
        return await self.func(**kwargs)


class MethodRegistry:
    """Registry of named JSON-RPC methods."""

    def __init__(self) -> None:
        self._methods: dict[str, RpcMethod] = {}

    def register(self, name: str, func: Callable[..., Any]) -> RpcMethod:
        """Register a new method handler."""
        method = RpcMethod(name, func)
        self._methods[name] = method
        return method

    def get(self, name: str) -> RpcMethod:
        """Look up a method by name.

        Raises :class:`MethodNotFoundError` if the method isn't registered.
        """
        try:
            return self._methods[name]
        except KeyError:
            raise MethodNotFoundError(f"Method '{name}' not found") from None

    def list_methods(self) -> dict[str, str]:
        """Return ``{method_name: description}`` for all registered methods."""
        return {name: m.description for name, m in self._methods.items()}

    def include(self, other: MethodRegistry, prefix: str = "") -> None:
        """Merge methods from another registry, optionally adding a prefix.

        Example::

            registry.include(router._registry, prefix="device.")
        """
        for name, method in other._methods.items():
            self._methods[prefix + name] = method

    async def dispatch(
        self,
        method_name: str,
        params: Any,
        context: JsonRpcContext,
    ) -> Any:
        """Resolve a method name, validate params, call the handler, return result."""
        method = self.get(method_name)
        return await method.call(params, context)


class Router:
    """A group of JSON-RPC methods that can be mounted as a unit.

    Like FastAPI's ``APIRouter``, this allows splitting method definitions
    across modules without a shared ``Lithe`` instance.

    Example::

        # devices/routes.py
        router = Router()

        @router.method()
        async def connect(addr: str) -> dict:
            ...

        # server.py
        from devices.routes import router as device_router
        server.include_router(device_router, prefix="device.")
    """

    def __init__(self) -> None:
        self._registry = MethodRegistry()

    @property
    def registry(self) -> MethodRegistry:
        """The internal :class:`MethodRegistry` backing this router."""
        return self._registry

    def method(self, name: str | None = None) -> Callable[..., Any]:
        """Decorator: register a JSON-RPC method on this router.

        Args:
            name: JSON-RPC method name. Defaults to the function name.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            method_name = name or func.__name__
            self._registry.register(method_name, func)
            return func

        return decorator


__all__ = ["RpcMethod", "MethodRegistry", "Router"]
