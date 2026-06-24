"""编解码器抽象层。

Transports 可通过 :attr:`Transport.codec` 属性指定序列化格式，
框架通过 codec 而非硬编码 JSON 进行编解码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Codec(ABC):
    """JSON-RPC 消息序列化/反序列化的抽象编解码器。"""

    @abstractmethod
    def encode(self, obj: Any) -> bytes:
        """将 Python 对象编码为字节。"""
        ...

    @abstractmethod
    def decode(self, data: bytes) -> Any:
        """将字节解码为 Python 对象。"""
        ...


class JsonCodec(Codec):
    """默认 JSON 编解码器（``json.dumps`` / ``json.loads``）。"""

    def encode(self, obj: Any) -> bytes:
        import json

        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def decode(self, data: bytes) -> Any:
        import json

        return json.loads(data)


class MsgPackCodec(Codec):
    """MessagePack 编解码器（``msgpack.packb`` / ``msgpack.unpackb``）。

    需要安装 ``msgpack`` 包。
    """

    def encode(self, obj: Any) -> bytes:
        import msgpack

        return msgpack.packb(obj, use_bin_type=True)

    def decode(self, data: bytes) -> Any:
        import msgpack

        return msgpack.unpackb(data, raw=False)


__all__ = ["Codec", "JsonCodec", "MsgPackCodec"]
