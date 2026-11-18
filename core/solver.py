from __future__ import annotations


class Simulator:
    """Dynamic solver: advances the graph one time step at a time.

    The march at every ``dt``:

    1. compute the execution order (topological + recycle-aware),
    2. ``update(dt)`` each block (integrates stateful/capacity units),
    3. ``calculate_outputs()`` each block,
    4. ``propagate()`` pushes outputs onto the connected input ports.
    """

    def __init__(self, graph, dt=1.0):
        self.graph = graph
        self.dt = dt
        self.time = 0.0
        self.iteration = 0
        self.running = False
        self.last_order = []

    def step(self) -> None:
        order = self.graph.execution_order()
        self.last_order = order
        for block in order:
            block.update(self.dt)
            block.calculate_outputs()
            block.propagate()
        self.time += self.dt
        self.iteration += 1

    def run(self, n_steps: int) -> None:
        for _ in range(n_steps):
            self.step()

    def reset(self) -> None:
        self.time = 0.0
        self.iteration = 0
        self.last_order = []
        for block in self.graph.nodes:
            block.reset()
