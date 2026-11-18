from __future__ import annotations

from collections import deque
from uuid import uuid4

from .ports import Port, PortType


class Edge:
    """Directed connection from an output port to an input port."""

    def __init__(self, source: Port, target: Port):
        self.source = source
        self.target = target
        self.id = uuid4().hex[:8]

    @property
    def source_block(self):
        return self.source.owner

    @property
    def target_block(self):
        return self.target.owner

    def __repr__(self) -> str:
        return f"<Edge {self.source_block.name}.{self.source.name} -> {self.target_block.name}.{self.target.name}>"


class Graph:
    """Topology container: nodes (ProcessBlock) and directed edges (Port->Port).

    Provides the execution order used by the solver at every time step. Recycle
    (closed) loops are handled by computing strongly-connected components and
    breaking each cycle at stateful (capacity) blocks, which always march on
    their integrated state rather than a circular algebraic dependency.
    """

    def __init__(self):
        self._nodes = {}
        self._edges = {}

    @property
    def nodes(self):
        return list(self._nodes.values())

    @property
    def edges(self):
        return list(self._edges.values())

    def get_node(self, instance_id):
        return self._nodes.get(instance_id)

    def add_node(self, block):
        self._nodes[block.instance_id] = block
        return block

    def remove_node(self, instance_id) -> None:
        block = self._nodes.pop(instance_id, None)
        if block is None:
            return
        for port in list(block.inputs.values()) + list(block.outputs.values()):
            port.disconnect()
        for eid in list(self._edges):
            e = self._edges[eid]
            if e.source_block.instance_id == instance_id or e.target_block.instance_id == instance_id:
                del self._edges[eid]

    def add_edge(self, source_port: Port, target_port: Port) -> Edge:
        # each port carries a single link: drop edges already using either port
        for eid in [eid for eid, e in self._edges.items()
                    if e.source is source_port or e.target is target_port]:
            self.remove_edge(eid)
        source_port.connect(target_port)
        edge = Edge(source_port, target_port)
        self._edges[edge.id] = edge
        return edge

    def remove_edge(self, edge_id) -> None:
        edge = self._edges.pop(edge_id, None)
        if edge is not None:
            edge.source.disconnect()

    def find_edge(self, source_port: Port, target_port: Port):
        for e in self._edges.values():
            if e.source is source_port and e.target is target_port:
                return e
        return None

    # -- pre-run checks -----------------------------------------------------
    def unconnected_material_ports(self):
        """Material (stream) ports, inlets and outlets, left unconnected.

        Every material port must be connected before a run: an open inlet
        has no feed and an open outlet has nowhere to send its flow. Signal
        ports are optional (a block falls back to its configured value).
        """
        return [port
                for block in self.nodes
                for port in list(block.inputs.values()) + list(block.outputs.values())
                if port.port_type is PortType.MATERIAL and not port.is_connected]

    # -- execution order ----------------------------------------------------
    def _adjacency(self):
        adj = {n.instance_id: [] for n in self.nodes}
        for e in self._edges.values():
            s = e.source_block.instance_id
            t = e.target_block.instance_id
            if s != t:
                adj[s].append(t)
        return adj

    def _sccs(self):
        """Tarjan strongly-connected components."""
        adj = self._adjacency()
        index, lowlink, stack, on_stack, counter = {}, {}, [], set(), [0]
        result = []

        def strongconnect(v):
            index[v] = counter[0]
            lowlink[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            for w in adj.get(v, []):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])
            if lowlink[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    comp.append(w)
                    if w == v:
                        break
                result.append(comp)

        for v in adj:
            if v not in index:
                strongconnect(v)
        return result

    def execution_order(self):
        """Blocks ordered for one solver march.

        Condensation DAG is topologically sorted; cyclic SCCs are linearised by
        pushing stateful blocks first and then breaking remaining cycles.
        """
        by_id = {n.instance_id: n for n in self.nodes}
        if not by_id:
            return []

        sccs = self._sccs()
        scc_id = {v: i for i, comp in enumerate(sccs) for v in comp}

        adj = self._adjacency()
        cond_adj = {i: set() for i in range(len(sccs))}
        for u, vs in adj.items():
            for v in vs:
                if scc_id[u] != scc_id[v]:
                    cond_adj[scc_id[u]].add(scc_id[v])

        indeg = {i: 0 for i in range(len(sccs))}
        for u, vs in cond_adj.items():
            for v in vs:
                indeg[v] += 1

        q = deque(sorted(i for i in range(len(sccs)) if indeg[i] == 0))
        cond_order = []
        while q:
            u = q.popleft()
            cond_order.append(u)
            for v in sorted(cond_adj[u]):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        if len(cond_order) != len(sccs):
            cond_order = list(range(len(sccs)))

        order = []
        for ci in cond_order:
            order.extend(self._order_ids(set(sccs[ci])))
        return [by_id[i] for i in order]

    def _order_ids(self, id_set):
        """Kahn topological sort with cycle-breaking (stateful first)."""
        adj = self._adjacency()
        indeg = {i: 0 for i in id_set}
        for i in id_set:
            for t in adj.get(i, []):
                if t in id_set:
                    indeg[t] += 1

        q = deque(sorted(i for i in id_set if indeg[i] == 0))
        ordered, pending = [], set(id_set)

        while pending:
            if not q:
                cand = sorted(pending, key=lambda i: (not self._nodes[i].is_stateful, i))
                q.append(cand[0])
            i = q.popleft()
            if i not in pending:
                continue
            pending.remove(i)
            ordered.append(i)
            for t in adj.get(i, []):
                if t in id_set:
                    indeg[t] -= 1
                    if indeg[t] == 0 and t in pending:
                        q.append(t)
        return ordered
