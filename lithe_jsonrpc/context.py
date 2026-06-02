"""Per-request context and server→client push notification support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .transport.base import Transport


class JsonRpcContext:
    """Context object injected into RPC method handlers.

    Provides access to request metadata and the ability to send
    server→client notifications (JSON-RPC push).
    """

    __slots__ = ("_transport", "method", "request_id")

    def __init__(
        self,
        transport: Transport,
        method: str = "",
        request_id: str | int | float | None = None,
    ) -> None:
        self._transport = transport
        self.method = method
        self.request_id = request_id

    @property
    def transport(self) -> Transport:
        return self._transport

    async def notify(self, method: str, params: Any = None) -> None:
        """Send a JSON-RPC notification (push) to the connected client.

        A notification has no ``id`` field — the client should not send a response.

        Args:
            method: The notification method name.
            params: Optional notification parameters.
        """
        from .protocol import JsonRpcRequest, to_json

        notif = JsonRpcRequest(method=method, params=params, id=None)
        await self._transport.send(to_json(notif).encode())
