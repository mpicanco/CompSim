from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from .ports import Port, PortDirection, PortType


class ProcessBlock(ABC):
    """Abstract parent class for every unit operation.

    Subclasses declare their input/output ports in ``__init__`` (via
    ``add_input``/``add_output``) and implement two methods:

    * ``update(dt)``           - advance internal state over one time step.
    * ``calculate_outputs()``  - write the output port values from inputs+state.

    The solver calls both once per march step, in graph execution order, then
    ``propagate()`` copies each output onto the connected input port.
    """

    block_type = "generic"
    category = "generic"
    # True when the block's material outputs can differ in composition from
    # its inlet (mixing, phase split); the config panel then lists each
    # output's own composition instead of just the inlet one.
    changes_composition = False

    def __init__(self, name=None):
        self.name = name or self.block_type
        self.instance_id = uuid4().hex[:8]
        self.inputs = {}
        self.outputs = {}
        self.states = {}
        self.config = {}
        self.position = (0.0, 0.0)

    # -- port helpers -------------------------------------------------------
    def add_input(self, name, port_type=PortType.MATERIAL) -> Port:
        port = Port(name, PortDirection.INPUT, port_type, owner=self)
        self.inputs[name] = port
        return port

    def add_output(self, name, port_type=PortType.MATERIAL) -> Port:
        port = Port(name, PortDirection.OUTPUT, port_type, owner=self)
        self.outputs[name] = port
        return port

    # -- interface ----------------------------------------------------------
    @abstractmethod
    def calculate_outputs(self):
        """Compute output port values from input values and internal state."""

    @abstractmethod
    def update(self, dt):
        """Advance internal state over one time step (no-op for algebraic units)."""

    def propagate(self) -> None:
        # ``None`` is propagated too, so a block that stops producing an
        # output does not leave a stale value on the downstream input.
        for out in self.outputs.values():
            if out.is_connected:
                out.connection.value = out.value

    def init_state(self) -> None:
        """(Re)initialise ``states`` and any internal memory from ``config``."""

    def reset(self) -> None:
        for port in list(self.inputs.values()) + list(self.outputs.values()):
            port.clear_runtime()
        self.states.clear()
        self.init_state()

    def config_changed(self, keys) -> None:
        """Called after the user edited the config keys ``keys``."""

    @property
    def is_stateful(self) -> bool:
        """True if the block integrates a differential state (capacity block)."""
        return False

    def __repr__(self) -> str:
        return f"<{self.block_type} '{self.name}' ({self.instance_id})>"


class CapacityBlock(ProcessBlock, ABC):
    """Stateful block integrating a differential variable (e.g. dP/dt, dM/dt).

    Capacity blocks are the algebraic-loop breakers: their state is a function
    of the previous time step, so a recycle stream feeding back into a vessel
    does not create a circular algebraic dependency inside a single march step.
    """

    @property
    def is_stateful(self) -> bool:
        return True
