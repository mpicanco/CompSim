from __future__ import annotations

from core.base import ProcessBlock


class Divider(ProcessBlock):
    """Stream divider / splitter (1 input, N outputs).

    Splits the incoming stream by specified mass-flow fractions; composition and
    thermodynamic state are preserved across each branch.
    """

    block_type = "Divider"
    category = "Equipment"

    def __init__(self, name=None, n_outputs=2):
        super().__init__(name)
        self.n_outputs = n_outputs
        self.add_input("in")
        for i in range(1, n_outputs + 1):
            self.add_output(f"out{i}")
        self.config = {"fractions": [0.5] * n_outputs}

    def update(self, dt):
        pass

    def calculate_outputs(self):
        inlet = self.inputs["in"].value
        fractions = self.config["fractions"]
        if inlet is None:
            for i in range(1, self.n_outputs + 1):
                self.outputs[f"out{i}"].value = None
            return
        fr = [max(0.0, float(fractions[i])) if i < len(fractions) else 0.0
              for i in range(self.n_outputs)]
        total = sum(fr)
        fr = [f / total for f in fr] if total > 0.0 else [0.0] * self.n_outputs
        for i in range(1, self.n_outputs + 1):
            out = inlet.copy()
            out.mass_flow = inlet.mass_flow * fr[i - 1]
            self.outputs[f"out{i}"].value = out
