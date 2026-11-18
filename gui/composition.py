from __future__ import annotations

"""Parsing / checking of ``{component: mole fraction}`` entries in the GUI."""

import ast

from PyQt6.QtWidgets import QMessageBox

from core.data import check_composition, composition_total_ok, normalize_composition


class CompositionCancelled(ValueError):
    """The user declined to normalise a composition that does not sum to 1."""


def parse_composition(text, label="composition"):
    """Parse a dict literal into ``{name: float}``; raises ValueError.

    Components that are not listed are taken as 0. Names are matched
    case-insensitively; a name that is not a known component is rejected,
    with the closest valid name suggested (see ``core.data.check_composition``).
    """
    try:
        value = ast.literal_eval(text) if isinstance(text, str) else text
    except (ValueError, SyntaxError):
        raise ValueError(f"{label}: not a valid {{component: fraction}} literal")
    return check_composition(value, label)


def confirm_composition(parent, value, label="composition"):
    """Check that ``value`` sums to 1; if not, ask the user to normalise.

    Returns the composition in GERG-2008 / ISO 20765 order. Raises
    ``CompositionCancelled`` when the user refuses normalisation.
    """
    total = sum(value.values())
    if not composition_total_ok(value):
        answer = QMessageBox.question(
            parent, "Normalise composition?",
            f"The {label} mole fractions add up to {total:.6g}, not 1.\n\n"
            "Components not listed are taken as 0.\n"
            "Normalise the fractions so they sum to 1?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            raise CompositionCancelled(f"{label}: fractions add up to {total:.6g}, not 1")
    # within tolerance (or accepted): scale to exactly 1
    return normalize_composition(value)
