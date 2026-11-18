"""Flowsheet save/load and the bundled example files.

Property files use the dedicated ``.sim`` file type (JSON content):

* ``blocks``  - ``key -> {type, name, pos, config}``; ``pos`` is the node's
  top-left corner on the canvas, ``config`` overrides the block defaults.
* ``edges``   - ``(source_key, output_port, target_key, input_port)``.
* ``charts``  - list of charts, each a list of ``(block_key, path, label)``
  pens (paths as in ``core.variables``).
* ``dt``      - solver time step [s].

Keys must match the block names so charts survive round-trips (instance ids
are regenerated on every load).
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QPointF

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

ATM = 101325.0  # Pa
AIR = {"nitrogen": 0.79, "oxygen": 0.21}


def list_examples():
    """Bundled example flowsheets, sorted from simple to complex by filename."""
    if not EXAMPLES_DIR.is_dir():
        return []
    return sorted(EXAMPLES_DIR.glob("*.sim"))


# -- serialization ---------------------------------------------------------
def flowsheet_to_spec(window):
    """Build a JSON-ready spec dict describing the flowsheet in ``window``."""
    scene = window.scene
    blocks = {}
    id2key = {}
    for block in window.controller.graph.nodes:
        item = scene.node_item(block.instance_id)
        if item is not None:
            pos = [item.pos().x(), item.pos().y()]
        else:
            pos = [0.0, 0.0]
        key = block.name
        id2key[block.instance_id] = key
        blocks[key] = {
            "type": block.block_type,
            "name": block.name,
            "pos": pos,
            "config": {k: v for k, v in block.config.items()},
        }

    edges = [
        [id2key[e.source_block.instance_id], e.source.name,
         id2key[e.target_block.instance_id], e.target.name]
        for e in window.controller.graph.edges
    ]

    charts = []
    for tile in window.trends.charts:
        pens = []
        for pen in tile.pens:
            key = id2key.get(pen["block_id"])
            if key is None:
                continue
            pens.append([key, list(pen["path"]), pen["label"]])
        if pens:
            charts.append(pens)

    return {
        "format": "comp-sim-flowsheet",
        "version": 1,
        "description": window.windowTitle(),
        "dt": window.controller.dt,
        "blocks": blocks,
        "edges": edges,
        "charts": charts,
    }


# -- loading ---------------------------------------------------------------
def load_spec(window, spec):
    """Replace the current flowsheet in ``window`` with ``spec``."""
    window.stop()
    scene = window.scene
    scene.clear_flowsheet()
    window.trends.clear_all()

    items = {}
    for bkey, b in spec["blocks"].items():
        item = scene.create_block(b["type"], QPointF(0, 0))
        block = item.block
        block.name = b["name"]
        block.config.update(b.get("config", {}))
        block.config_changed(list(b.get("config", {})))
        item.setPos(QPointF(*b["pos"]))
        items[bkey] = item

    for src, out_port, tgt, in_port in spec.get("edges", []):
        scene.create_edge(items[src].port_items[out_port], items[tgt].port_items[in_port])

    window.dt_spin.setValue(spec.get("dt", window.controller.dt))
    window.controller.reset()

    for pens in spec.get("charts", []):
        tile = window.trends.add_chart()
        for bkey, path, label in pens:
            tile.add_pen(items[bkey].block.instance_id, list(path), label)

    window._on_blocks_changed()
    scene.update()
    window.view.centerOn(scene.itemsBoundingRect().center())


def load_file(window, path):
    """Load a ``.sim`` flowsheet file into ``window``."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if spec.get("format") != "comp-sim-flowsheet":
        raise ValueError("not a CompSim flowsheet file")
    load_spec(window, spec)
    window.notify(f"Loaded flowsheet: {Path(path).name}")


def save_file(window, path):
    """Save the flowsheet in ``window`` to a ``.sim`` file."""
    Path(path).write_text(
        json.dumps(flowsheet_to_spec(window), indent=2), encoding="utf-8"
    )
    window.notify(f"Saved flowsheet: {Path(path).name}")


def close_flowsheet(window):
    """Fully clear the workspace: blocks, streams, charts and PLC tags."""
    window.stop()
    window.scene.clear_flowsheet()
    window.trends.clear_all()
    window.controller.reset()
    window.controller.dt = 1.0
    window.dt_spin.setValue(1.0)
    window.ioplc.clear_workspace()
    window._on_blocks_changed()
    window.view.centerOn(QPointF(0, 0))
    window.notify("Flowsheet closed")
