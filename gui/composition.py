from __future__ import annotations

"""Parsing / checking of ``{component: mole fraction}`` entries in the GUI."""

import ast
import difflib

from PyQt6.QtWidgets import QMessageBox

from core.data import COMPOSITION_SUM_TOL, KNOWN_COMPONENTS, sort_composition


class CompositionCancelled(ValueError):
    """The user declined to normalise a composition that does not sum to 1."""


def parse_composition(text, label="composition"):
    """Parse a dict literal into ``{name: float}``; raises ValueError.

    Components that are not listed are taken as 0. Names are matched
    case-insensitively; a name that is not a known component is rejected
    (with the closest valid name suggested) instead of silently being given
    air-like properties.
    """
    try:
        value = ast.literal_eval(text) if isinstance(text, str) else text
    except (ValueError, SyntaxError):
        raise ValueError(f"{label}: not a valid {{component: fraction}} literal")
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label}: expected a non-empty {{component: fraction}} dict")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
               for v in value.values()):
        raise ValueError(f"{label}: fractions must be non-negative numbers")
    if sum(value.values()) <= 0:
        raise ValueError(f"{label}: fractions must not all be zero")
    out = {}
    for k, v in value.items():
        name = " ".join(str(k).split()).lower()
        if name not in KNOWN_COMPONENTS:
            raise ValueError(f"{label}: {_unknown_message(str(k))}")
        if name in out:
            raise ValueError(f"{label}: component '{name}' is listed twice")
        out[name] = float(v)
    return out


# common shorthands mapped to the name the user most likely meant
_SHORTHANDS = {
    "c1": "methane", "ch4": "methane", "c2": "ethane", "c2h6": "ethane",
    "c3": "propane", "c3h8": "propane", "nc4": "n-butane", "ic4": "i-butane",
    "isobutane": "i-butane", "nc5": "n-pentane", "ic5": "i-pentane",
    "isopentane": "i-pentane", "nc6": "n-hexane", "n2": "nitrogen",
    "o2": "oxygen", "co2": "carbon dioxide", "carbondioxide": "carbon dioxide",
    "co": "carbon monoxide", "carbonmonoxide": "carbon monoxide",
    "h2": "hydrogen", "h2o": "water", "h2s": "hydrogen sulfide",
    "hydrogensulfide": "hydrogen sulfide", "hydrogen sulphide": "hydrogen sulfide",
    "he": "helium", "ar": "argon",
}


def _unknown_message(name):
    key = " ".join(name.split()).lower()
    guess = _SHORTHANDS.get(key) or _SHORTHANDS.get(key.replace(" ", ""))
    if guess is None:
        close = difflib.get_close_matches(key, sorted(KNOWN_COMPONENTS), n=1, cutoff=0.6)
        guess = close[0] if close else None
    hint = f" Did you mean '{guess}'?" if guess else " See 'Component names' in the README."
    return f"unknown component '{name}'.{hint}"


def confirm_composition(parent, value, label="composition"):
    """Check that ``value`` sums to 1; if not, ask the user to normalise.

    Returns the composition in GERG-2008 / ISO 20765 order. Raises
    ``CompositionCancelled`` when the user refuses normalisation.
    """
    total = sum(value.values())
    if abs(total - 1.0) > COMPOSITION_SUM_TOL:
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
    return sort_composition({k: v / total for k, v in value.items()})
