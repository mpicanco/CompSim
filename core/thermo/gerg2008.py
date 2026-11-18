"""GERG-2008 equation of state (Kunz & Wagner, J. Chem. Eng. Data 2012).

Only the residual Helmholtz part is implemented, which is all that is needed
for pressure, compressibility and density. Ideal-gas caloric terms are not used.

Reduced mixture variables:
    Tr(x)   = sum_i x_i^2 Tc_i + sum_{i<j} 2 x_i x_j zeta_T,ij sqrt(Tc_i Tc_j)
    1/rhor  = sum_i x_i^2 / rhoc_i
              + sum_{i<j} 2 x_i x_j /8 (rhoc_i^-1/3 + rhoc_j^-1/3)^3 zeta_V,ij
    zeta_ij = beta gamma (x_i + x_j) / (beta^2 x_i + x_j)
    delta = rho / rhor,  tau = Tr / T

Residual Helmholtz energy:
    alphar = sum_i x_i alphar_oi(delta_i, tau_i) + sum_{i<j} x_i x_j F_ij dalpha_ij
    delta_i = rho / rhoc_i,  tau_i = Tc_i / T

Pressure: P = rho R T (1 + delta dalphar/ddelta).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from core.thermo.eos import EquationOfState, R
from core.thermo import gerg_data as G

# project component names -> GERG-2008 names
ALIASES = {
    "methane": "methane", "nitrogen": "nitrogen", "carbon dioxide": "carbondioxide",
    "ethane": "ethane", "propane": "propane", "n-butane": "n-butane",
    "i-butane": "isobutane", "n-pentane": "n-pentane", "n-hexane": "n-hexane",
    "n-heptane": "n-heptane", "n-octane": "n-octane", "hydrogen": "hydrogen",
    "oxygen": "oxygen", "water": "water", "hydrogen sulfide": "hydrogensulfide",
    "i-pentane": "isopentane", "n-nonane": "n-nonane", "n-decane": "n-decane",
    "carbon monoxide": "carbonmonoxide", "helium": "helium", "argon": "argon",
}

_BIN = {}
for (a, b), vals in G.BINARY:
    _BIN[(a, b)] = vals
_FIJ = {tuple(p): f for p, f in G.FIJ}
_DEP = {tuple(p): v for p, v in G.DEPARTURE}


def _gerg_name(comp):
    name = ALIASES.get(comp, comp)
    if name not in G.PURE:
        raise ValueError(f"GERG-2008 has no data for component '{comp}'")
    return name


def _pair(i, j):
    """(first, second, (bV, gV, bT, gT)) in the order the table stores the pair."""
    if (i, j) in _BIN:
        return i, j, _BIN[(i, j)]
    if (j, i) in _BIN:
        return j, i, _BIN[(j, i)]
    return i, j, (1.0, 1.0, 1.0, 1.0)


def _fij(i, j):
    return _FIJ.get((i, j), _FIJ.get((j, i), 1.0))


def _dep(i, j):
    return _DEP.get((i, j), _DEP.get((j, i)))


class _Mixture:
    """Precomputed reducing parameters and term arrays for one composition."""

    def __init__(self, composition):
        names = [_gerg_name(c) for c, x in composition.items() if x > 0.0]
        xs = {_gerg_name(c): x for c, x in composition.items() if x > 0.0}
        names = list(xs)
        x = np.array([xs[n] for n in names])
        self.names = names
        self.x = x
        Tc = np.array([G.PURE[n]["Tc"] for n in names])
        rhoc = np.array([G.PURE[n]["rhoc"] for n in names])
        self.M = float(sum(xs[n] * G.PURE[n]["M"] for n in names))

        # reducing functions (pairs use the stored order)
        Tr = float(np.sum(x * x * Tc))
        inv_rho = float(np.sum(x * x / rhoc))
        cbrt_inv = 1.0 / np.cbrt(rhoc)
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                f, s, (bV, gV, bT, gT) = _pair(names[a], names[b])
                xf, xs_ = xs[f], xs[s]
                ia, ib = names.index(f), names.index(s)
                zeta_T = bT * gT * (xf + xs_) / (bT * bT * xf + xs_)
                zeta_V = bV * gV * (xf + xs_) / (bV * bV * xf + xs_)
                Tr += 2.0 * xf * xs_ * zeta_T * np.sqrt(Tc[ia] * Tc[ib])
                inv_rho += 2.0 * xf * xs_ / 8.0 * (cbrt_inv[ia] + cbrt_inv[ib]) ** 3 * zeta_V
        self.Tr = Tr
        self.rhor = 1.0 / inv_rho

        # pure-fluid term arrays: value depends on delta_i = delta * s_k
        pn, pt, pd, pc, pl, ps, pw, ptau = [], [], [], [], [], [], [], []
        for k, n in enumerate(names):
            r = G.RESIDUAL[n]
            m = len(r["n"])
            pn += r["n"]; pt += r["t"]; pd += r["d"]; pc += r["c"]; pl += r["l"]
            ps += [self.rhor / (G.PURE[n]["rhoc"])] * m
            pw += [x[k]] * m
            ptau += [G.PURE[n]["Tc"]] * m
        self.p = {k: np.array(v, dtype=float) for k, v in
                  dict(n=pn, t=pt, d=pd, c=pc, l=pl, s=ps, w=pw, Tc=ptau).items()}

        # departure term arrays (scaled by x_i x_j F_ij)
        dn, dt, dd, de, de2, db, dg, dw = [], [], [], [], [], [], [], []
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                dep = _dep(names[a], names[b])
                if dep is None:
                    continue
                f = _fij(names[a], names[b])
                w = x[a] * x[b] * f
                m = len(dep["n"])
                dn += dep["n"]; dt += dep["t"]; dd += dep["d"]
                de += dep["eta"]; de2 += dep["epsilon"]; db += dep["beta"]; dg += dep["gamma"]
                dw += [w] * m
        self.q = {k: np.array(v, dtype=float) for k, v in
                  dict(n=dn, t=dt, d=dd, eta=de, eps=de2, beta=db, gamma=dg, w=dw).items()}

    def dalpha_ddelta(self, rho, T):
        """d(alphar)/d(delta) at fixed tau and composition, with delta = rho/rhor."""
        delta = rho / self.rhor
        p = self.p
        tau_i = p["Tc"] / T
        dk = delta * p["s"]                               # pure reduced densities
        E = np.exp(-p["c"] * dk ** p["l"])
        pure = (p["w"] * p["n"] * tau_i ** p["t"] * E
                * (p["d"] * dk ** (p["d"] - 1.0) - p["c"] * p["l"] * dk ** (p["d"] + p["l"] - 1.0))
                * p["s"])
        total = float(np.sum(pure))
        if self.q["n"].size:
            q = self.q
            tau = self.Tr / T
            Ed = np.exp(-q["eta"] * (delta - q["eps"]) ** 2 - q["beta"] * (delta - q["gamma"]))
            dep = (q["w"] * q["n"] * tau ** q["t"] * delta ** q["d"] * Ed
                   * (q["d"] / delta - 2.0 * q["eta"] * (delta - q["eps"]) - q["beta"]))
            total += float(np.sum(dep))
        return total

    def compressibility(self, rho, T):
        delta = rho / self.rhor
        return 1.0 + delta * self.dalpha_ddelta(rho, T)


_CACHE = {}


def _mixture(composition):
    key = tuple(sorted((c, round(float(x), 12)) for c, x in composition.items() if x > 0.0))
    mix = _CACHE.get(key)
    if mix is None:
        if len(_CACHE) > 256:
            _CACHE.clear()
        mix = _Mixture(composition)
        _CACHE[key] = mix
    return mix


class GERG2008(EquationOfState):
    name = "GERG-2008"

    def molar_mass(self, composition):
        return _mixture(composition).M

    def z_factor(self, P, T, composition):
        if not composition or P <= 0.0 or T <= 0.0:
            return 1.0
        mix = _mixture(composition)
        rho0 = P / (R * T)

        def f(rho):
            return rho * R * T * mix.compressibility(rho, T) - P

        # scan from low density for the first sign change: the vapour root
        grid = rho0 * np.logspace(-6, 1.0, 80)
        vals = [f(r) for r in grid]
        for i in range(len(grid) - 1):
            if vals[i] < 0.0 <= vals[i + 1]:
                rho = brentq(f, grid[i], grid[i + 1], xtol=1e-12 * rho0, rtol=1e-12)
                return P / (rho * R * T)
        return 1.0  # no vapour root found: treat as ideal rather than fail
