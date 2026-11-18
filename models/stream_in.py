from __future__ import annotations

from core.base import ProcessBlock
from core.ports import MaterialStream


class StreamIn(ProcessBlock):
    """Source boundary condition.

    Imposes a fixed material state (composition, P, T, mass flow) and an EOS.
    Air and natural-gas preset compositions are available via ``config``.
    """

    block_type = "StreamIn"
    category = "Sources"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_output("out")
        self.config = {
            "composition": {"methane": 1.0},
            "pressure": 1.0e5,
            "temperature": 293.15,
            "mass_flow": 1.0,
            "eos": "Ideal Gas",
        }

    def update(self, dt):
        pass

    def calculate_outputs(self):
        # Pressure boundary: when the downstream element is pressure-driven
        # (e.g. a valve) it sets ``flow_demand`` and that flow is delivered;
        # otherwise the configured mass flow is imposed.
        out_port = self.outputs["out"]
        mass_flow = self.config["mass_flow"]
        if out_port.is_connected and out_port.connection.flow_demand is not None:
            mass_flow = out_port.connection.flow_demand
        out_port.value = MaterialStream(
            pressure=self.config["pressure"],
            temperature=self.config["temperature"],
            mass_flow=mass_flow,
            composition=dict(self.config["composition"]),
        )
