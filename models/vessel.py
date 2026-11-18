from __future__ import annotations

from core.base import CapacityBlock
from core.ports import MaterialStream, PortType
from core.thermo import get_eos
from core.thermo.eos import CubicEOS
from core.thermo.flash import flash_isothermal, flash_eos
from core.flow import isa_valve_flow, isa_liquid_flow
from core.data import molar_mass, liquid_molar_volume

R = 8.31446261815324
G = 9.80665


class Vessel(CapacityBlock):
    """Two-phase capacity block (separator / accumulator).

    Integrates the total molar hold-up ``N`` and overall composition ``z`` from
    the component mass balance, then performs a constant-volume (UV) isothermal
    flash. The flash may be a rigorous EOS (phi-phi) flash when ``flash_method``
    is ``"eos"`` and the selected EOS is cubic, otherwise a Wilson/Raoult K-value
    flash.

    Outlet flows are pressure-driven (bidirectional): the vapour is withdrawn
    through an equivalent valve (compressible ISA-75.01) against the downstream
    back-pressure, and the liquid through an equivalent valve (incompressible)
    with the hydrostatic head from the level. The vessel imposes its pressure
    back on the inlet so upstream flow elements see the correct downstream
    pressure. When a pressure-driven element (valve) is connected to an outlet,
    that element sets the withdrawn flow (``flow_demand``) and the vessel's own
    equivalent exit valve is bypassed.
    """

    # editing any of these restarts the hold-up from the initial conditions
    _INIT_KEYS = {"volume", "temperature", "eos", "initial_pressure", "initial_composition"}

    block_type = "Vessel"
    changes_composition = True
    category = "Equipment"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_input("in")
        self.add_output("vap_out")
        self.add_output("liq_out")
        self.add_output("level", PortType.SIGNAL)
        self.config = {
            "volume": 1.0,               # m3
            "temperature": 293.15,       # K (isothermal for now)
            "eos": "Ideal Gas",
            "flash_method": "wilson",    # wilson | raoult | eos
            "initial_pressure": 1.0e5,
            "initial_composition": {"methane": 0.85, "ethane": 0.10, "propane": 0.05},
            "gamma": 1.3,
            "xT": 0.7,
            "vap_exit_Cv": 1.0,
            "liq_exit_Cv": 1.0,
            "height": 1.0,               # m (for hydrostatic head)
            "vap_downstream_pressure": 1.0e5,
            "liq_downstream_pressure": 1.0e5,
        }
        self.init_state()

    def init_state(self):
        z0 = dict(self.config["initial_composition"])
        eos = get_eos(self.config["eos"])
        V = self.config["volume"]
        T = self.config["temperature"]
        P0 = self.config["initial_pressure"]

        # Charge the vessel with the same phase split and molar volumes the
        # constant-volume pressure solve uses, so that P0 is exactly the
        # pressure the solver returns for the initial hold-up (no jump at the
        # first step when part of the charge is liquid).
        v0, beta, x, y = self._mixture_molar_volume(P0, T, z0, eos)
        n0 = V / v0 if v0 > 0.0 else 0.0
        V_liq = n0 * (1.0 - beta) * self._liquid_molar_volume(x)

        self.states["moles"] = n0
        self.states["composition"] = z0
        self.states["pressure"] = P0
        self.states["level"] = min(1.0, max(0.0, V_liq / V)) if V > 0 else 0.0
        self._phase = {"V": beta, "x": dict(x), "y": dict(y)}
        self._vap_flow = 0.0
        self._liq_flow = 0.0

    def config_changed(self, keys):
        if self._INIT_KEYS & set(keys):
            self.init_state()

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _molar_mass(z):
        return molar_mass(z)

    @staticmethod
    def _liquid_molar_volume(x):
        return liquid_molar_volume(x)

    def _gas_molar_volume(self, P, T, y, eos):
        Z = eos.z_factor(P, T, y) if y else 1.0
        return Z * R * T / P

    def _flash(self, P, T, z, eos):
        method = self.config["flash_method"]
        if method == "eos" and not isinstance(eos, CubicEOS):
            # phi-phi flash needs a cubic EOS (ideal gas gives K = 1 for all)
            method = "wilson"
        if method == "eos":
            try:
                return flash_eos(P, T, z, eos)
            except Exception:
                method = "wilson"
        return flash_isothermal(P, T, z, method=method)

    def _downstream(self, out_port, default):
        if out_port.is_connected and out_port.connection.back_pressure is not None:
            return out_port.connection.back_pressure
        return default

    @staticmethod
    def _demand(out_port):
        """Signed flow [kg/s] the connected element draws from this outlet.

        Positive: withdrawn from the vessel. Negative: the element pushes gas
        or liquid back into the vessel (reverse flow).
        """
        if out_port.is_connected and out_port.connection.flow_demand is not None:
            return out_port.connection.flow_demand
        return None

    # -- constant-volume flash ----------------------------------------------
    def _phase_split(self, P, T, z, eos):
        """Flash at (P, T): returns (beta, x, y) with single phases collapsed."""
        res = self._flash(P, T, z, eos)
        beta = res.V
        if beta <= 1e-6:
            return 0.0, dict(z), {}
        if beta >= 1.0 - 1e-6:
            return 1.0, {}, dict(z)
        return beta, res.x, res.y

    def _mixture_molar_volume(self, P, T, z, eos):
        """Overall molar volume [m3/mol] of the two-phase mixture at (P, T).

        Returns (v, beta, x, y). Used both for the initial charge and for the
        constant-volume pressure solve, so the two are always consistent.
        """
        beta, x, y = self._phase_split(P, T, z, eos)
        if beta <= 0.0:
            return self._liquid_molar_volume(z), beta, x, y
        if beta >= 1.0:
            return self._gas_molar_volume(P, T, z, eos), beta, x, y
        v_gas = self._gas_molar_volume(P, T, y, eos)
        v_liq = self._liquid_molar_volume(x)
        return beta * v_gas + (1.0 - beta) * v_liq, beta, x, y

    def _solve_pressure(self, N, z, T, V, eos):
        def flash_at(P):
            return self._phase_split(P, T, z, eos)

        def g(P):
            return N * self._mixture_molar_volume(P, T, z, eos)[0] - V

        P_lo, P_hi = 1.0, 1.0e8
        if g(P_hi) >= 0.0:
            return P_hi, 0.0, dict(z), {}
        if g(P_lo) <= 0.0:
            return P_lo, 1.0, {}, dict(z)

        for _ in range(80):
            Pm = 0.5 * (P_lo + P_hi)
            if g(Pm) > 0.0:
                P_lo = Pm
            else:
                P_hi = Pm
        P = 0.5 * (P_lo + P_hi)
        beta, x, y = flash_at(P)
        return P, beta, x, y

    # -- solver interface ---------------------------------------------------
    def update(self, dt):
        inlet = self.inputs["in"].value
        N = self.states["moles"]
        z = self.states["composition"]
        zf = inlet.composition if inlet is not None else dict(z)
        mm_f = self._molar_mass(zf)
        F_in = inlet.mass_flow / mm_f if (inlet is not None and mm_f > 0) else 0.0

        y = self._phase.get("y", dict(z))
        x = self._phase.get("x", dict(z))
        M_y = self._molar_mass(y)
        M_x = self._molar_mass(x)

        F_vap = self._vap_flow / M_y if M_y > 0 else 0.0
        F_liq = self._liq_flow / M_x if M_x > 0 else 0.0

        N_new = N + (F_in - F_vap - F_liq) * dt
        if N_new <= 0.0:
            N_new = 1e-6

        comps = set(z) | set(zf) | set(y) | set(x)
        z_new = {}
        for c in comps:
            d = (F_in * zf.get(c, 0.0) - F_vap * y.get(c, 0.0) - F_liq * x.get(c, 0.0)) * dt
            z_new[c] = N * z.get(c, 0.0) + d
        s = sum(z_new.values())
        if s <= 0.0:
            z_new = dict(z)
        else:
            z_new = {c: v / s for c, v in z_new.items()}

        self.states["moles"] = N_new
        self.states["composition"] = z_new

    def calculate_outputs(self):
        eos = get_eos(self.config["eos"])
        T = self.config["temperature"]
        V = self.config["volume"]
        N = self.states["moles"]
        z = self.states["composition"]

        P, beta, x, y = self._solve_pressure(N, z, T, V, eos)

        v_liq = self._liquid_molar_volume(x)
        V_liq = N * (1.0 - beta) * v_liq
        level = min(1.0, max(0.0, V_liq / V))

        M_y = self._molar_mass(y)
        M_x = self._molar_mass(x)
        rho_liq = M_x / v_liq if v_liq > 0 else 0.0
        Z_y = eos.z_factor(P, T, y) if y else 1.0

        P_dv = self._downstream(self.outputs["vap_out"], self.config["vap_downstream_pressure"])
        P_dl = self._downstream(self.outputs["liq_out"], self.config["liq_downstream_pressure"])

        head = level * self.config["height"]
        P_liq = P + rho_liq * G * head

        # A signed demand: a positive value is withdrawn, a negative one is
        # gas pushed back in. Gas can always enter; it can leave only if a
        # vapour phase exists.
        dem_v = self._demand(self.outputs["vap_out"])
        if dem_v is not None:
            F_vap = dem_v if (y or dem_v < 0.0) else 0.0
        elif not y:
            F_vap = 0.0
        else:
            F_vap = isa_valve_flow(P, P_dv, T, M_y, Z_y, self.config["vap_exit_Cv"],
                                   self.config["xT"], self.config["gamma"])

        dem_l = self._demand(self.outputs["liq_out"])
        if dem_l is not None:
            F_liq = dem_l if (x or dem_l < 0.0) else 0.0
        elif not x:
            F_liq = 0.0
        else:
            F_liq = isa_liquid_flow(P_liq, P_dl, rho_liq, self.config["liq_exit_Cv"])

        self._vap_flow = F_vap
        self._liq_flow = F_liq
        self.states["pressure"] = P
        self.states["level"] = level
        self._phase = {"V": beta, "x": x, "y": y}

        self.outputs["vap_out"].value = MaterialStream(
            pressure=P, temperature=T, mass_flow=F_vap, composition=dict(y), phase="vapour")
        self.outputs["liq_out"].value = MaterialStream(
            pressure=P_liq, temperature=T, mass_flow=F_liq, composition=dict(x), phase="liquid")
        self.outputs["level"].value = level

        self.inputs["in"].back_pressure = P
