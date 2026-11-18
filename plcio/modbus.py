from __future__ import annotations

import inspect

from .base import (
    IOBackend,
    RegisterType,
    to_device,
    from_device,
    pack_words,
    unpack_words,
    register_count,
)


def _unit_kwarg(method):
    """Name of the unit-id keyword: ``device_id`` (pymodbus >= 3.10) or ``slave``."""
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return "device_id"
    for name in ("device_id", "slave", "unit"):
        if name in params:
            return name
    return "device_id"


class ModbusBackend(IOBackend):
    """Modbus TCP / RTU client (via pymodbus 3.x).

    config keys: host, port (TCP) or serial_port/baudrate (RTU), protocol.
    Plain numeric addresses are 0-based protocol addresses; Modicon-style
    addresses are 1-based (``40001`` / ``4x0001`` / ``hr1`` -> holding 0).
    The table is selected by the tag's signal type (AI -> input register,
    AO -> holding register, DI -> discrete, DO -> coil).
    """

    type = "modbus"

    def __init__(self, config):
        super().__init__(config)
        self.protocol = config.get("protocol", "tcp")
        self.host = config.get("host", "127.0.0.1")
        self.port = int(config.get("port", 502))
        self.client = None
        self._unit_kw = "device_id"

    def _endpoint(self):
        if self.protocol == "rtu":
            return f"{self.config.get('serial_port', '/dev/ttyUSB0')}@{self.config.get('baudrate', 19200)}"
        return f"{self.host}:{self.port}"

    def connect(self):
        from pymodbus.client import ModbusTcpClient, ModbusSerialClient

        if self.protocol == "rtu":
            # RTU framing is the default for ModbusSerialClient in pymodbus 3.x
            self.client = ModbusSerialClient(
                port=self.config.get("serial_port", "/dev/ttyUSB0"),
                baudrate=int(self.config.get("baudrate", 19200)),
                timeout=3,
            )
        else:
            self.client = ModbusTcpClient(self.host, port=self.port, timeout=3)
        self._unit_kw = _unit_kwarg(self.client.read_coils)
        if not self.client.connect():
            self.client.close()
            self.client = None
            raise ConnectionError(f"cannot connect to {self._endpoint()}")
        self._connected = True
        self.status = "connected"

    def disconnect(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self._connected = False
        self.status = "disconnected"

    # -- address parsing ----------------------------------------------------
    _PREFIXES = {
        "4x": RegisterType.HOLDING, "hr": RegisterType.HOLDING,
        "3x": RegisterType.INPUT, "ir": RegisterType.INPUT,
        "1x": RegisterType.DISCRETE, "di": RegisterType.DISCRETE,
        "0x": RegisterType.COIL, "co": RegisterType.COIL,
    }
    _MODICON = {"4": RegisterType.HOLDING, "3": RegisterType.INPUT,
                "1": RegisterType.DISCRETE, "0": RegisterType.COIL}

    @classmethod
    def _addr(cls, tag):
        """0-based protocol address of ``tag``; raises ValueError if malformed."""
        s = str(tag.address).strip().lower()
        if not s:
            raise ValueError(f"tag '{tag.name}' has no address")
        if s[:2] in cls._PREFIXES:
            n = int(s[2:].lstrip(":"))
            if n < 1:
                raise ValueError(f"1-based address expected in '{tag.address}'")
            return n - 1
        if (s.isdigit() and len(s) in (5, 6)
                and cls._MODICON.get(s[0]) is tag.register_type):
            # Modicon notation: 40001 / 400001 -> holding register 0
            return int(s[1:]) - 1
        n = int(s)
        if n < 0:
            raise ValueError(f"negative address '{tag.address}'")
        return n

    def read(self, tag):
        return self._read_at(tag, self._addr(tag), tag.register_type)

    def write(self, tag, value):
        self._write_at(tag, self._addr(tag), tag.register_type, value)

    # -- transport -----------------------------------------------------------
    def _call(self, fn, *args, **kwargs):
        if self.client is None:
            self._connected = False
            raise ConnectionError("not connected")
        try:
            rr = fn(*args, **kwargs)
        except Exception:
            if not getattr(self.client, "connected", False):
                self.disconnect()   # let the scan thread reconnect
            raise
        if rr is None or rr.isError():
            raise IOError(f"Modbus error response: {rr}")
        return rr

    def _read_at(self, tag, addr, register_type, data_type=None):
        data_type = data_type or tag.data_type
        unit = {self._unit_kw: tag.unit_id}
        c = self.client
        if register_type is RegisterType.COIL:
            rr = self._call(c.read_coils, addr, count=1, **unit)
            raw = bool(rr.bits[0])
        elif register_type is RegisterType.DISCRETE:
            rr = self._call(c.read_discrete_inputs, addr, count=1, **unit)
            raw = bool(rr.bits[0])
        elif register_type is RegisterType.INPUT:
            rr = self._call(c.read_input_registers, addr, count=register_count(data_type), **unit)
            raw = unpack_words(rr.registers, data_type)
        else:
            rr = self._call(c.read_holding_registers, addr, count=register_count(data_type), **unit)
            raw = unpack_words(rr.registers, data_type)
        return from_device(raw, tag)

    def _write_at(self, tag, addr, register_type, value, data_type=None):
        data_type = data_type or tag.data_type
        unit = {self._unit_kw: tag.unit_id}
        raw = to_device(value, tag)
        c = self.client
        if register_type is RegisterType.COIL:
            self._call(c.write_coil, addr, bool(raw), **unit)
        elif register_type is RegisterType.HOLDING:
            self._call(c.write_registers, addr, pack_words(raw, data_type), **unit)
        else:
            raise ValueError(f"{register_type} is read-only")
