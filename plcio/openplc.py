from __future__ import annotations

import re
import urllib.request

from .modbus import ModbusBackend
from .base import DataType, RegisterType, SignalType

_LOCATION_RE = re.compile(r"^%(QX|IX|QW|IW|MW)(\d+)(?:\.(\d+))?$")


def openplc_to_modbus(location):
    """Translate an OpenPLC I/O location to (register_type, 0-based address).

    OpenPLC Runtime default Modbus mapping:
      %QX{byte}.{bit}  -> coil            address = byte*8 + bit
      %IX{byte}.{bit}  -> discrete input  address = byte*8 + bit
      %IW{word}        -> input register  address = word
      %QW{word}        -> holding register address = word
      %MW{word}        -> holding register address = 1024 + word
    """
    m = _LOCATION_RE.match(location.strip())
    if not m:
        raise ValueError(f"unknown OpenPLC location '{location}'")
    prefix, num, bit = m.group(1), int(m.group(2)), m.group(3)
    if prefix == "QX":
        return RegisterType.COIL, num * 8 + (int(bit) if bit else 0)
    if prefix == "IX":
        return RegisterType.DISCRETE, num * 8 + (int(bit) if bit else 0)
    if prefix == "IW":
        return RegisterType.INPUT, num
    if prefix == "QW":
        return RegisterType.HOLDING, num
    if prefix == "MW":
        return RegisterType.HOLDING, 1024 + num
    raise ValueError(f"unknown OpenPLC location '{location}'")


def openplc_location(signal_type: SignalType, index: int = 0) -> str:
    """Default OpenPLC location for a signal class + index."""
    if signal_type is SignalType.AI:
        return f"%IW{index}"
    if signal_type is SignalType.AO:
        return f"%QW{index}"
    if signal_type is SignalType.DI:
        return f"%IX{index // 8}.{index % 8}"
    if signal_type is SignalType.DO:
        return f"%QX{index // 8}.{index % 8}"
    raise ValueError(f"unsupported signal type '{signal_type}'")


class OpenPLCBackend(ModbusBackend):
    """OpenPLC Runtime integration.

    Talks to the OpenPLC Runtime's built-in Modbus TCP server (port 502) using
    the native I/O location mapping, and exposes the runtime's HTTP control API
    (start/stop/status) on port 8080.

    OpenPLC word locations (%IW/%QW/%MW) are single 16-bit registers, so analog
    tags are exchanged as UINT16 (0..65535) unless the tag sets ``dtype``; use
    ``scale``/``offset`` to map engineering units onto the raw range.
    """

    type = "openplc"

    def __init__(self, config):
        super().__init__({**config, "protocol": "tcp"})
        self.host = config.get("host", "127.0.0.1")
        self.http_port = int(config.get("http_port", 8080))

    @staticmethod
    def _word_type(tag):
        return tag.dtype if tag.dtype is not None else DataType.UINT16

    def read(self, tag):
        reg, addr = openplc_to_modbus(tag.address)
        return self._read_at(tag, addr, reg, self._word_type(tag))

    def write(self, tag, value):
        reg, addr = openplc_to_modbus(tag.address)
        self._write_at(tag, addr, reg, value, self._word_type(tag))

    # -- runtime HTTP control ----------------------------------------------
    def _http(self, path, method="GET"):
        url = f"http://{self.host}:{self.http_port}{path}"
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode().strip()

    def runtime_status(self):
        return self._http("/runtime/status")

    def runtime_start(self):
        return self._http("/runtime/start", method="POST")

    def runtime_stop(self):
        return self._http("/runtime/stop", method="POST")
