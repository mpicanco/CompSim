"""Thermophysical property data for common oil & gas components.

Values in SI units: molar mass [kg/mol], critical temperature [K],
critical pressure [Pa], acentric factor [-], liquid density at normal boiling
point [kg/m3], and Antoine coefficients for vapour pressure
(log10(P_sat / mmHg) = A - B / (C + T[degC])).
"""

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

# tolerance for "the mole fractions add up to 1"
COMPOSITION_SUM_TOL = 1e-6


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
