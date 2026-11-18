from __future__ import annotations

from core.base import ProcessBlock
from core.ports import MaterialStream
from core.thermo import get_eos


class Mixer(ProcessBlock):
    """Adiabatic stream mixer (N inputs, 1 output).

    Combines mass flows and compositions. Mole fractions are blended on a
    molar-flow basis (``F = m_dot / M`` with ``M`` from the selected EOS);
    outlet temperature is the mass-flow-weighted average of the inlets.
    """

    block_type = "Mixer"
    changes_composition = True
    category = "Equipment"

    def __init__(self, name=None, n_inputs=2):
        super().__init__(name)
        self.n_inputs = n_inputs
        for i in range(1, n_inputs + 1):
            self.add_input(f"in{i}")
        self.add_output("out")
        self.config = {"eos": "Ideal Gas"}

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

        # mole fractions must be weighted by molar flow, not mass flow
        eos = get_eos(self.config.get("eos", "Ideal Gas"))
        molar = []
        for s in streams:
            M = eos.molar_mass(s.composition) if s.composition else 0.0
            molar.append(s.mass_flow / M if M > 0.0 else 0.0)
        total_molar = sum(molar)

        comps = set()
        for s in streams:
            comps.update(s.composition)
        composition = {}
        if total_molar > 0.0:
            for c in comps:
                composition[c] = sum(F * s.composition.get(c, 0.0)
                                     for F, s in zip(molar, streams)) / total_molar
        else:
            composition = dict(streams[0].composition)

        out = MaterialStream(
            pressure=max(s.pressure for s in streams),
            temperature=sum(s.mass_flow * s.temperature for s in streams) / total_mass,
            mass_flow=total_mass,
            composition=composition,
        )
        self.outputs["out"].value = out
