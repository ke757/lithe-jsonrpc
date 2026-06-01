"""JSON-RPC 2.0 protocol models and message handling.

Spec: https://www.jsonrpc.org/specification
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema


# ── Request ───────────────────────────────────────────────────────────

class JsonRpcRequest(BaseModel):
    """A JSON-RPC 2.0 request object.

    Notifications (server push, client fire-and-forget) omit the ``id`` field.
    """

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Annotated[Any, SkipJsonSchema] = Field(
        default_factory=dict,
        description="Parameters: positional (list) or named (dict).",
    )
    id: str | int | float | None = None

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: Any) -> Any:
        """JSON-RPC id must be string, integer, float, or null."""
        if v is None:
            return None
        if isinstance(v, (str, int, float)):
            return v
        raise ValueError("id must be a string, number, or null")

    @property
    def is_notification(self) -> bool:
        """True when this is a notification (no id)."""
        return self.id is None


# ── Response ──────────────────────────────────────────────────────────

class JsonRpcErrorObject(BaseModel):
    """The error object within a JSON-RPC error response."""

    code: int
    message: str
    data: Any = None


class JsonRpcResponse(BaseModel):
    """A JSON-RPC 2.0 success response."""

    jsonrpc: Literal["2.0"] = "2.0"
    result: Any
    id: str | int | float | None


class JsonRpcErrorResponse(BaseModel):
    """A JSON-RPC 2.0 error response."""

    jsonrpc: Literal["2.0"] = "2.0"
    error: JsonRpcErrorObject
    id: str | int | float | None


# A protocol message can be any of these
JsonRpcMessage = Union[JsonRpcRequest, JsonRpcResponse, JsonRpcErrorResponse]


# ── Serialization helpers ──────────────────────────────────────────────

def parse_request(raw: str | bytes) -> JsonRpcRequest:
    """Parse a raw JSON-RPC request string into a ``JsonRpcRequest``.

    Returns ``None`` for batch requests — callers should check for arrays
    themselves if batch support is desired.

    Raises :class:`~lithe_jsonrpc.errors.ParseError` on invalid JSON.
    """
    from .errors import ParseError

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(str(exc)) from exc

    if isinstance(data, list):
        # Batch — caller handles this case
        return _parse_batch(data)

    return JsonRpcRequest.model_validate(data)


def _parse_batch(data: list) -> list[JsonRpcRequest]:
    """Parse a batch of requests. Returns a list (may be empty → InvalidRequestError)."""
    from .errors import InvalidRequestError

    if not data:
        raise InvalidRequestError("Empty batch is invalid per JSON-RPC 2.0")
    return [JsonRpcRequest.model_validate(item) for item in data]


def format_response(
    result: Any,
    request_id: str | int | float | None,
) -> JsonRpcResponse:
    """Build a success response for the given request id."""
    return JsonRpcResponse(result=result, id=request_id)


def format_error(
    code: int,
    message: str,
    request_id: str | int | float | None,
    data: Any = None,
) -> JsonRpcErrorResponse:
    """Build an error response for the given request id."""
    return JsonRpcErrorResponse(
        error=JsonRpcErrorObject(code=code, message=message, data=data),
        id=request_id,
    )


def to_json(obj: BaseModel) -> str:
    """Serialize a Pydantic model to a JSON string.

    Uses ``exclude_none`` so notifications (id=None) don't emit ``"id": null``.
    """
    return obj.model_dump_json(exclude_none=True)


__all__ = [
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcErrorObject",
    "JsonRpcErrorResponse",
    "JsonRpcMessage",
    "parse_request",
    "format_response",
    "format_error",
    "to_json",
]
