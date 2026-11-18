from __future__ import annotations

from core.base import ProcessBlock


class StreamOut(ProcessBlock):
    """Sink / downstream boundary condition.

    Imposes a fixed boundary pressure (e.g. atmosphere) as back-pressure on its
    inlet so upstream flow elements can compute a pressure drop. Consumes the
    incoming stream.
    """

    block_type = "StreamOut"
    category = "Sources"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_input("in")
        self.config = {"pressure": 1.0e5}

    def update(self, dt):
        pass

    def calculate_outputs(self):
        self.inputs["in"].back_pressure = self.config["pressure"]
