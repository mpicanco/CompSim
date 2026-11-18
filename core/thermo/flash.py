from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.data import COMPONENTS

R = 8.31446261815324
MMHG_TO_PA = 133.322368


@dataclass
class FlashResult:
    V: float          # vapour fraction (moles vapour / moles total)
    x: dict           # liquid mole fractions
    y: dict           # vapour mole fractions
    converged: bool = True


def psat(component: str, T: float):
    """Antoine vapour pressure [Pa] at temperature T [K]."""
    props = COMPONENTS.get(component)
    if props is None or "antoine" not in props:
        return None
    A, B, C = props["antoine"]
    Tc = T - 273.15
    denom = C + Tc
    if denom <= 0:
        return None
    return 10 ** (A - B / denom) * MMHG_TO_PA


def kvalues_raoult(P: float, T: float, components):
    """Raoult's-law K-values (ideal mixture): K_i = P_sat,i(T) / P."""
    K = {}
    for c in components:
        p = psat(c, T)
        if p is not None:
            K[c] = p / P
        else:
            K[c] = kvalue_wilson(c, P, T)
    return K


def kvalue_wilson(c: str, P: float, T: float):
    props = COMPONENTS.get(c, {})
    Tc = props.get("Tc", 200.0)
    Pc = props.get("Pc", 4.0e6)
    omega = props.get("omega", 0.0)
    return (Pc / P) * np.exp(5.373 * (1.0 + omega) * (1.0 - Tc / T))


def kvalues_wilson(P: float, T: float, components):
    """Wilson K-values (standard initial guess for rigorous EOS flashes)."""
    return {c: kvalue_wilson(c, P, T) for c in components}


def rachford_rice(z: dict, K: dict) -> float:
    """Solve for vapour fraction V in [0,1] by bisection."""
    comps = list(z)

    def f(V):
        return sum(z[c] * (K[c] - 1.0) / (1.0 + V * (K[c] - 1.0)) for c in comps)

    if f(0.0) <= 0.0:
        return 0.0  # all liquid
    if f(1.0) >= 0.0:
        return 1.0  # all vapour
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < 1e-10:
            return mid
        if fm > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def flash_isothermal(P: float, T: float, z: dict, method="wilson") -> FlashResult:
    """Two-phase isothermal flash at (P, T) for overall composition z."""
    components = list(z)
    if method == "raoult":
        K = kvalues_raoult(P, T, components)
    else:
        K = kvalues_wilson(P, T, components)

    V = rachford_rice(z, K)

    if V <= 1e-9:
        return FlashResult(0.0, x=dict(z), y={c: z[c] * K[c] for c in components})
    if V >= 1.0 - 1e-9:
        return FlashResult(1.0, x={c: z[c] / K[c] for c in components}, y=dict(z))

    x = {c: z[c] / (1.0 + V * (K[c] - 1.0)) for c in components}
    y = {c: K[c] * x[c] for c in components}
    return FlashResult(V, x, y)


def flash_eos(P: float, T: float, z: dict, eos, tol=1e-9, max_iter=80) -> FlashResult:
    """Rigorous phi-phi flash using an equation of state.

    K-values are refined by successive substitution: K_i = phi_i^L / phi_i^V,
    starting from a Wilson estimate. Requires a cubic EOS providing
    ``fugacity_coefficients``.
    """
    comps = list(z)
    K = kvalues_wilson(P, T, comps)

    for _ in range(max_iter):
        V = rachford_rice(z, K)
        if V <= 1e-9:
            return FlashResult(0.0, x=dict(z), y={c: z[c] * K[c] for c in comps})
        if V >= 1.0 - 1e-9:
            return FlashResult(1.0, x={c: z[c] / K[c] for c in comps}, y=dict(z))

        x = {c: z[c] / (1.0 + V * (K[c] - 1.0)) for c in comps}
        y = {c: K[c] * x[c] for c in comps}
        phiL = eos.fugacity_coefficients(P, T, x, phase="liquid")
        phiV = eos.fugacity_coefficients(P, T, y, phase="vapour")
        K_new = {c: phiL[c] / phiV[c] for c in comps}
        if not all(np.isfinite(k) and k > 0.0 for k in K_new.values()):
            raise ValueError("EOS flash diverged (non-finite K-values)")
        err = max(abs(K_new[c] - K[c]) for c in comps)
        K = K_new
        if err < tol:
            break

    V = rachford_rice(z, K)
    if V <= 1e-9:
        return FlashResult(0.0, x=dict(z), y={c: z[c] * K[c] for c in comps})
    if V >= 1.0 - 1e-9:
        return FlashResult(1.0, x={c: z[c] / K[c] for c in comps}, y=dict(z))
    x = {c: z[c] / (1.0 + V * (K[c] - 1.0)) for c in comps}
    y = {c: K[c] * x[c] for c in comps}
    return FlashResult(V, x, y)
