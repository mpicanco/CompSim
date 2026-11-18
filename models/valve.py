from __future__ import annotations

from core.base import ProcessBlock
from core.ports import PortType
from core.thermo import get_eos
from core.thermo.joule_thomson import throttle_temperature
from core.flow import isa_valve_flow, isa_liquid_flow
from core.data import liquid_density

EQ_PCT_RANGEABILITY = 50.0
P_MAX = 1.0e8  # Pa, upper bracket for pressure solves


class Valve(ProcessBlock):
    """Control valve following ISA-75.01 sizing (compressible or liquid).

    Pressure/flow coupling with the neighbours:

    * **Pressure mode** - the upstream block is a pressure node (StreamIn,
      Vessel, compressor, ...). The valve computes

          w = N6 * Cv * P1 * Y * sqrt( x * M / (T1 * Z1) )      (gas)
          w = N1 * Cv * sqrt( dP / G ) * rho                     (liquid)

      from the inlet pressure P1 and the downstream back-pressure P2, and
      publishes ``w`` as ``flow_demand`` on its inlet so the upstream pressure
      node withdraws exactly that flow. ``w`` is signed: when the downstream
      pressure is higher, ``w`` is negative and the upstream node receives gas
      back through the valve.

    * **Joule-Thomson** - for gas flow, the outlet temperature follows the
      isenthalpic throttle from the high to the low pressure side.

    * **Series mode** - the upstream block is another valve (no capacity in
      between). The intermediate pressure is solved so that the flow through
      the upstream chain equals the flow through this valve (forward flow only;
      reverse flow is not solved in series chains); it is imposed as
      back-pressure on the inlet.

    The effective Cv follows the installed characteristic (linear or modified
    equal-percentage) from the 0-100 % opening signal; 0 % is tight shut-off.
    """

    block_type = "Valve"
    category = "Equipment"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_input("in")
        self.add_input("opening", PortType.SIGNAL)
        self.add_output("out")
        self.config = {
            "Cv": 1.0,
            "opening": 100.0,             # %
            "characteristic": "linear",   # linear | equal-percentage
            "xT": 0.7,
            "gamma": 1.3,
            "eos": "Ideal Gas",
            "downstream_pressure": 1.0e5,
        }
        self._busy = False  # recursion guard for series chains / loops

    def update(self, dt):
        pass

    # -- characteristic ------------------------------------------------------
    def _opening(self):
        signal = self.inputs["opening"].value
        opening = self.config["opening"] if signal is None else float(signal)
        return max(0.0, min(100.0, opening))

    def _effective_cv(self, opening):
        cv = self.config["Cv"]
        frac = max(0.0, min(100.0, opening)) / 100.0
        if self.config["characteristic"] == "equal-percentage":
            R = EQ_PCT_RANGEABILITY
            # modified equal-percentage: 0 at closed, Cv at fully open
            return cv * (R ** (frac - 1.0) - 1.0 / R) / (1.0 - 1.0 / R)
        return cv * frac

    # -- flow law --------------------------------------------------------------
    def _flow(self, P1, P2, inlet):
        """Signed mass flow [kg/s] through this valve alone, P1 vs P2.

        Positive for P1 > P2 (forward). Negative when P2 > P1: gas then flows
        back from the downstream side into the inlet node.
        """
        Cv = self._effective_cv(self._opening())
        if Cv <= 0.0 or P1 == P2:
            return 0.0
        comp = inlet.composition
        if inlet.phase == "liquid":
            return isa_liquid_flow(P1, P2, liquid_density(comp), Cv)
        eos = get_eos(self.config["eos"])
        Z1 = eos.z_factor(P1, inlet.temperature, comp)
        M = eos.molar_mass(comp)
        return isa_valve_flow(P1, P2, inlet.temperature, M, Z1, Cv,
                              self.config["xT"], self.config["gamma"])

    def _upstream_valve(self):
        port = self.inputs["in"]
        if not port.is_connected:
            return None
        owner = port.connection.owner
        if isinstance(owner, Valve) and not owner._busy:
            return owner
        return None

    def supply_pressure(self):
        """Pressure of the pressure node feeding this valve chain."""
        inlet = self.inputs["in"].value
        up = self._upstream_valve()
        if up is not None:
            self._busy = True
            try:
                return up.supply_pressure()
            finally:
                self._busy = False
        return inlet.pressure if inlet is not None else 0.0

    def flow_at(self, P2):
        """Flow through this valve *and its upstream valve chain* for outlet P2.

        Returns ``(w, P1)`` where ``P1`` is this valve's inlet pressure.
        """
        inlet = self.inputs["in"].value
        if inlet is None:
            return 0.0, P2
        up = self._upstream_valve()
        if up is None:
            return self._flow(inlet.pressure, P2, inlet), inlet.pressure

        self._busy = True
        try:
            P_hi = min(up.supply_pressure(), P_MAX)
            if P_hi <= P2:
                return 0.0, P_hi
            # h(Pm) = upstream flow (decreasing in Pm) - own flow (increasing)
            lo, hi = P2, P_hi
            for _ in range(50):
                Pm = 0.5 * (lo + hi)
                w_up, _ = up.flow_at(Pm)
                if w_up > self._flow(Pm, P2, inlet):
                    lo = Pm
                else:
                    hi = Pm
                if hi - lo < 1e-6 * max(1.0, hi):
                    break
            Pm = 0.5 * (lo + hi)
            return self._flow(Pm, P2, inlet), Pm
        finally:
            self._busy = False

    # -- solver interface ------------------------------------------------------
    def calculate_outputs(self):
        in_port = self.inputs["in"]
        inlet = in_port.value
        if inlet is None:
            in_port.back_pressure = None
            in_port.flow_demand = None
            self.outputs["out"].value = None
            return

        P2 = self.config["downstream_pressure"]
        out_port = self.outputs["out"]
        if out_port.is_connected and out_port.connection.back_pressure is not None:
            P2 = out_port.connection.back_pressure

        w, P1 = self.flow_at(P2)

        if self._upstream_valve() is not None:
            # series mode: impose the intermediate pressure on the upstream valve
            in_port.back_pressure = P1
            in_port.flow_demand = None
        else:
            # pressure mode: tell the upstream pressure node how much we draw
            in_port.back_pressure = None
            in_port.flow_demand = w

        out = inlet.copy()
        out.pressure = P2
        out.mass_flow = w
        # Joule-Thomson: throttling is isenthalpic, so a gas stream that flows
        # through the valve leaves at a different temperature. Liquids and
        # stagnant valves are not throttled. For reverse flow the throttle runs
        # from the downstream side; its gas is taken to be the inlet gas.
        if inlet.phase != "liquid" and w != 0.0:
            eos = get_eos(self.config["eos"])
            out.temperature = throttle_temperature(
                eos, max(P1, P2), min(P1, P2), inlet.temperature, inlet.composition)
        self.outputs["out"].value = out
