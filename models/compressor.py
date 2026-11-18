from __future__ import annotations

from core.base import ProcessBlock
from core.ports import MaterialStream, PortType
from core.thermo import get_eos


# -- OEM performance curve data ------------------------------------------------
# Five points shared by both curves (the flows are the x values for both). Each
# curve is evaluated as a Catmull-Rom-like cubic spline through its points.
N_STATIONS = 5

# flow stations span the full flow axis (surge end to choke end)
_FLOW_FRACTIONS = (0.0, 0.25, 0.50, 0.75, 1.00)

# design-point parameters replaced by the OEM curves; dropped on config load
RETIRED_KEYS = ("design_pressure_ratio", "design_flow", "design_speed",
                "polytropic_efficiency")


def default_design_conditions():
    """Suction conditions the OEM curves were drawn for (SI: Pa, K, mole fr.)."""
    return {"pressure": 1.0e5, "temperature": 293.15,
            "composition": {"methane": 1.0}}


def normalize_design_conditions(value):
    """Fill missing entries of a (possibly partial/legacy) design-conditions dict."""
    base = default_design_conditions()
    if isinstance(value, dict):
        for key in ("pressure", "temperature"):
            if isinstance(value.get(key), (int, float)):
                base[key] = float(value[key])
        comp = value.get("composition")
        if isinstance(comp, dict) and comp:
            base["composition"] = {str(k): float(v) for k, v in comp.items()}
    return base


def default_axis(**kwargs):
    """Axis body with the project default range (min 0, max 100)."""
    return {"min": float(kwargs.get("min", 0.0)),
            "max": float(kwargs.get("max", 100.0))}

# the default pressure-ratio curve starts at this fraction of its axis span:
# 2/3 of the default 0..3 axis, i.e. a pressure ratio of 2 at surge
_PR_START = 2.0 / 3.0


def _pr_fraction(f):
    """Pressure-ratio axis fraction: decreasing half-parabola from
    ``_PR_START`` at f=0 down to the axis minimum at f=1."""
    return _PR_START * (1.0 - f * f)

def _eff_fraction(f):
    """Efficiency axis fraction: upside-down parabola, peak 1.0 at f=0.5,
    rising from and falling back to 0.5 of the axis."""
    return 0.50 + 0.50 * (1.0 - (2.0 * f - 1.0) ** 2)

def default_stations(flow_axis=None, pr_axis=None, eff_axis=None):
    """Default 100 % rotation curves scaled to fill the given axis ranges."""
    flow_axis = flow_axis or default_axis()
    pr_axis = pr_axis or default_axis()
    eff_axis = eff_axis or default_axis()

    def axis_span(axis):
        return float(axis["min"]), float(axis["max"])

    lo_f, hi_f = axis_span(flow_axis)
    lo_p, hi_p = axis_span(pr_axis)
    lo_e, hi_e = axis_span(eff_axis)

    flows = [round(lo_f + f * (hi_f - lo_f), 6) for f in _FLOW_FRACTIONS]
    pr = [round(lo_p + (hi_p - lo_p) * _pr_fraction(f), 6) for f in _FLOW_FRACTIONS]
    eff = [round(lo_e + (hi_e - lo_e) * _eff_fraction(f), 6) for f in _FLOW_FRACTIONS]

    return {"flows": flows, "pr": pr, "eff": eff}


def clamp_stations(stations, flow_axis, pr_axis, eff_axis):
    """Snap the stations into the current axis ranges.

    Flows keep the station order (sorted, minimum separation enforced within
    the range), curve values stay inside their own vertical axis. Returns a
    fresh dict/list structure ready to be written back to ``config``.
    """
    lo = float(flow_axis["min"])
    hi = float(flow_axis["max"])
    eps = (hi - lo) / 1000.0 if hi > lo else 0.0
    clamped = sorted(min(hi, max(lo, float(f))) for f in stations["flows"])
    for i in range(1, len(clamped)):
        if clamped[i] < clamped[i - 1] + eps:
            clamped[i] = min(hi, clamped[i - 1] + eps)

    def snap(axis, values):
        a_lo = float(axis["min"])
        a_hi = float(axis["max"])
        return [round(min(a_hi, max(a_lo, float(v))), 6) for v in values[:N_STATIONS]]

    return {
        "flows": [round(f, 6) for f in clamped],
        "pr": snap(pr_axis, stations["pr"]),
        "eff": snap(eff_axis, stations["eff"]),
    }


def _tangents(xs, ys):
    """Slopes at each node (three-point central difference, clamped at ends)."""
    n = len(xs)
    slopes = []
    for j in range(n):
        x0, y0 = xs[max(0, j - 1)], ys[max(0, j - 1)]
        x1, y1 = xs[min(n - 1, j + 1)], ys[min(n - 1, j + 1)]
        slopes.append((y1 - y0) / (x1 - x0) if x1 > x0 else 0.0)
    return slopes


def spline_eval(xs, ys, x):
    """Cubic Hermite interpolation through the curve points."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    m = _tangents(xs, ys)
    for j in range(len(xs) - 1):
        if x < xs[j + 1]:
            h = xs[j + 1] - xs[j]
            t = (x - xs[j]) / h if h > 0.0 else 0.0
            t2 = t * t
            t3 = t2 * t
            return (2 * t3 - 3 * t2 + 1) * ys[j] \
                + (t3 - 2 * t2 + t) * h * m[j] \
                + (-2 * t3 + 3 * t2) * ys[j + 1] \
                + (t3 - t2) * h * m[j + 1]
    return ys[-1]


class Compressor(ProcessBlock):
    """Centrifugal compressor with an OEM 100 %-speed performance curve.

    The curve set consists of two 5-point splines over inlet volumetric flow
    (m3/s). The default pressure-ratio curve is a decreasing half-parabola
    from 2/3 of its axis (a ratio of 2 on the default 0-3 axis) down to the
    axis minimum; the default efficiency curve is an upside-down parabola
    peaking at the efficiency axis maximum, drawn from and back to half the
    axis. Flows cover the axis from surge (0) to choke (1). Off-design
    operation follows the affinity laws: the curve flow
    is scaled 1/N and the pressure rise scales with N^2. The efficiency read
    from the curve drives the polytropic discharge temperature.
    """

    block_type = "Compressor"
    category = "Equipment"

    def __init__(self, name=None):
        super().__init__(name)
        self.add_input("in")
        self.add_input("speed", PortType.SIGNAL)
        self.add_output("out")
        flow_axis = default_axis(min=0.0, max=100.0)
        pr_axis = default_axis(min=0.0, max=3.0)
        eff_axis = default_axis(min=0.0, max=100.0)
        self.config = {
            "speed": 100.0,
            "gamma": 1.3,
            "flow_axis": flow_axis,
            "pr_axis": pr_axis,
            "eff_axis": eff_axis,
            "stations": default_stations(flow_axis, pr_axis, eff_axis),
            # suction conditions the curves are referred to (user data)
            "design_conditions": default_design_conditions(),
        }

    def config_changed(self, keys=None):
        # retire the pre-curve design-point parameters from loaded files
        for key in RETIRED_KEYS:
            self.config.pop(key, None)
        self.config["design_conditions"] = normalize_design_conditions(
            self.config.get("design_conditions"))

    def _station_sets(self):
        stations = self.config.get("stations") or default_stations()
        flows = stations.get("flows") or [0.0] * N_STATIONS
        pr = stations.get("pr") or [0.0] * N_STATIONS
        eff = stations.get("eff") or [0.0] * N_STATIONS
        return list(flows), list(pr), list(eff)

    def update(self, dt):
        pass

    def calculate_outputs(self):
        inlet = self.inputs["in"].value
        if inlet is None:
            self.outputs["out"].value = None
            return
        signal = self.inputs["speed"].value
        speed = self.config["speed"] if signal is None else float(signal)
        n = max(0.0, float(speed)) / 100.0

        # inlet volumetric flow: 100 % curve is read at 1/N times the actual
        # flow (affinity: flow ~ N); head/pressure-rise scales with N^2
        flow_axis = self.config["flow_axis"]
        flows, pr, eff = self._station_sets()
        q = self._inlet_volume_flow(inlet)
        q0 = q / n if n > 0.0 else float("inf")
        q_lo = min(flow_axis["min"], flows[0])
        q_hi = max(flow_axis["max"], flows[-1])
        q0_clamped = min(max(q0, q_lo), q_hi) if q0 != float("inf") else q_hi

        pr0 = max(1.0, float(spline_eval(flows, pr, q0_clamped)))
        eta = float(spline_eval(flows, eff, q0_clamped)) / 100.0

        if n > 0.0:
            ratio = 1.0 + (pr0 - 1.0) * n * n
        else:
            ratio = 1.0

        out = inlet.copy()
        out.pressure = inlet.pressure * max(ratio, 0.0)

        # polytropic discharge temperature from the curve efficiency
        eta_poly = eta if 0.05 <= eta <= 1.0 else None
        if n > 0.0 and ratio > 1.0 and eta_poly:
            gamma = float(self.config.get("gamma", 1.3))
            exponent = (gamma - 1.0) / (gamma * eta_poly)
            out.temperature = inlet.temperature * max(ratio, 1.0) ** exponent
        else:
            out.temperature = inlet.temperature

        self.outputs["out"].value = out

    @staticmethod
    def _inlet_volume_flow(inlet: MaterialStream) -> float:
        """Actual (inlet-condition) volumetric flow [m3/s]; 0 when unknown."""
        if not inlet.mass_flow or inlet.pressure is None or inlet.temperature is None:
            return 0.0
        try:
            rho = get_eos("Ideal Gas").density(
                inlet.pressure, inlet.temperature, inlet.composition
            )
        except Exception:
            rho = None
        if not rho or rho <= 0.0:
            return 0.0
        return inlet.mass_flow / rho
