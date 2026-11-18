from __future__ import annotations

"""Shared helpers to list, read and write process variables.

A *path* is a tuple identifying a value inside a block:
    ("state", key)                       integrated state variable
    ("config", key)                      configuration parameter
    ("port_out", name, field)            output material field (pressure/temperature/mass_flow)
    ("port_in",  name, field)            input material field
    ("signal_in", name)                  scalar input signal port
    ("signal_out", name)                 scalar output signal port
"""

import numbers

_MATERIAL_FIELDS = ("pressure", "temperature", "mass_flow")


def is_scalar(value):
    """True for values that can be plotted / exchanged with a PLC."""
    return isinstance(value, numbers.Real)


def _scalar_or_unset(value):
    return value is None or is_scalar(value)


def _material_get(stream, field):
    return getattr(stream, field, None) if stream is not None else None


def block_variables(block):
    """Readable variables (display, path)."""
    out = []
    for key, value in block.states.items():
        if _scalar_or_unset(value):
            out.append((f"{block.name}: {key}", ("state", key)))
    for name in block.outputs:
        if block.outputs[name].port_type.name == "SIGNAL":
            out.append((f"{block.name}.{name}", ("signal_out", name)))
        else:
            for field in _MATERIAL_FIELDS:
                out.append((f"{block.name}.{name}.{field}", ("port_out", name, field)))
    for name in block.inputs:
        if block.inputs[name].port_type.name == "SIGNAL":
            out.append((f"{block.name}.{name}", ("signal_in", name)))
        else:
            for field in _MATERIAL_FIELDS:
                out.append((f"{block.name}.{name}.{field}", ("port_in", name, field)))
    for key, value in block.config.items():
        if is_scalar(value):
            out.append((f"{block.name}: cfg.{key}", ("config", key)))
    return out


def writable_variables(block):
    """Variables the outside world may write into (config, state, signal inputs)."""
    out = []
    for key, value in block.states.items():
        if is_scalar(value):
            out.append((f"{block.name}: {key}", ("state", key)))
    for name, port in block.inputs.items():
        if port.port_type.name == "SIGNAL":
            out.append((f"{block.name}.{name}", ("signal_in", name)))
    for key, value in block.config.items():
        if is_scalar(value):
            out.append((f"{block.name}: cfg.{key}", ("config", key)))
    return out


def resolve(block, path):
    kind = path[0]
    if kind == "state":
        return block.states.get(path[1])
    if kind == "config":
        return block.config.get(path[1])
    if kind == "port_out":
        return _material_get(block.outputs[path[1]].value, path[2])
    if kind == "port_in":
        return _material_get(block.inputs[path[1]].value, path[2])
    if kind == "signal_in":
        return block.inputs[path[1]].value
    if kind == "signal_out":
        return block.outputs[path[1]].value
    return None


def apply(block, path, value):
    """Write ``value`` into ``block``; refuses to overwrite non-numeric data."""
    kind = path[0]
    if not is_scalar(value):
        return False
    try:
        if kind == "state":
            if not _scalar_or_unset(block.states.get(path[1])):
                return False
            block.states[path[1]] = value
        elif kind == "config":
            current = block.config[path[1]]
            if not is_scalar(current):
                return False
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int):
                value = int(round(value))
            else:
                value = float(value)
            block.config[path[1]] = value
        elif kind == "signal_in":
            block.inputs[path[1]].value = value
        else:
            return False
        return True
    except (KeyError, IndexError):
        return False
