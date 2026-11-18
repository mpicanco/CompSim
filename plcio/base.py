from __future__ import annotations

import struct
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    IN = "in"    # device -> simulation (read from PLC, write into a sim variable)
    OUT = "out"  # simulation -> device (read a sim variable, write to PLC)


class DataType(Enum):
    BOOL = "bool"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    FLOAT32 = "float32"
    FLOAT64 = "float64"


class RegisterType(Enum):
    COIL = "coil"
    DISCRETE = "discrete"
    INPUT = "input"
    HOLDING = "holding"


class SignalType(Enum):
    """PLC signal class (IEC 61131-3 / OpenPLC terminology).

    Encodes both the direction and the data kind:
      * AI - analog input    (field -> sim, float, e.g. pressure transmitter)
      * AO - analog output   (sim -> field, float, e.g. valve opening)
      * DI - digital input   (field -> sim, bool)
      * DO - digital output  (sim -> field, bool)
    """

    AI = "ai"
    AO = "ao"
    DI = "di"
    DO = "do"

    @property
    def direction(self) -> Direction:
        return Direction.IN if self in (SignalType.AI, SignalType.DI) else Direction.OUT

    @property
    def data_type(self) -> DataType:
        return DataType.BOOL if self in (SignalType.DI, SignalType.DO) else DataType.FLOAT32

    @property
    def register_type(self) -> RegisterType:
        return {
            SignalType.AI: RegisterType.INPUT,
            SignalType.AO: RegisterType.HOLDING,
            SignalType.DI: RegisterType.DISCRETE,
            SignalType.DO: RegisterType.COIL,
        }[self]

    @property
    def is_analog(self) -> bool:
        return self in (SignalType.AI, SignalType.AO)

    @property
    def label(self) -> str:
        return {
            SignalType.AI: "AI  (Analog Input)",
            SignalType.AO: "AO  (Analog Output)",
            SignalType.DI: "DI  (Digital Input)",
            SignalType.DO: "DO  (Digital Output)",
        }[self]

    @property
    def short(self) -> str:
        return self.value.upper()


@dataclass
class IOTag:
    """A single mapped signal between a sim variable and a field-device point.

    The signal class (``signal_type``) determines the direction, data type and
    default Modbus register table; ``address`` is the device point (Modbus
    register, OPC UA NodeId, or OpenPLC location such as %IW0 / %QW0).
    """

    name: str
    signal_type: SignalType
    backend: str
    address: str = ""
    unit_id: int = 1
    scale: float = 1.0
    offset: float = 0.0
    block_id: str = ""
    path: tuple = ()
    dtype: DataType | None = None   # overrides the signal type's default

    @property
    def direction(self) -> Direction:
        return self.signal_type.direction

    @property
    def data_type(self) -> DataType:
        return self.dtype if self.dtype is not None else self.signal_type.data_type

    @property
    def register_type(self) -> RegisterType:
        return self.signal_type.register_type


# --- engineering <-> raw scaling -------------------------------------------
def to_device(value, tag):
    """engineering value -> raw value handed to the device."""
    return (value - tag.offset) / tag.scale if tag.scale else value


def from_device(raw, tag):
    """raw value from the device -> engineering value."""
    return raw * tag.scale + tag.offset


def register_count(data_type):
    return {DataType.FLOAT32: 2, DataType.INT32: 2, DataType.FLOAT64: 4}.get(data_type, 1)


def pack_words(value, data_type):
    if data_type is DataType.FLOAT32:
        return list(struct.unpack(">HH", struct.pack(">f", float(value))))
    if data_type is DataType.FLOAT64:
        return list(struct.unpack(">HHHH", struct.pack(">d", float(value))))
    if data_type is DataType.INT32:
        v = max(-2 ** 31, min(2 ** 31 - 1, int(round(value))))
        return list(struct.unpack(">HH", struct.pack(">i", v)))
    if data_type is DataType.INT16:
        v = max(-32768, min(32767, int(round(value))))
        return [v & 0xFFFF]
    if data_type is DataType.BOOL:
        return [1 if value else 0]
    # UINT16: saturate instead of wrapping around
    return [max(0, min(0xFFFF, int(round(value))))]


def unpack_words(words, data_type):
    if data_type is DataType.FLOAT32:
        return struct.unpack(">f", struct.pack(">HH", *words[:2]))[0]
    if data_type is DataType.FLOAT64:
        return struct.unpack(">d", struct.pack(">HHHH", *words[:4]))[0]
    if data_type is DataType.INT32:
        return struct.unpack(">i", struct.pack(">HH", *words[:2]))[0]
    if data_type is DataType.INT16:
        v = words[0]
        return v - 0x10000 if v & 0x8000 else v
    return words[0]


class IOBackend(ABC):
    """Abstract fieldbus/driver. Each backend owns one transport connection."""

    type = "base"

    def __init__(self, config):
        self.config = config
        self.name = config.get("name", self.type)
        self._connected = False
        self.status = "idle"
        # False after a manual disconnect: the scan thread will not reconnect
        self.enabled = True
        # serialises transport access between the scan thread and the GUI
        self.lock = threading.RLock()

    @property
    def is_connected(self):
        return self._connected

    @abstractmethod
    def connect(self):
        """Open the transport; raise on failure."""

    @abstractmethod
    def disconnect(self):
        """Close the transport."""

    @abstractmethod
    def read(self, tag: IOTag):
        """Read one point; returns engineering value."""

    @abstractmethod
    def write(self, tag: IOTag, value):
        """Write one point; ``value`` is engineering value."""


class IOManager:
    """Owns backends and tags; runs device I/O on a background thread.

    Threading model:
      * the GUI pushes engineering values for AO/DO tags via ``set_output``,
      * the GUI pulls engineering values for AI/DI tags via ``get_input``,
      * the background thread performs the actual network I/O.
    Buffers are lock-protected; sim objects are only touched by the GUI thread.
    """

    def __init__(self, scan_interval=0.5):
        self.backends = {}
        self.tags = []
        self.scan_interval = scan_interval
        self._stop = threading.Event()
        self._thread = None
        self._inbuf = {}
        self._outbuf = {}
        self._lock = threading.Lock()
        self.on_log = None

    def _log(self, msg):
        if self.on_log is not None:
            self.on_log(msg)

    # -- configuration ------------------------------------------------------
    def add_backend(self, backend):
        old = self.backends.get(backend.name)
        if old is not None:
            self._safe_disconnect(old)
        self.backends = {**self.backends, backend.name: backend}
        return backend

    @staticmethod
    def _safe_disconnect(backend):
        with backend.lock:
            try:
                backend.disconnect()
            except Exception:
                pass

    def remove_backend(self, name):
        backend = self.backends.get(name)
        if backend is not None:
            backend.enabled = False
            self._safe_disconnect(backend)
            # replace (not mutate) so the scan thread's iteration stays valid
            self.backends = {k: v for k, v in self.backends.items() if k != name}
        self.tags = [t for t in self.tags if t.backend != name]

    def add_tag(self, tag):
        self.tags = [t for t in self.tags if t.name != tag.name]
        self.tags.append(tag)

    def remove_tag(self, name):
        self.tags = [t for t in self.tags if t.name != name]
        with self._lock:
            self._inbuf.pop(name, None)
            self._outbuf.pop(name, None)

    def get_backend(self, name):
        return self.backends.get(name)

    # -- buffers (GUI thread) ----------------------------------------------
    def set_output(self, name, value):
        with self._lock:
            self._outbuf[name] = value

    def get_input(self, name):
        with self._lock:
            return self._inbuf.get(name)

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="io-scan")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        for b in list(self.backends.values()):
            self._safe_disconnect(b)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._scan()
            except Exception as e:
                self._log(f"scan error: {e}")
            self._stop.wait(self.scan_interval)

    def _scan(self):
        for b in list(self.backends.values()):
            if self._stop.is_set():
                return
            if not b.enabled:
                continue
            with b.lock:
                self._scan_backend(b)

    def _scan_backend(self, b):
        if not b.enabled:
            return
        if not b.is_connected:
            try:
                b.connect()
                self._log(f"{b.name}: connected")
            except Exception as e:
                b.status = f"error: {e}"
                try:
                    b.disconnect()   # release half-open transports/threads
                except Exception:
                    pass
                return
        tags = [t for t in self.tags if t.backend == b.name]
        for t in tags:
            try:
                if t.direction is Direction.IN:
                    v = b.read(t)
                    with self._lock:
                        self._inbuf[t.name] = v
                else:
                    with self._lock:
                        v = self._outbuf.get(t.name)
                    if v is not None:
                        b.write(t, v)
                b.status = "ok"
            except Exception as e:
                b.status = f"error: {e}"
                if not b.is_connected:
                    self._log(f"{b.name}: connection lost ({e})")
                    return
