from .base import (
    IOBackend,
    IOManager,
    IOTag,
    Direction,
    DataType,
    RegisterType,
    SignalType,
    to_device,
    from_device,
    pack_words,
    unpack_words,
)
from .modbus import ModbusBackend
from .opcua import OPCUABackend
from .openplc import OpenPLCBackend, openplc_to_modbus, openplc_location
from .virtual import VirtualBackend

# key -> (factory, default endpoint fields)
BACKEND_TYPES = {
    "Modbus TCP": ("modbus", {"host": "127.0.0.1", "port": 502}),
    "Modbus RTU": ("modbus-rtu", {"serial_port": "/dev/ttyUSB0", "baudrate": 19200}),
    "OPC UA": ("opcua", {"url": "opc.tcp://127.0.0.1:4840"}),
    "OpenPLC": ("openplc", {"host": "127.0.0.1", "port": 502, "http_port": 8080}),
    "Virtual (demo)": ("virtual", {}),
}


def create_backend(type_key, config):
    kind = BACKEND_TYPES[type_key][0]
    if kind == "modbus":
        return ModbusBackend({**config, "protocol": "tcp"})
    if kind == "modbus-rtu":
        return ModbusBackend({**config, "protocol": "rtu"})
    if kind == "opcua":
        return OPCUABackend(config)
    if kind == "openplc":
        return OpenPLCBackend(config)
    if kind == "virtual":
        return VirtualBackend(config)
    raise KeyError(f"unknown backend type '{type_key}'")


__all__ = [
    "IOBackend",
    "IOManager",
    "IOTag",
    "Direction",
    "DataType",
    "RegisterType",
    "SignalType",
    "ModbusBackend",
    "OPCUABackend",
    "OpenPLCBackend",
    "VirtualBackend",
    "BACKEND_TYPES",
    "create_backend",
    "openplc_to_modbus",
    "openplc_location",
    "to_device",
    "from_device",
    "pack_words",
    "unpack_words",
]
