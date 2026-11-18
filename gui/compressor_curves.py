from __future__ import annotations

import ast

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.compressor import (
    N_STATIONS,
    clamp_stations,
    default_stations,
    normalize_design_conditions,
    spline_eval,
)

from .theme import Theme

KELVIN = 273.15
PA_PER_BAR = 1.0e5

PR_COLOR = QColor("#4a8fe0")
EFF_COLOR = QColor("#e09a3c")

LEFT = 84      # room for the pressure-ratio axis spin boxes
RIGHT = 84     # room for the efficiency axis spin boxes
TOP = 26
BOTTOM = 62    # room for the flow axis spin boxes
GRAB_RADIUS = 9.0
SPIN_W = 76
SPIN_H = 24


class CurveCanvas(QWidget):
    """The plot: flow (x), pressure ratio (left axis), efficiency (right axis).

    Both curves pass through 5 stations that share the flow value; dragging a
    handle horizontally moves the station for both curves, dragging vertically
    moves only the curve value at that station.
    """

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setMinimumHeight(300)
        self.setMinimumWidth(LEFT + RIGHT + 480)   # keep the plot itself wide
        self.setMouseTracking(True)
        self._drag = None   # (station, "pr"|"eff")

    # -- coordinates ---------------------------------------------------------
    def plot_rect(self):
        return self.rect().adjusted(LEFT, TOP, -RIGHT, -BOTTOM)

    def value_to_px(self, value, lo, hi, start, span):
        frac = 0.0 if hi <= lo else (value - lo) / (hi - lo)
        return start + span * frac

    def px_to_value(self, px, lo, hi, start, span):
        frac = (px - start) / span if span else 0.0
        return lo + max(0.0, min(1.0, frac)) * (hi - lo)

    def handle_pos(self, station, kind):
        cfg = self.editor.block.config
        rect = self.plot_rect()
        flows = cfg["stations"]["flows"]
        ys = cfg["stations"]["pr" if kind == "pr" else "eff"]
        axis = cfg[f"{kind}_axis"]
        x = self.value_to_px(flows[station], *self.axis_x(), rect.left(), rect.width())
        y = self.value_to_px(
            ys[station], axis["min"], axis["max"], rect.top(), rect.height())
        return x, rect.top() + rect.height() - (y - self.plot_rect().top())

    def axis_x(self):
        fa = self.editor.block.config["flow_axis"]
        return fa["min"], fa["max"]

    def resizeEvent(self, event):
        self._place_axis_spins()
        super().resizeEvent(event)

    def _place_axis_spins(self):
        """Pin each axis min/max spin box to its end of the plot."""
        spins = getattr(self.editor, "spins", {})
        if not spins:
            return
        r = self.plot_rect()
        half = SPIN_H // 2
        positions = {
            ("pr", "max"): (4, r.top() - half),
            ("pr", "min"): (4, r.bottom() - half),
            ("eff", "max"): (self.width() - SPIN_W - 4, r.top() - half),
            ("eff", "min"): (self.width() - SPIN_W - 4, r.bottom() - half),
            ("flow", "min"): (r.left(), r.bottom() + 34),
            ("flow", "max"): (r.right() - SPIN_W, r.bottom() + 34),
        }
        for key, (x, y) in positions.items():
            spins[key].setGeometry(x, y, SPIN_W, SPIN_H)

    def _hit(self, pos):
        best = None
        for station in range(N_STATIONS):
            for kind in ("pr", "eff"):
                x, y = self.handle_pos(station, kind)
                d = (x - pos.x()) ** 2 + (y - pos.y()) ** 2
                if d <= GRAB_RADIUS ** 2 and (best is None or d < best[0]):
                    best = (d, station, kind)
        return None if best is None else (best[1], best[2])

    # -- interaction ----------------------------------------------------------
    def mousePressEvent(self, event):
        hit = self._hit(event.position().toPoint())
        if hit is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = hit
        else:
            self._drag = None
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is None:
            hit = self._hit(event.position().toPoint())
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if hit else Qt.CursorShape.ArrowCursor
            )
            return
        station, kind = self._drag
        self.editor.drag_station(station, kind, event.position().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.editor.commit()
        event.accept()

    # -- painting -------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.plot_rect()
        text_col = QColor(Theme.color("text"))
        sub_col = QColor(Theme.color("subtext"))

        painter.setPen(QPen(sub_col, 1.0))
        painter.drawRect(rect)

        fa = self.editor.block.config["flow_axis"]
        pr_ax = self.editor.block.config["pr_axis"]
        eff_ax = self.editor.block.config["eff_axis"]

        # station guide lines
        pen = QPen(sub_col, 1.0, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        for station in range(N_STATIONS):
            x, y1 = self.handle_pos(station, "pr")
            _, y2 = self.handle_pos(station, "eff")
            painter.drawLine(int(x), int(y1), int(x), int(y2))

        # curves
        levels, effs = self._samples()
        self._draw_curve(painter, levels, pr_ax, PR_COLOR)
        self._draw_curve(painter, effs, eff_ax, EFF_COLOR)

        # handles
        painter.setPen(QPen(text_col, 1.0))
        for station in range(N_STATIONS):
            for kind, color in (("pr", PR_COLOR), ("eff", EFF_COLOR)):
                x, y = self.handle_pos(station, kind)
                painter.setBrush(color)
                painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)

        # axes ticks + labels
        painter.setFont(QFont())
        for axis, color, frac_step, label, side in (
            (pr_ax, PR_COLOR, 0.2, "pressure ratio", "left"),
            (eff_ax, EFF_COLOR, 0.2, "efficiency (%)", "right"),
            (fa, text_col, 0.2, "flow (m³/s)", "bottom"),
        ):
            painter.setPen(QPen(color, 1.0))
            for frac in (0.0, frac_step, 2 * frac_step, 3 * frac_step, 4 * frac_step, 1.0):
                value = axis["min"] + frac * (axis["max"] - axis["min"])
                # the end values of the side axes are the spin boxes, not text
                end_of_side = side != "bottom" and frac in (0.0, 1.0)
                if side == "bottom":
                    px = self.value_to_px(
                        value, fa["min"], fa["max"], rect.left(), rect.width())
                    painter.drawLine(int(px), rect.bottom(), int(px), rect.bottom() + 4)
                    painter.drawText(
                        int(px) - 18, rect.bottom() + 18, 36, 14,
                        Qt.AlignmentFlag.AlignCenter, f"{value:g}")
                else:
                    x = rect.right() if side == "right" else rect.left()
                    py = self.value_to_px(
                        value, axis["min"], axis["max"], rect.top(), rect.height())
                    py = rect.top() + rect.height() - (py - rect.top())
                    if side == "left":
                        painter.drawLine(x - 4, int(py), x, int(py))
                        if not end_of_side:
                            painter.drawText(
                                2, int(py) - 7, LEFT - 8, 14,
                                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                f"{value:g}")
                    else:
                        painter.drawLine(x, int(py), x + 4, int(py))
                        if not end_of_side:
                            painter.drawText(
                                x + 6, int(py) - 7, RIGHT - 8, 14,
                                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                f"{value:g}")

        # title text
        painter.setPen(QPen(PR_COLOR, 1.0))
        painter.drawText(LEFT, 14, rect.width(), 14, Qt.AlignmentFlag.AlignLeft, "pressure ratio")
        painter.setPen(QPen(EFF_COLOR, 1.0))
        painter.drawText(rect.left(), 14, rect.width(), 14, Qt.AlignmentFlag.AlignRight, "efficiency (%)")
        painter.setPen(QPen(text_col, 1.0))
        painter.drawText(rect.left(), rect.bottom() + 32, rect.width(), 14,
                         Qt.AlignmentFlag.AlignCenter, "flow (m³/s)")

    def _samples(self):
        """Dense polyline points for both curves between the first/last flow."""
        cfg = self.editor.block.config
        stations = cfg["stations"]
        flows = stations["flows"]
        pr = stations["pr"]
        eff = stations["eff"]
        levels, effs = [], []
        steps = 240
        span = flows[-1] - flows[0]
        for i in range(steps + 1):
            x = flows[0] + span * i / steps if span else flows[0]
            levels.append((x, spline_eval(flows, pr, x)))
            effs.append((x, spline_eval(flows, eff, x)))
        return levels, effs

    def _draw_curve(self, painter, values, axis, color):
        painter.setPen(QPen(color, 2.0))
        rect = self.plot_rect()
        for i in range(len(values) - 1):
            x0, v0 = values[i]
            x1, v1 = values[i + 1]
            px0 = self.value_to_px(x0, *self.axis_x(), rect.left(), rect.width())
            px1 = self.value_to_px(x1, *self.axis_x(), rect.left(), rect.width())
            py0 = self.value_to_px(v0, axis["min"], axis["max"], rect.top(), rect.height())
            py1 = self.value_to_px(v1, axis["min"], axis["max"], rect.top(), rect.height())
            py0 = rect.top() + rect.height() - (py0 - rect.top())
            py1 = rect.top() + rect.height() - (py1 - rect.top())
            painter.drawLine(int(px0), int(py0), int(px1), int(py1))


class CompressorCurveEditor(QWidget):
    """OEM 100%-speed curve editor: drag-drop plot, point table and axes."""

    edited = pyqtSignal()   # config written; receiver should refresh blocks

    def __init__(self, block, parent=None):
        super().__init__(parent)
        self.block = block
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.canvas = CurveCanvas(self)
        top.addWidget(self.canvas, 1)

        # axis min/max spin boxes live on the plot edges (positioned by the canvas)
        self.spins = {}
        names = {"flow": "Flow", "pr": "Pressure ratio", "eff": "Efficiency"}
        for kind in ("flow", "pr", "eff"):
            axis = block.config[f"{kind}_axis"]
            for bound in ("min", "max"):
                spin = QDoubleSpinBox(self.canvas)
                spin.setRange(-1e9, 1e9)
                spin.setDecimals(2)
                spin.setValue(float(axis[bound]))
                spin.setToolTip(f"{names[kind]} axis {bound}")
                spin.valueChanged.connect(
                    lambda v, k=kind, b=bound: self._axis_changed(k, b, v))
                self.spins[(kind, bound)] = spin
        self.canvas._place_axis_spins()

        # side column: curve points table and reset
        side = QVBoxLayout()
        table_box = QGroupBox("Curve points (shared flow)")
        tlay = QVBoxLayout(table_box)
        self.table = QTableWidget(N_STATIONS, 3)
        self.table.setHorizontalHeaderLabels(
            ["Flow (m³/s)", "Pressure ratio", "Efficiency (%)"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumWidth(340)
        self.table.itemChanged.connect(self._cell_changed)
        tlay.addWidget(self.table)
        side.addWidget(table_box, 1)

        reset = QPushButton("Reset curves")
        reset.setToolTip("Regenerate the typical curves over the current axis ranges")
        reset.clicked.connect(self.reset)
        side.addWidget(reset)
        top.addLayout(side)
        layout.addLayout(top, 1)

        self._refresh_table()
        self._refresh_spins()

    # -- read/write helpers ----------------------------------------------------
    def stations(self):
        return self.block.config["stations"]

    def axes(self):
        cfg = self.block.config
        return (dict(cfg["flow_axis"]), dict(cfg["pr_axis"]), dict(cfg["eff_axis"]))

    def _write_stations(self, stations, emit=True):
        self.block.config["stations"] = {
            k: list(v) for k, v in stations.items()}
        self.block.config_changed(["stations"])
        self._refresh_table()
        self._refresh_spins()
        self.canvas.update()
        if emit:
            self.edited.emit()

    def _write_axis(self, key, axis):
        self.block.config[key] = dict(axis)
        self.block.config_changed([key])
        self.canvas.update()
        self.edited.emit()

    # -- external sync ---------------------------------------------------------
    def refresh_all(self):
        self._refresh_table()
        self._refresh_spins()
        self.canvas.update()

    def _refresh_table(self):
        self._loading = True
        stations = self.stations()
        rows = list(zip(stations["flows"], stations["pr"], stations["eff"]))
        for r, (flow, pr, eff) in enumerate(rows):
            for c, value in enumerate((flow, pr, eff)):
                item = self.table.item(r, c)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(r, c, item)
                item.setText(f"{value:g}")
        self._loading = False

    def _refresh_spins(self):
        self._loading = True
        for (kind, bound), spin in self.spins.items():
            axis = self.block.config[f"{kind}_axis"]
            spin.setValue(float(axis[bound]))
        self._loading = False

    # -- user actions ----------------------------------------------------------
    def drag_station(self, station, kind, pos):
        cfg = self.block.config
        rect = self.canvas.plot_rect()
        fa = cfg["flow_axis"]
        flows = list(cfg["stations"]["flows"])
        new_flow = self.canvas.px_to_value(
            pos.x(), fa["min"], fa["max"], rect.left(), rect.width())
        eps = (fa["max"] - fa["min"]) / 1000.0
        if station > 0:
            new_flow = max(new_flow, flows[station - 1] + eps)
        if station < N_STATIONS - 1:
            new_flow = min(new_flow, flows[station + 1] - eps)
        flows[station] = max(fa["min"], min(fa["max"], new_flow))

        axis = cfg[f"{kind}_axis"]
        ys = list(cfg["stations"][kind])
        new_y = self.canvas.px_to_value(
            pos.y(), axis["max"], axis["min"], rect.top(), rect.height())
        ys[station] = max(axis["min"], min(axis["max"], new_y))

        stations = dict(cfg["stations"])
        stations["flows"] = flows
        stations[kind] = ys
        self._write_stations(stations, emit=False)

    def commit(self):
        self.edited.emit()

    def reset(self):
        self._write_stations(default_stations(*self.axes()))

    def _axis_changed(self, kind, bound, value):
        if self._loading:
            return
        key = f"{kind}_axis"
        axis = dict(self.block.config[key])
        if bound == "min" and value >= axis["max"]:
            self._refresh_spins()
            return
        if bound == "max" and value <= axis["min"]:
            self._refresh_spins()
            return
        axis[bound] = float(value)
        axis_map = {k: dict(self.block.config[k])
                    for k in ("flow_axis", "pr_axis", "eff_axis")}
        axis_map[key] = axis
        self.block.config["flow_axis"] = axis_map["flow_axis"]
        self.block.config["pr_axis"] = axis_map["pr_axis"]
        self.block.config["eff_axis"] = axis_map["eff_axis"]
        stations = clamp_stations(self.block.config["stations"],
                                  axis_map["flow_axis"], axis_map["pr_axis"],
                                  axis_map["eff_axis"])
        self._write_stations(stations)

    def _cell_changed(self, item):
        if self._loading:
            return
        row, col = item.row(), item.column()
        field = ("flows", "pr", "eff")[col]
        try:
            value = float(item.text())
        except ValueError:
            self._refresh_table()
            return
        if value != value or value in (float("inf"), float("-inf")):
            self._refresh_table()
            return
        stations = {
            "flows": list(self.stations()["flows"]),
            "pr": list(self.stations()["pr"]),
            "eff": list(self.stations()["eff"]),
        }
        stations[field][row] = value
        flow_axis, pr_axis, eff_axis = self.axes()
        stations = clamp_stations(stations, flow_axis, pr_axis, eff_axis)
        self._write_stations(stations)


class DesignConditionsBox(QGroupBox):
    """Suction conditions the OEM curves were drawn for.

    Pressure is entered in bar(a) and temperature in degC; both are stored in
    SI (Pa, K) under ``config["design_conditions"]``. The composition is a
    ``{component: fraction}`` literal, normalised to sum to 1 on apply.
    """

    def __init__(self, block, parent=None):
        super().__init__("Curve design conditions", parent)
        self.block = block
        self._composition = None
        dc = normalize_design_conditions(block.config.get("design_conditions"))

        form = QFormLayout(self)
        self.pressure = QDoubleSpinBox()
        self.pressure.setRange(0.001, 1.0e4)
        self.pressure.setDecimals(4)
        self.pressure.setSuffix(" bar a")
        self.pressure.setValue(dc["pressure"] / PA_PER_BAR)
        self.pressure.setToolTip("Inlet suction pressure of the curve design point")
        form.addRow("Suction pressure", self.pressure)

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(-KELVIN + 0.01, 2000.0)
        self.temperature.setDecimals(2)
        self.temperature.setSuffix(" °C")
        self.temperature.setValue(dc["temperature"] - KELVIN)
        self.temperature.setToolTip("Inlet suction temperature of the curve design point")
        form.addRow("Suction temperature", self.temperature)

        self.composition = QLineEdit(repr(dc["composition"]))
        self.composition.setToolTip(
            "Gas composition as {component: mole fraction}, e.g. "
            "{'methane': 0.9, 'ethane': 0.1}; normalised on apply")
        form.addRow("Gas composition", self.composition)

        help_text = QLabel(
            "Enter the composition as <b>{'component': fraction, ...}</b>, e.g. "
            "<code>{'methane': 0.9, 'ethane': 0.07, 'nitrogen': 0.03}</code>. "
            "Use lower-case names in quotes (methane, ethane, propane, n-butane, "
            "isobutane, nitrogen, carbondioxide, hydrogensulfide, water, ...), "
            "separated by commas. Fractions are mole fractions, they need not add "
            "up to 1 (percentages work too), and are normalised on Apply.")
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.TextFormat.RichText)
        help_text.setStyleSheet("color: gray;")
        form.addRow(help_text)

    def validate(self):
        """Parse the composition; raises ValueError with a user message."""
        try:
            value = ast.literal_eval(self.composition.text())
        except (ValueError, SyntaxError):
            raise ValueError("design composition: not a valid {component: fraction} literal")
        if not isinstance(value, dict) or not value:
            raise ValueError("design composition: expected a non-empty dict")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
                   for v in value.values()):
            raise ValueError("design composition: fractions must be non-negative numbers")
        total = float(sum(value.values()))
        if total <= 0:
            raise ValueError("design composition: fractions must not all be zero")
        self._composition = {str(k): float(v) / total for k, v in value.items()}

    def apply(self):
        """Write the validated values into the block; True when changed."""
        if self._composition is None:
            return False
        new = {
            "pressure": round(self.pressure.value() * PA_PER_BAR, 6),
            "temperature": round(self.temperature.value() + KELVIN, 6),
            "composition": self._composition,
        }
        changed = new != self.block.config.get("design_conditions")
        self.block.config["design_conditions"] = new
        self.composition.setText(repr(new["composition"]))
        return changed
