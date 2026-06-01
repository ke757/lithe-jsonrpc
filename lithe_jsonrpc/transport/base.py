"""Transport abstraction layer.

Transports handle the actual I/O (stdio, WebSocket, etc.) and are
decoupled from the JSON-RPC protocol logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Transport(ABC):
    """Abstract base for all transports.

    Each transport manages a single connection to one client:
    - Stdio transport talks to the parent process via stdin/stdout.
    - WebSocket transport manages one WebSocket connection.

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
        await self.connect()
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
    def transport_type(self) -> str:
        """Human-readable transport name for diagnostics."""
        return self.__class__.__name__
