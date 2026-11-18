from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PortDirection(Enum):
    INPUT = "in"
    OUTPUT = "out"


class PortType(Enum):
    MATERIAL = "material"
    SIGNAL = "signal"
    ENERGY = "energy"
    POWER = "power"


@dataclass
class MaterialStream:
    """Thermodynamic + flow state carried along material connections (SI units)."""

    pressure: float = 101325.0       # Pa
    temperature: float = 293.15      # K
    mass_flow: float = 0.0           # kg/s
    composition: dict = field(default_factory=dict)  # {component: mole_fraction}
    phase: str = "vapour"

    def copy(self) -> "MaterialStream":
        return MaterialStream(
            pressure=self.pressure,
            temperature=self.temperature,
            mass_flow=self.mass_flow,
            composition=dict(self.composition),
            phase=self.phase,
        )


class Port:
    """Connection point of a process block.

    An output port propagates its ``value`` downstream through a connection to
    exactly one input port. Values are swapped during the solver march, not
    copied by reference, so each block owns a fresh state per step.
    """

    def __init__(self, name, direction, port_type=PortType.MATERIAL, owner=None):
        self.name = name
        self.direction = direction
        self.port_type = port_type
        self.owner = owner
        self.connection = None
        self.value = None
        # Pressure imposed on this (input) port by its owner, read by the
        # upstream flow element as its downstream pressure.
        self.back_pressure = None
        # Mass flow [kg/s] a downstream flow element draws through this
        # (input) port, read by the upstream pressure node (vessel/source).
        self.flow_demand = None

    def clear_runtime(self) -> None:
        """Drop values computed during the march (keeps the connection)."""
        self.value = None
        self.back_pressure = None
        self.flow_demand = None

    @property
    def is_connected(self) -> bool:
        return self.connection is not None

    def connect(self, other: "Port") -> None:
        # a port links to exactly one peer: release any previous link first
        if self.connection is not None and self.connection is not other:
            self.disconnect()
        if other.connection is not None and other.connection is not self:
            other.disconnect()
        self.connection = other
        other.connection = self

    def disconnect(self) -> None:
        other = self.connection
        self.connection = None
        if other is not None:
            other.connection = None
        # stale values must not keep feeding the block after the link is gone
        for port in (self, other):
            if port is not None:
                port.back_pressure = None
                port.flow_demand = None
                if port.direction is PortDirection.INPUT:
                    port.value = None

    def __repr__(self) -> str:
        owner = self.owner.name if self.owner is not None else "?"
        return f"<Port {owner}.{self.name} ({self.direction.value}/{self.port_type.value})>"
