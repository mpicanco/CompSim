from __future__ import annotations

import ast

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QWidget,
)

from core.thermo import EOS_NAMES
from core.variables import block_variables, resolve, is_scalar
from .compressor_curves import CompressorCurveEditor, DesignConditionsBox

# config keys rendered as a dedicated editor widget instead of generic fields
CUSTOM_KEYS = {
    "Compressor": ("flow_axis", "pr_axis", "eff_axis", "stations",
                   "design_conditions"),
}

# config keys whose value must be one of a fixed set of options
CHOICES = {
    "eos": EOS_NAMES,
    "characteristic": ["linear", "equal-percentage"],
    "flash_method": ["wilson", "raoult", "eos"],
}

LIVE_REFRESH_MS = 500


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if is_scalar(value):
        return f"{value:.6g}"
    return str(value)


class ConfigDialog(QDialog):
    """Configuration panel for one block (opens on double-click).

    * **Parameters** - the block's ``config``: bool/int/float use spin boxes,
      enumerated keys a drop-down, dict/list values (composition, fractions)
      are edited as Python literals and validated before they are accepted.
    * **Live values** - read-only states and port values, refreshed while the
      panel is open so the effect of a change can be watched while running.

    The panel is non-modal: *Apply* writes the parameters and keeps it open,
    *OK* writes and closes, *Cancel* closes without writing. ``applied`` is
    emitted after every write.
    """

    applied = pyqtSignal(object)   # the block

    def __init__(self, block, parent=None):
        super().__init__(parent)
        self.block = block
        self._widgets = {}   # key -> widget
        self._kinds = {}     # key -> kind
        self._parsed = {}    # key -> validated literal value
        self._live = []      # (label widget, path)
        self._design = None  # DesignConditionsBox (compressor only)
        self.setWindowTitle(f"Edit {block.name}  ({block.block_type})")
        self.setMinimumWidth(420)
        if block.block_type == "Compressor":
            # Width only: a fixed minimum height here would be smaller than the
            # content's sizeHint, so Qt squeezes the curve plot and table.
            self.setMinimumWidth(900)

        layout = QVBoxLayout(self)

        header = QLabel(f"<b>{block.name}</b> &nbsp;·&nbsp; {block.block_type}")
        layout.addWidget(header)
        doc = (type(block).__doc__ or "").strip().split("\n\n")[0]
        if doc:
            summary = QLabel(" ".join(doc.split()))
            summary.setWordWrap(True)
            summary.setStyleSheet("color: gray;")
            layout.addWidget(summary)

        # Compressor: wide layout, parameters and live values on the left,
        # the curve editor on the right. Other blocks stack vertically.
        custom = CUSTOM_KEYS.get(block.block_type, ())
        if custom:
            columns = QHBoxLayout()
            layout.addLayout(columns, 1)
            left = QVBoxLayout()
            right = QVBoxLayout()
            columns.addLayout(left, 1)
            columns.addLayout(right, 3)
        else:
            left = right = layout

        # -- parameters ------------------------------------------------------
        params = QGroupBox("Parameters")
        self.form = QFormLayout(params)
        generic_keys = [k for k in block.config if k not in custom]
        if generic_keys:
            for key in generic_keys:
                self.form.addRow(key, self._make_widget(key, block.config[key]))
        else:
            self.form.addRow(QLabel("Generic parameters edited above the curve set."))
        left.addWidget(params)

        # -- dedicated editors (performance curves) ---------------------------
        if custom:
            editor = CompressorCurveEditor(block)
            editor.edited.connect(self._on_curves_edited)
            right.addWidget(editor, 1)

        # -- live values -----------------------------------------------------
        live_vars = [(d, p) for d, p in block_variables(block) if p[0] != "config"]
        if live_vars:
            live = QGroupBox("Live values")
            live_form = QFormLayout()
            for display, path in live_vars:
                label = QLabel()
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                live_form.addRow(display.replace(f"{block.name}", "", 1).lstrip(":. ") or display, label)
                self._live.append((label, path))
            host = QWidget()
            host.setLayout(live_form)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(host)
            scroll.setMinimumHeight(min(200, 24 * len(live_vars) + 12))
            scroll.setMaximumHeight(240)
            box_layout = QVBoxLayout(live)
            box_layout.addWidget(scroll)
            left.addWidget(live)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.refresh_live)
            self._timer.start(LIVE_REFRESH_MS)
            self.refresh_live()
        # -- curve design (suction) conditions --------------------------------
        if "design_conditions" in custom:
            self._design = DesignConditionsBox(block)
            left.addWidget(self._design)
        if custom:
            left.addStretch(1)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #e5534b;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_clicked)
        layout.addWidget(buttons)

        if custom:
            self.resize(self.sizeHint())   # open at the wide natural size

    def _on_curves_edited(self):
        self.applied.emit(self.block)

    # -- widgets -------------------------------------------------------------
    def _make_widget(self, key, value):
        if key in CHOICES and isinstance(value, str):
            w = QComboBox()
            options = list(CHOICES[key])
            if value not in options:
                options.insert(0, value)
            w.addItems(options)
            w.setCurrentText(value)
            self._kinds[key] = "choice"
        elif isinstance(value, bool):
            w = QCheckBox()
            w.setChecked(value)
            self._kinds[key] = "bool"
        elif isinstance(value, int):
            w = QSpinBox()
            w.setRange(-10 ** 9, 10 ** 9)
            w.setValue(value)
            self._kinds[key] = "int"
        elif isinstance(value, float):
            w = QDoubleSpinBox()
            w.setRange(-1e12, 1e12)
            w.setDecimals(6)
            w.setValue(value)
            w.setSingleStep(abs(value) * 0.05 if value else 1.0)
            self._kinds[key] = "float"
        elif isinstance(value, str):
            w = QLineEdit(value)
            self._kinds[key] = "str"
        else:
            w = QLineEdit(repr(value))
            self._kinds[key] = "literal"
        self._widgets[key] = w
        return w

    def refresh_live(self):
        for label, path in self._live:
            try:
                value = resolve(self.block, path)
            except (KeyError, IndexError):
                value = None
            label.setText(_fmt(value))

    # -- validation ----------------------------------------------------------
    def _parse_literal(self, key):
        current = self.block.config[key]
        text = self._widgets[key].text()
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            raise ValueError(f"{key}: not a valid literal")
        if type(value) is not type(current):
            raise ValueError(f"{key}: expected a {type(current).__name__}")
        if isinstance(value, dict):
            if not value or not all(isinstance(v, (int, float)) and v >= 0 for v in value.values()):
                raise ValueError(f"{key}: values must be non-negative numbers")
            total = float(sum(value.values()))
            if total <= 0:
                raise ValueError(f"{key}: fractions must not all be zero")
            value = {str(k): float(v) / total for k, v in value.items()}   # normalise
        elif isinstance(value, list):
            if not all(isinstance(v, (int, float)) and v >= 0 for v in value):
                raise ValueError(f"{key}: values must be non-negative numbers")
            value = [float(v) for v in value]
        return value

    def _validate(self):
        self._parsed.clear()
        try:
            for key, kind in self._kinds.items():
                if kind == "literal":
                    self._parsed[key] = self._parse_literal(key)
            if self._design is not None:
                self._design.validate()
        except ValueError as e:
            self.error_label.setText(str(e))
            return False
        self.error_label.clear()
        return True

    def apply_clicked(self):
        if self._validate():
            self.apply()

    def accept(self):
        if not self._validate():
            return
        self.apply()
        super().accept()

    def apply(self):
        """Write the edited parameters into the block; returns changed keys."""
        changed = []
        for key in list(self.block.config):
            w = self._widgets.get(key)
            if w is None:
                continue
            kind = self._kinds[key]
            if kind == "bool":
                new = w.isChecked()
            elif kind in ("int", "float"):
                new = w.value()
            elif kind == "choice":
                new = w.currentText()
            elif kind == "str":
                new = w.text()
            elif kind == "literal":
                if key not in self._parsed:
                    continue
                new = self._parsed[key]
            else:
                continue
            if new != self.block.config[key]:
                self.block.config[key] = new
                changed.append(key)
        if self._design is not None and self._design.apply():
            changed.append("design_conditions")
        if changed:
            self.block.config_changed(changed)
        # normalised literals (e.g. composition) are shown as stored
        for key, kind in self._kinds.items():
            if kind == "literal":
                self._widgets[key].setText(repr(self.block.config[key]))
        self.refresh_live()
        self.applied.emit(self.block)
        return changed
