"""Transport abstraction layer.

Transports handle the actual I/O (stdio, WebSocket, TCP, etc.) and are
decoupled from the JSON-RPC protocol logic.  Each transport can specify
its preferred serialization format via the :attr:`codec` property.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..codec import Codec


class Transport(ABC):
    """Abstract base for all transports.

    Each transport manages a single connection to one client:
    - Stdio transport talks to the parent process via stdin/stdout.
    - WebSocket transport manages one WebSocket connection.
    - TCP transport connects to a remote server.

    Transports are async context managers: ``async with transport:``
    for lifecycle management (connect / disconnect).
    """

    @abstractmethod
    async def send(self, message: bytes) -> None:
        """Send a raw message to the client."""
        ...

    @abstractmethod
    async def recv(self) -> bytes:
        """Receive a raw message from the client.

        Should block until a complete message arrives.
        """
        ...

    async def __aenter__(self) -> Transport:
        try:
            await self.connect()
        except BaseException:
            await self.disconnect()
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Setup the transport (optional hook)."""
        pass

    async def disconnect(self) -> None:
        """Tear down the transport (optional hook)."""
        pass

    @property
    def codec(self) -> Codec:
        """Transport 使用的序列化编解码器。"""
        from ..codec import JsonCodec

        return JsonCodec()

    @property
    def transport_type(self) -> str:
        """Human-readable transport name for diagnostics."""
        return self.__class__.__name__
