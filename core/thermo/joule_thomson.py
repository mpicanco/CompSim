"""Joule-Thomson effect for isenthalpic throttling of gases.

The coefficient is

    mu_JT = (dT/dP)_H = (T (dV/dT)_P - V) / Cp = (R T^2 / P) (dZ/dT)_P / Cp

so it only needs the compressibility factor from the EOS (numerically
differentiated in T) and the mixture heat capacity. Cp is approximated with the
ideal-gas value (constant, from ``core.data``); the real-gas residual is
neglected, which is adequate at the moderate pressures of this simulator.
An ideal-gas EOS has Z = 1 everywhere, so mu_JT = 0 and no temperature change.
"""

from __future__ import annotations

from core.data import COMPONENTS, DEFAULT_CP
from core.thermo.eos import R


def mixture_cp(composition):
    """Ideal-gas molar heat capacity of the mixture [J/(mol K)]."""
    total = sum(composition.values())
    if total <= 0.0:
        return DEFAULT_CP
    return sum(x * COMPONENTS.get(c, {}).get("cp", DEFAULT_CP)
               for c, x in composition.items()) / total


def mu_jt(eos, P, T, composition):
    """Joule-Thomson coefficient [K/Pa] of the gas at (P, T)."""
    if P <= 0.0 or T <= 0.0 or not composition:
        return 0.0
    h = max(1e-3 * T, 1e-3)
    dZdT = (eos.z_factor(P, T + h, composition)
            - eos.z_factor(P, T - h, composition)) / (2.0 * h)
    return R * T * T / P * dZdT / mixture_cp(composition)


def throttle_temperature(eos, P_hi, P_lo, T, composition, steps=10):
    """Gas temperature after isenthalpic throttling from P_hi down to P_lo.

    Integrates dT/dP = mu_JT along the pressure path in ``steps`` midpoint
    increments. Returns ``T`` unchanged when there is no pressure drop.
    """
    if P_hi <= P_lo or P_lo <= 0.0:
        return T
    dP = (P_lo - P_hi) / steps
    for k in range(steps):
        P_mid = P_hi + (k + 0.5) * dP
        T = T + mu_jt(eos, P_mid, T, composition) * dP
    return T
