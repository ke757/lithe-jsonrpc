"""Stdio transport — communicates via stdin/stdout using ``anyio``.

Each message is a single newline-delimited JSON line.

Uses ``anyio.wrap_file()`` to wrap ``sys.stdin.buffer`` and
``sys.stdout.buffer`` as native async file objects — no thread-pool
workaround needed.
"""

from __future__ import annotations

import sys

import anyio

from .base import Transport


class StdioTransport(Transport):
    """JSON-RPC transport over standard input/output.

    Reads JSON-RPC messages from stdin (one per line) and writes
    responses to stdout. Designed for subprocess-based integrations.

    Uses anyio's native async file I/O::

        stdin  →  anyio.wrap_file(sys.stdin.buffer)   →  async readline
        stdout →  anyio.wrap_file(sys.stdout.buffer)  →  async write
    """

    def __init__(self) -> None:
        self._stdin: anyio.AsyncFile[str] | None = None
        self._stdout: anyio.AsyncFile[bytes] | None = None

    async def connect(self) -> None:
        # Wrap stdin as text stream for line-oriented reading
        self._stdin = anyio.wrap_file(sys.stdin)
        # Wrap stdout as binary stream for byte-level writes
        self._stdout = anyio.wrap_file(sys.stdout.buffer)

    async def disconnect(self) -> None:
        if self._stdin is not None:
            await self._stdin.aclose()
        if self._stdout is not None:
            await self._stdout.aclose()

    async def send(self, message: bytes) -> None:
        """Write a JSON-RPC message line to stdout."""
        assert self._stdout is not None
        await self._stdout.write(message + b"\n")
        await self._stdout.flush()

    async def recv(self) -> bytes:
        """Read one line from stdin.

        Raises ``EOFError`` when stdin is closed by the parent process.
        """
        assert self._stdin is not None
        line = await self._stdin.readline()
        if not line:
            raise EOFError("stdin closed")
        return line.strip().encode()

    @property
    def transport_type(self) -> str:
        return "stdio"
