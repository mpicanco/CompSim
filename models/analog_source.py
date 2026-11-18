from __future__ import annotations

from core.base import ProcessBlock
from core.ports import PortType


class AnalogSource(ProcessBlock):
    """Analog signal source.

    Writes a user-editable analog value to its signal output. Use it to feed a
    valve position, compressor speed or any signal input with a fixed (or
    hand-tuned) value.
    """

    block_type = "AnalogSource"
    category = "Signals"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_output("out", PortType.SIGNAL)
        self.config = {"value": 0.0}

    def update(self, dt):
        pass

    def calculate_outputs(self):
        self.outputs["out"].value = self.config["value"]
