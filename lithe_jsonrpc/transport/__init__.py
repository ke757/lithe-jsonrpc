"""Transport abstraction — interface only.

Concrete transports (stdio, WebSocket, etc.) live in the application
layer (e.g. ``app/device_provider/transports/``) and implement the
:class:`Transport` ABC defined here.
"""

from .base import Transport

__all__ = ["Transport"]
