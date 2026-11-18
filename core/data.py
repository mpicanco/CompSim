"""Thermophysical property data for common oil & gas components.

Every GERG-2008 component plus the ``air`` pseudo-component has an entry, so
any accepted composition is modelled with its own properties by every EOS.

Values in SI units: molar mass [kg/mol], critical temperature [K],
critical pressure [Pa], acentric factor [-], liquid density at normal boiling
point [kg/m3], and Antoine coefficients for vapour pressure
(log10(P_sat / mmHg) = A - B / (C + T[degC])).
"""

import difflib

COMPONENTS = {
    "methane":          {"MW": 0.016043, "Tc": 190.56,  "Pc": 45.99e5,  "omega": 0.011,
                         "cp": 35.7, "rhoL": 422.4, "antoine": (6.69561, 405.42, 267.777)},
    "ethane":           {"MW": 0.030070, "Tc": 305.32,  "Pc": 48.72e5,  "omega": 0.099,
                         "cp": 52.5, "rhoL": 546.0, "antoine": (6.83452, 663.70, 256.470)},
    "propane":          {"MW": 0.044097, "Tc": 369.83,  "Pc": 42.48e5,  "omega": 0.152,
                         "cp": 73.6, "rhoL": 585.0, "antoine": (6.80398, 803.81, 247.04)},
    "n-butane":         {"MW": 0.058124, "Tc": 425.12,  "Pc": 37.96e5,  "omega": 0.200,
                         "cp": 98.5, "rhoL": 601.0, "antoine": (6.80896, 935.86, 238.73)},
    "i-butane":         {"MW": 0.058124, "Tc": 407.82,  "Pc": 36.40e5,  "omega": 0.186,
                         "cp": 96.7, "rhoL": 595.0, "antoine": (6.82485, 943.453, 240.00)},
    "n-pentane":        {"MW": 0.072151, "Tc": 469.70,  "Pc": 33.70e5,  "omega": 0.252,
                         "cp": 120.2, "rhoL": 626.0, "antoine": (6.87632, 1075.78, 233.205)},
    "nitrogen":         {"MW": 0.028013, "Tc": 126.20,  "Pc": 33.98e5,  "omega": 0.037,
                         "cp": 29.1, "rhoL": 808.0, "antoine": (6.49457, 255.68, 266.55)},
    "oxygen":           {"MW": 0.031999, "Tc": 154.58,  "Pc": 50.43e5,  "omega": 0.022,
                         "cp": 29.4, "rhoL": 1141.0, "antoine": (6.6914, 319.013, 266.697)},
    "carbon dioxide":   {"MW": 0.044010, "Tc": 304.12,  "Pc": 73.74e5,  "omega": 0.225,
                         "cp": 37.1, "rhoL": 777.0, "antoine": (6.81228, 1301.679, -3.494)},
    "water":            {"MW": 0.018015, "Tc": 647.14,  "Pc": 220.64e5, "omega": 0.344,
                         "cp": 33.6, "rhoL": 998.0, "antoine": (8.07131, 1730.63, 233.426)},
    "hydrogen":         {"MW": 0.002016, "Tc": 33.19,   "Pc": 12.96e5,  "omega": -0.216,
                         "cp": 28.8, "rhoL": 70.8, "antoine": (5.98612, 153.76, 276.21)},
    "hydrogen sulfide": {"MW": 0.034081, "Tc": 373.40,  "Pc": 89.63e5,  "omega": 0.090,
                         "cp": 34.2, "rhoL": 914.0, "antoine": (6.99365, 768.742, 247.09)},
    "i-pentane":        {"MW": 0.072151, "Tc": 460.39,  "Pc": 33.81e5,  "omega": 0.229,
                         "cp": 118.8, "rhoL": 613.0, "antoine": (6.83315, 1040.73, 235.445)},
    "n-hexane":         {"MW": 0.086178, "Tc": 507.60,  "Pc": 30.25e5,  "omega": 0.300,
                         "cp": 143.1, "rhoL": 615.0, "antoine": (6.87601, 1171.17, 224.41)},
    "n-heptane":        {"MW": 0.100205, "Tc": 540.20,  "Pc": 27.40e5,  "omega": 0.350,
                         "cp": 166.0, "rhoL": 614.0, "antoine": (6.89385, 1264.37, 216.636)},
    "n-octane":         {"MW": 0.114232, "Tc": 568.70,  "Pc": 24.90e5,  "omega": 0.399,
                         "cp": 188.9, "rhoL": 612.0, "antoine": (6.91874, 1351.756, 209.100)},
    "n-nonane":         {"MW": 0.128259, "Tc": 594.60,  "Pc": 22.90e5,  "omega": 0.445,
                         "cp": 211.7, "rhoL": 610.0, "antoine": (6.93893, 1431.82, 202.011)},
    "n-decane":         {"MW": 0.142285, "Tc": 617.70,  "Pc": 21.10e5,  "omega": 0.490,
                         "cp": 234.6, "rhoL": 604.0, "antoine": (6.94365, 1495.17, 193.858)},
    "carbon monoxide":  {"MW": 0.028010, "Tc": 132.85,  "Pc": 34.94e5,  "omega": 0.045,
                         "cp": 29.1, "rhoL": 789.0, "antoine": (6.24021, 230.27, 260.01)},
    # no Antoine fit for helium: the flash uses Wilson K-values for it
    "helium":           {"MW": 0.004003, "Tc": 5.19,    "Pc": 2.27e5,   "omega": -0.390,
                         "cp": 20.8, "rhoL": 125.0},
    "argon":            {"MW": 0.039948, "Tc": 150.86,  "Pc": 48.98e5,  "omega": -0.002,
                         "cp": 20.8, "rhoL": 1395.0, "antoine": (6.61651, 304.227, 267.32)},
    "air":              {"MW": 0.028964, "Tc": 132.60,  "Pc": 37.71e5,  "omega": 0.0,
                         "cp": 29.1, "rhoL": 870.0, "antoine": (6.49457, 255.68, 266.55)},
}

# Component order of GERG-2008 / ISO 20765-2 (AGA-8 lists the same 21
# components, with the butane and pentane isomers swapped), in this project's
# naming. Used to list compositions in a fixed, standard order; components
# outside the list (e.g. "air") follow, alphabetically.
COMPONENT_ORDER = (
    "methane", "nitrogen", "carbon dioxide", "ethane", "propane",
    "n-butane", "i-butane", "n-pentane", "i-pentane", "n-hexane",
    "n-heptane", "n-octane", "n-nonane", "n-decane", "hydrogen", "oxygen",
    "carbon monoxide", "water", "hydrogen sulfide", "helium", "argon",
)
_ORDER_INDEX = {c: i for i, c in enumerate(COMPONENT_ORDER)}

# every component name a composition may contain: the GERG-2008 set plus
# the components with built-in property data (e.g. the "air" pseudo-component)
KNOWN_COMPONENTS = frozenset(COMPONENT_ORDER) | frozenset(COMPONENTS)
assert KNOWN_COMPONENTS == frozenset(COMPONENTS), "component without property data"

# tolerance for "the mole fractions add up to 1"
COMPOSITION_SUM_TOL = 1e-6


def check_composition(value, label="composition"):
    """Validate a ``{name: mole fraction}`` dict; raises ValueError.

    Returns a new dict with canonical names (lower case, single spaces) and
    float fractions; it is not normalised. Components that are not listed
    are taken as 0. A name that is not a known component is rejected, with
    the closest valid name suggested, as is a component listed twice.
    """
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
            raise ValueError(f"{label}: {unknown_component_message(str(k))}")
        if name in out:
            raise ValueError(f"{label}: component '{name}' is listed twice")
        out[name] = float(v)
    return out


def composition_total_ok(z):
    """True when the fractions of ``z`` add up to 1 within tolerance."""
    return abs(sum(z.values()) - 1.0) <= COMPOSITION_SUM_TOL


def normalize_composition(z):
    """``z`` scaled to sum to exactly 1, in GERG-2008 / ISO 20765 order."""
    total = sum(z.values())
    return sort_composition({k: v / total for k, v in z.items()})


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


def unknown_component_message(name):
    """'unknown component ...' message with the closest valid name, if any."""
    key = " ".join(name.split()).lower()
    guess = _SHORTHANDS.get(key) or _SHORTHANDS.get(key.replace(" ", ""))
    if guess is None:
        close = difflib.get_close_matches(key, sorted(KNOWN_COMPONENTS), n=1, cutoff=0.6)
        guess = close[0] if close else None
    hint = f" Did you mean '{guess}'?" if guess else " See 'Component names' in the README."
    return f"unknown component '{name}'.{hint}"


def sort_composition(z):
    """Return ``z`` as a new dict in the GERG-2008 / ISO 20765 component order.

    Components not present are implicitly 0 and are not added.
    """
    return dict(sorted(z.items(),
                       key=lambda kv: (_ORDER_INDEX.get(kv[0], len(_ORDER_INDEX)), kv[0])))


DEFAULT_MW = 0.028964  # kg/mol (air)
DEFAULT_CP = 29.1       # J/(mol K), air-like ideal-gas Cp for unknown components


def molar_mass(z):
    """Mixture molar mass [kg/mol] for mole fractions ``z``."""
    if not z:
        return 0.0
    return sum(x * COMPONENTS.get(c, {}).get("MW", DEFAULT_MW) for c, x in z.items())


def liquid_molar_volume(x):
    """Ideal-mixing liquid molar volume [m3/mol]."""
    if not x:
        return 0.0
    v = 0.0
    for c, xi in x.items():
        props = COMPONENTS.get(c, {})
        v += xi * props.get("MW", DEFAULT_MW) / props.get("rhoL", 700.0)
    return v


def liquid_density(x):
    """Ideal-mixing liquid density [kg/m3]."""
    v = liquid_molar_volume(x)
    return molar_mass(x) / v if v > 0 else 0.0
