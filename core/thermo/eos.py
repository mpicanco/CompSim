from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from core.data import COMPONENTS, DEFAULT_MW

R = 8.31446261815324  # J/(mol K)


class EquationOfState(ABC):
    """Abstract equation-of-state contract.

    Composition is a dict mapping component name -> mole fraction. Pressure in
    Pa, temperature in K, density in kg/m3.
    """

    name = "EOS"

    @abstractmethod
    def z_factor(self, P: float, T: float, composition: dict) -> float:
        """Compressibility factor Z (largest real root = vapour)."""

    def molar_mass(self, composition: dict) -> float:
        mm = 0.0
        for comp, x in composition.items():
            mm += x * COMPONENTS.get(comp, {}).get("MW", DEFAULT_MW)
        return mm

    def density(self, P: float, T: float, composition: dict) -> float:
        z = self.z_factor(P, T, composition)
        mm = self.molar_mass(composition)
        return P * mm / (z * R * T)

    def fugacity_coefficients(self, P, T, composition, phase="vapour"):
        """Fugacity coefficients phi_i (default 1.0 = ideal)."""
        return {c: 1.0 for c in composition}


class IdealGas(EquationOfState):
    name = "Ideal Gas"

    def z_factor(self, P: float, T: float, composition: dict) -> float:
        return 1.0


class CubicEOS(EquationOfState, ABC):
    """Two-parameter cubic EOS with mixing rules and fugacity coefficients.

    Generic cubic: P = RT/(v-b) - a/(v^2 + u b v + w b^2).
    Peng-Robinson: u=2, w=-1.  Soave-Redlich-Kwong: u=1, w=0.
    """

    u = 2.0
    w = -1.0

    @staticmethod
    def _component_ab(comp: str, T: float, ac, bc, kappa_coeffs):
        props = COMPONENTS.get(comp)
        if props is None:
            props = {"Tc": 132.6, "Pc": 37.71e5, "omega": 0.0, "MW": DEFAULT_MW}
        Tc, Pc, omega = props["Tc"], props["Pc"], props["omega"]
        Tr = T / Tc
        c0, c1, c2 = kappa_coeffs
        kappa = c0 + c1 * omega + c2 * omega ** 2
        alpha = (1.0 + kappa * (1.0 - np.sqrt(Tr))) ** 2
        a_i = ac * (R ** 2) * (Tc ** 2) / Pc * alpha
        b_i = bc * R * Tc / Pc
        return a_i, b_i

    def _mix(self, T, composition, ac, bc, kappa_coeffs):
        a = {}
        b = {}
        for comp in composition:
            a[comp], b[comp] = self._component_ab(comp, T, ac, bc, kappa_coeffs)
        b_mix = sum(x * b[c] for c, x in composition.items())
        S = sum(x * np.sqrt(a[c]) for c, x in composition.items())
        a_mix = S * S  # geometric mixing (k_ij = 0)
        return a, b, a_mix, b_mix, S

    def _abc(self, P, T, composition):
        ac, bc, kappa_coeffs = self._params()
        a, b, a_mix, b_mix, S = self._mix(T, composition, ac, bc, kappa_coeffs)
        A = a_mix * P / (R * T) ** 2
        B = b_mix * P / (R * T)
        return a, b, a_mix, b_mix, S, A, B

    def z_roots(self, P, T, composition):
        _, _, _, _, _, A, B = self._abc(P, T, composition)
        u, w = self.u, self.w
        # generic two-parameter cubic in Z (PR: u=2,w=-1; SRK: u=1,w=0)
        coeffs = [
            1.0,
            -(1.0 + B - u * B),
            A + w * B ** 2 - u * B - u * B ** 2,
            -(A * B + w * B ** 2 + w * B ** 3),
        ]
        roots = np.roots(coeffs)
        real = np.sort(roots[np.abs(roots.imag) < 1e-10].real)
        # physical roots must satisfy v > b, i.e. Z > B
        return [float(r) for r in real if r > B]

    def z_factor(self, P, T, composition):
        roots = self.z_roots(P, T, composition)
        if roots:
            return roots[-1]
        _, _, _, _, _, _, B = self._abc(P, T, composition)
        return max(1e-6, B) * (1.0 + 1e-6)

    def fugacity_coefficients(self, P, T, composition, phase="vapour"):
        a, b, a_mix, b_mix, S, A, B = self._abc(P, T, composition)
        if a_mix <= 0.0 or b_mix <= 0.0:
            return {c: 1.0 for c in composition}

        roots = self.z_roots(P, T, composition)
        if not roots:
            Z = self.z_factor(P, T, composition)
        elif phase == "liquid":
            Z = roots[0]
        else:
            Z = roots[-1]

        sq = np.sqrt(self.u * self.u - 4.0 * self.w)
        lnphi = {}
        for c, x in composition.items():
            coef = 2.0 * np.sqrt(a[c]) / S - b[c] / b_mix
            t1 = (b[c] / b_mix) * (Z - 1.0)
            t2 = np.log(max(Z - B, 1e-12))
            t3 = (A / (B * sq)) * coef
            denom = (Z + 0.5 * (self.u - sq) * B)
            if denom <= 0.0:
                t4 = 0.0
            else:
                t4 = np.log((Z + 0.5 * (self.u + sq) * B) / denom)
            lnphi[c] = t1 - t2 - t3 * t4
        return {c: float(np.exp(lnphi[c])) for c in composition}


class PengRobinson(CubicEOS):
    name = "Peng-Robinson"
    u = 2.0
    w = -1.0

    @staticmethod
    def _params():
        return 0.45724, 0.07780, (0.37464, 1.54226, -0.26992)


class SoaveRedlichKwong(CubicEOS):
    name = "Soave-Redlich-Kwong"
    u = 1.0
    w = 0.0

    @staticmethod
    def _params():
        return 0.42747, 0.08664, (0.480, 1.574, -0.176)
