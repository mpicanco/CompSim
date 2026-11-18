from __future__ import annotations

from .base import IOBackend, from_device, to_device


class VirtualBackend(IOBackend):
    """In-memory demo backend: mirrors writes back to reads.

    Useful for exercising the I/O manager and tag map without any hardware.
    """

    type = "virtual"

    def __init__(self, config):
        super().__init__(config)
        self._mem = {}

    def connect(self):
        self._connected = True
        self.status = "connected"

    def disconnect(self):
        self._connected = False
        self.status = "disconnected"

    @staticmethod
    def _key(tag):
        # keyed by address so an AO and an AI on the same point loop back
        return str(tag.address).strip() or tag.name

    def read(self, tag):
        raw = self._mem.get(self._key(tag), 0.0)
        return from_device(raw, tag)

    def write(self, tag, value):
        self._mem[self._key(tag)] = to_device(value, tag)
