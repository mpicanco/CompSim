from __future__ import annotations

import math

# ISA-75.01 compressible-flow sizing constant: w[kg/h] = N6 * Cv * P1[bar] * ...
N6 = 27.3


def _gas_magnitude(P_hi, P_lo, T1, M_kgmol, Z1, Cv, xT, gamma, Fp):
    """Compressible flow magnitude [kg/s] for upstream P_hi > downstream P_lo."""
    x = (P_hi - P_lo) / P_hi
    Fk = gamma / 1.40
    x_choked = Fk * xT
    if x_choked <= 1e-12:
        return 0.0
    x_eff = min(x, x_choked)
    Y = 1.0 - x_eff / (3.0 * x_choked)
    Y = max(0.667, Y)
    M_kgkmol = M_kgmol * 1000.0
    P_hi_bar = P_hi / 1e5
    w_kgh = N6 * Fp * Cv * P_hi_bar * Y * math.sqrt(x_eff * M_kgkmol / (T1 * Z1))
    return w_kgh / 3600.0


def isa_valve_flow(P1, P2, T1, M_kgmol, Z1, Cv, xT=0.7, gamma=1.3, Fp=1.0):
    """Compressible (gas/vapour) mass flow through a control valve, ISA-75.01.

    Bidirectional. Positive flow runs P1 -> P2 (P1 > P2); negative flow runs
    P2 -> P1 when the downstream pressure P2 is higher. The sizing is always
    done from the higher-pressure side, using ``T1`` and ``Z1`` of the gas
    there (the caller supplies the gas state it has).

        w = N6 * Fp * Cv * P_up * Y * sqrt( x * M / (T_up * Z_up) )

    Returns mass flow in kg/s (P in Pa, T in K, M in kg/mol).
    """
    if P1 == P2 or Cv <= 0.0 or M_kgmol <= 0.0 or min(P1, P2) <= 0.0:
        return 0.0
    if P1 > P2:
        return _gas_magnitude(P1, P2, T1, M_kgmol, Z1, Cv, xT, gamma, Fp)
    return -_gas_magnitude(P2, P1, T1, M_kgmol, Z1, Cv, xT, gamma, Fp)


def _liquid_magnitude(P_hi, P_lo, rho, Cv, Fp):
    dp_bar = (P_hi - P_lo) / 1e5
    G = rho / 1000.0
    Q_m3h = 0.865 * Fp * Cv * math.sqrt(dp_bar / G)
    return Q_m3h * rho / 3600.0


def isa_liquid_flow(P1, P2, rho, Cv, Fp=1.0):
    """Incompressible (liquid) mass flow through a valve, ISA-75.01.

    Bidirectional, same sign convention as ``isa_valve_flow``.
    Q[m3/h] = N1 * Cv * sqrt(dP/G);  N1 = 0.865, G = rho/1000.
    Returns mass flow in kg/s.
    """
    if P1 == P2 or rho <= 0.0 or Cv <= 0.0:
        return 0.0
    if P1 > P2:
        return _liquid_magnitude(P1, P2, rho, Cv, Fp)
    return -_liquid_magnitude(P2, P1, rho, Cv, Fp)
