from __future__ import annotations

from core.base import ProcessBlock


class CheckValve(ProcessBlock):
    """Non-return valve.

    Passes flow only when the upstream pressure exceeds the downstream pressure
    by the cracking pressure; otherwise the valve closes and blocks reverse
    flow (outlet mass flow is zero). The downstream pressure is read from the
    back-pressure imposed by the connected pressure node (vessel, valve, ...),
    the same way control valves read theirs.
    """

    block_type = "CheckValve"
    category = "Equipment"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_input("in")
        self.add_output("out")
        self.config = {"cracking_pressure": 0.0}

    def update(self, dt):
        pass

    def is_open(self, inlet):
        """True when the upstream pressure opens the valve against downstream."""
        out_port = self.outputs["out"]
        if not out_port.is_connected or out_port.connection.back_pressure is None:
            return True  # no downstream pressure known: nothing to block against
        cracking = float(self.config.get("cracking_pressure", 0.0))
        return inlet.pressure > out_port.connection.back_pressure + cracking

    def calculate_outputs(self):
        inlet = self.inputs["in"].value
        if inlet is None:
            self.outputs["out"].value = None
            return
        out = inlet.copy()
        if not self.is_open(inlet):
            out.mass_flow = 0.0  # closed: no flow, reverse or forward
        self.outputs["out"].value = out
