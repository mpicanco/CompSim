from __future__ import annotations

from .graph import Graph
from .solver import Simulator


class SimulationController:
    """Qt-free facade owning the process graph and the dynamic solver.

    The GUI layer (main window, canvas, trends, I/O) talks to this object
    exclusively, keeping the simulation core independent of any UI toolkit.
    """

    def __init__(self, dt=1.0):
        self.graph = Graph()
        self.simulator = Simulator(self.graph, dt=dt)

    @property
    def dt(self):
        return self.simulator.dt

    @dt.setter
    def dt(self, value):
        self.simulator.dt = value

    def add_block(self, block):
        return self.graph.add_node(block)

    def remove_block(self, instance_id):
        self.graph.remove_node(instance_id)

    def add_edge(self, source_port, target_port):
        return self.graph.add_edge(source_port, target_port)

    def remove_edge(self, edge_id):
        self.graph.remove_edge(edge_id)

    def check_ready(self):
        """Pre-run sanity check; returns a list of problems (empty = ready)."""
        problems = []
        if not self.graph.nodes:
            problems.append("The flowsheet is empty.")
        for port in self.graph.unconnected_material_ports():
            kind = "inlet" if port.direction.value == "in" else "outlet"
            problems.append(f"{port.owner.name}: material {kind} '{port.name}' "
                            "is not connected")
        return problems

    def step(self):
        self.simulator.step()

    def reset(self):
        self.simulator.reset()
