from __future__ import annotations

from core.base import ProcessBlock
from core.ports import MaterialStream


class Mixer(ProcessBlock):
    """Adiabatic stream mixer (N inputs, 1 output).

    Combines mass flows and compositions; outlet enthalpy is the flow-weighted
    average of the inlet enthalpies (Step 2).
    """

    block_type = "Mixer"
    category = "Equipment"

    def __init__(self, name=None, n_inputs=2):
        super().__init__(name)
        self.n_inputs = n_inputs
        for i in range(1, n_inputs + 1):
            self.add_input(f"in{i}")
        self.add_output("out")

    def update(self, dt):
        pass

    def calculate_outputs(self):
        streams = [self.inputs[f"in{i}"].value for i in range(1, self.n_inputs + 1)]
        streams = [s for s in streams if s is not None]
        if not streams:
            self.outputs["out"].value = None
            return

        total_mass = sum(s.mass_flow for s in streams)
        if total_mass <= 0.0:
            out = streams[0].copy()
            out.mass_flow = 0.0
            self.outputs["out"].value = out
            return

        comps = set()
        for s in streams:
            comps.update(s.composition)
        composition = {}
        for c in comps:
            numerator = sum(s.mass_flow * s.composition.get(c, 0.0) for s in streams)
            composition[c] = numerator / total_mass

        out = MaterialStream(
            pressure=max(s.pressure for s in streams),
            temperature=sum(s.mass_flow * s.temperature for s in streams) / total_mass,
            mass_flow=total_mass,
            composition=composition,
        )
        self.outputs["out"].value = out
