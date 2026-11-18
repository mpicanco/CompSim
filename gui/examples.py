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
from PyQt6.QtWidgets import QMessageBox

from core.data import check_composition, composition_total_ok, normalize_composition
from core.thermo import EOS_NAMES

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
def _is_composition_key(key):
    return key == "composition" or key.endswith("_composition")


def _check_config(config, where, notes):
    """Check the compositions and EOS name in one block config, in place.

    Compositions are checked like an entry in the config panel and stored with
    canonical names, normalised and in GERG-2008 order. Raises ValueError for
    an entry the panel would reject; appends a note for each composition that
    had to be normalised.
    """
    for key, value in config.items():
        label = f"{where}: {key}"
        if _is_composition_key(key):
            z = check_composition(value, label)
            if not composition_total_ok(z):
                notes.append(f"{label} added up to {sum(z.values()):.6g}; normalised to 1")
            config[key] = normalize_composition(z)
        elif key == "eos" and value not in EOS_NAMES:
            raise ValueError(f"{label}: unknown EOS {value!r}. Available: "
                             + ", ".join(EOS_NAMES))
        elif isinstance(value, dict):
            _check_config(value, label, notes)


def check_spec(spec):
    """Validate the block configs of a loaded ``spec``; returns notes.

    Hand-edited files get the same composition checks as the config panels.
    Raises ValueError naming the block and entry at fault.
    """
    notes = []
    for bkey, b in spec.get("blocks", {}).items():
        config = b.get("config", {})
        if not isinstance(config, dict):
            raise ValueError(f"block '{b.get('name', bkey)}': config must be a dict")
        _check_config(config, f"block '{b.get('name', bkey)}'", notes)
    return notes


def load_spec(window, spec):
    """Replace the current flowsheet in ``window`` with ``spec``.

    The spec is checked first (see ``check_spec``), so an invalid file leaves
    the current flowsheet untouched. Returns the check notes.
    """
    notes = check_spec(spec)
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
    return notes


def load_file(window, path):
    """Load a ``.sim`` flowsheet file into ``window``."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if spec.get("format") != "comp-sim-flowsheet":
        raise ValueError("not a CompSim flowsheet file")
    notes = load_spec(window, spec)
    window.notify(f"Loaded flowsheet: {Path(path).name}")
    if notes:
        QMessageBox.warning(
            window, "Compositions normalised",
            f"{Path(path).name}: some compositions did not add up to 1 and were "
            "normalised. Save the flowsheet to keep the corrected values.\n\n"
            + "\n".join(notes))


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
