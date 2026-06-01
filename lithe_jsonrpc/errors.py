"""JSON-RPC 2.0 standard error codes and exception hierarchy.

Maps Python exceptions to JSON-RPC error codes so framework code can simply
``raise MethodNotFound(...)`` and the protocol layer serialises it correctly.
"""

from __future__ import annotations

from typing import Any


# ── Standard error codes (JSON-RPC 2.0 §5.1) ──────────────────────────

PARSE_ERROR = -32700
"""Invalid JSON was received by the server."""

INVALID_REQUEST = -32600
"""The JSON sent is not a valid Request object."""

METHOD_NOT_FOUND = -32601
"""The method does not exist / is not available."""

INVALID_PARAMS = -32602
"""Invalid method parameter(s)."""

INTERNAL_ERROR = -32603
"""Internal JSON-RPC error."""

# Server error range: -32000 to -32099 (reserved for implementation-defined errors)
SERVER_ERROR_START = -32000
SERVER_ERROR_END = -32099


# ── Exception hierarchy ───────────────────────────────────────────────


class LitheError(Exception):
    """Base exception for all framework-level errors.

    Subclasses carry a JSON-RPC error ``code`` and user-facing ``message``.
    ```

    Attributes:
        code: JSON-RPC error code.
        message: Human-readable error description.
        data: Optional additional data attached to the error object.
    """

    code: int = INTERNAL_ERROR
    message: str = "Internal error"

    def __init__(self, message: str | None = None, data: Any = None) -> None:
        super().__init__(message or self.message)
        self._message = message or self.message
        self.data = data

    @property
    def error_message(self) -> str:
        return self._message


class ParseError(LitheError):
    """Invalid JSON was received."""

    code = PARSE_ERROR
    message = "Parse error"


class InvalidRequestError(LitheError):
    """The JSON sent is not a valid Request object."""

    code = INVALID_REQUEST
    message = "Invalid Request"


class MethodNotFoundError(LitheError):
    """The method does not exist."""

    code = METHOD_NOT_FOUND
    message = "Method not found"


class InvalidParamsError(LitheError):
    """Invalid method parameter(s)."""

    code = INVALID_PARAMS
    message = "Invalid params"


class InternalError(LitheError):
    """Internal JSON-RPC error."""

    code = INTERNAL_ERROR
    message = "Internal error"


class ServerDefinedError(LitheError):
    """An application-defined error within the reserved server range."""

    def __init__(
        self,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        if not (SERVER_ERROR_START <= code <= SERVER_ERROR_END):
            raise ValueError(
                f"Server-defined error code must be in range "
                f"[{SERVER_ERROR_START}, {SERVER_ERROR_END}], got {code}"
            )
        self.code = code
        super().__init__(message, data)


__all__ = [
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "SERVER_ERROR_START",
    "SERVER_ERROR_END",
    "LitheError",
    "ParseError",
    "InvalidRequestError",
    "MethodNotFoundError",
    "InvalidParamsError",
    "InternalError",
    "ServerDefinedError",
]
