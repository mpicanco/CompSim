"""Lee-Kesler (1975) generalized compressibility-factor EOS.

Z = Z0 + (omega / omega_r) (Zr - Z0), where Z0 is the simple-fluid (Ar) term and
Zr the reference-fluid (n-octane) term. Both are evaluated at the mixture
reduced conditions, using the pseudo-critical properties of the mixture for
Z0 and the reference fluid's own critical constants for Zr.

Each term solves the Lee-Kesler virial-type form

    Z = 1 + B/Vr + C/Vr^2 + D/Vr^5 + c4/(Tr^3 Vr^2) (beta + gamma/Vr^2) exp(-gamma/Vr^2)

for the reduced volume Vr = Pc V/(R Tc), taking the largest real root (vapour).
Constants: Lee & Kesler (1975), as printed in Cantera's lk.cpp (tpx namespace).
Mixing: Plocker-type pseudo-critical rules with no binary interaction.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from core.data import COMPONENTS, DEFAULT_MW
from core.thermo.eos import EquationOfState, R

# (b1..b4), (c1..c4), (d1, d2), beta, gamma -- index 0 simple fluid, 1 reference
SIMPLE = {
    "b": (0.1181193, 0.265728, 0.154790, 0.030323),
    "c": (0.0236744, 0.0186984, 0.0, 0.042724),
    "d": (1.55488e-5, 6.23689e-5),
    "beta": 0.65392,
    "gamma": 0.060167,
}
REFERENCE = {
    "b": (0.2026579, 0.331511, 0.027655, 0.203488),
    "c": (0.0313385, 0.0503618, 0.016901, 0.041577),
    "d": (4.8736e-5, 0.740336e-5),
    "beta": 1.226,
    "gamma": 0.03754,
}
# n-octane reference fluid (Lee & Kesler 1975)
TC_REF = 568.7        # K
PC_REF = 24.90e5      # Pa
OMEGA_REF = 0.3978    # acentric factor of n-octane

def _reference_is_liquid(Tr, Pr):
    """True when the n-octane reference is above its saturation pressure.

    Lee-Kesler vapour-pressure correlation: ln Pr_sat = f0 + omega_r f1.
    """
    if Tr >= 1.0:
        return False
    f0 = 5.92714 - 6.09648 / Tr - 1.28862 * np.log(Tr) + 0.169347 * Tr ** 6
    f1 = 15.2518 - 15.6875 / Tr - 13.4721 * np.log(Tr) + 0.43577 * Tr ** 6
    return np.log(Pr) > f0 + OMEGA_REF * f1


_VR_GRID = np.logspace(-2.0, 9.0, 1200)  # reduced-volume scan for the vapour root


def _residual(Vr, Pr, Tr, k):
    """Z*Vr - [Vr + B + C/Vr + D/Vr^4 + c4 term]; zero at a physical root."""
    b1, b2, b3, b4 = k["b"]
    c1, c2, c3, c4 = k["c"]
    d1, d2 = k["d"]
    B = b1 - b2 / Tr - b3 / Tr ** 2 - b4 / Tr ** 3
    C = c1 - c2 / Tr + c3 / Tr ** 3
    D = d1 + d2 / Tr
    beta, gamma = k["beta"], k["gamma"]
    expo = np.exp(-gamma / (Vr * Vr))
    return (Pr * Vr * Vr / Tr
            - (Vr + B + C / Vr + D / Vr ** 4
               + c4 / (Tr ** 3 * Vr) * (beta + gamma / (Vr * Vr)) * expo))


def _lk_term_z(Tr, Pr, k):
    """Compressibility factor of one Lee-Kesler term (largest real root).

    Returns None when the term has no real root (no vapour state at this point).
    """
    g = _residual(_VR_GRID, Pr, Tr, k)
    sign_change = np.where(np.sign(g[:-1]) * np.sign(g[1:]) < 0.0)[0]
    if sign_change.size == 0:
        return None
    i = sign_change[-1]
    Vr = brentq(lambda v: _residual(v, Pr, Tr, k), _VR_GRID[i], _VR_GRID[i + 1],
                xtol=1e-14, rtol=1e-12)
    return Pr * Vr / Tr


def _component_props(comp):
    props = COMPONENTS.get(comp)
    if props is None:
        props = {"Tc": 132.6, "Pc": 37.71e5, "omega": 0.0, "MW": DEFAULT_MW}
    return props


def pseudo_critical(composition):
    """Mixture (Tc, Pc, omega) by Plocker-type pseudo-critical mixing rules."""
    items = [(x, _component_props(c)) for c, x in composition.items() if x > 0.0]
    if not items:
        return 132.6, 37.71e5, 0.0
    Vc = []
    for _, p in items:
        Zc = 0.2905 - 0.085 * p["omega"]
        Vc.append(Zc * R * p["Tc"] / p["Pc"])
    V_cm = 0.0
    T_num = 0.0
    for i, (xi, pi) in enumerate(items):
        for j, (xj, pj) in enumerate(items):
            V_ij = ((Vc[i] ** (1.0 / 3.0) + Vc[j] ** (1.0 / 3.0)) / 2.0) ** 3
            T_ij = np.sqrt(pi["Tc"] * pj["Tc"])
            w = xi * xj
            V_cm += w * V_ij
            T_num += w * V_ij * T_ij
    T_cm = T_num / V_cm
    omega = sum(x * p["omega"] for x, p in items)
    Zc_m = 0.2905 - 0.085 * omega
    P_cm = Zc_m * R * T_cm / V_cm
    return T_cm, P_cm, omega


class LeeKesler(EquationOfState):
    name = "Lee-Kesler"

    def z_factor(self, P, T, composition):
        if not composition or P <= 0.0 or T <= 0.0:
            return 1.0
        Tc, Pc, omega = pseudo_critical(composition)
        Z0 = _lk_term_z(T / Tc, P / Pc, SIMPLE)
        if Z0 is None:
            Z0 = 1.0
        Zr = _lk_term_z(T / TC_REF, P / PC_REF, REFERENCE)
        # The acentric correction assumes the n-octane reference is a vapour at
        # its own reduced state. Where it is below saturation (liquid), its
        # "vapour" root is not physical and biases Z, so Z = Z0 is used there.
        if Zr is None or _reference_is_liquid(T / TC_REF, P / PC_REF):
            return Z0
        return Z0 + (omega / OMEGA_REF) * (Zr - Z0)
