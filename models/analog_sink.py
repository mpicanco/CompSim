from __future__ import annotations

from core.base import ProcessBlock
from core.ports import PortType


class AnalogSink(ProcessBlock):
    """Analog signal display.

    Reads the analog value on its signal input and exposes it as ``value`` so
    the node can display it live (e.g. vessel level, valve position).
    """

    block_type = "AnalogSink"
    category = "Signals"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_input("in", PortType.SIGNAL)
        self.init_state()

    def init_state(self):
        self.states["value"] = None

    def update(self, dt):
        pass

    def calculate_outputs(self):
        self.states["value"] = self.inputs["in"].value
