from __future__ import annotations

import json
from uuid import uuid4

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFrame,
    QLabel,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QScrollArea,
    QPushButton,
    QSpinBox,
    QSplitter,
    QSizePolicy,
)

from core.variables import block_variables, resolve, is_scalar

VAR_MIME = "application/x-comp-sim-var"
CHART_MIME = "application/x-comp-sim-chart"


class VariableTree(QTreeWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

    def refresh(self):
        self.clear()
        for block in self.controller.graph.nodes:
            top = QTreeWidgetItem([block.name])
            top.setData(0, Qt.ItemDataRole.UserRole, block.instance_id)
            for display, path in block_variables(block):
                child = QTreeWidgetItem([display])
                child.setData(0, Qt.ItemDataRole.UserRole, json.dumps([block.instance_id, path]))
                top.addChild(child)
            self.addTopLevelItem(top)
        self.expandAll()

    def mimeTypes(self):
        return [VAR_MIME]

    def mimeData(self, items):
        if not items:
            return None
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return None
        mime = QMimeData()
        mime.setData(VAR_MIME, str(data).encode())
        return mime


class ChartTile(QFrame):
    reorder_requested = pyqtSignal(str, str)
    close_requested = pyqtSignal(str)

    def __init__(self, controller, title="Chart", parent=None):
        super().__init__(parent)
        self.controller = controller
        self.uid = uuid4().hex[:8]
        self.pens = []
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.setMinimumSize(320, 240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 2, 4, 2)
        self.handle = QLabel(title)
        self.handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.handle.setToolTip("Drag to reorder; drop variables here to plot")
        close = QToolButton()
        close.setText("x")
        close.clicked.connect(lambda: self.close_requested.emit(self.uid))
        header_layout.addWidget(self.handle)
        header_layout.addStretch(1)
        header_layout.addWidget(close)
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(header)

        self.figure = Figure(figsize=(3, 2), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.axes.grid(True, alpha=0.3)
        self.axes.set_xlabel("time (s)")
        layout.addWidget(self.canvas, 1)

        self.handle.mousePressEvent = self._handle_press
        self.handle.mouseMoveEvent = self._handle_move

    def _handle_press(self, event):
        self._press = event.position().toPoint()

    def _handle_move(self, event):
        if not hasattr(self, "_press"):
            return
        if (event.position().toPoint() - self._press).manhattanLength() < 8:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(CHART_MIME, self.uid.encode())
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def add_pen(self, block_id, path, label):
        if any(p["block_id"] == block_id and p["path"] == path for p in self.pens):
            return
        line, = self.axes.plot([], [], label=label, linewidth=1.4)
        self.pens.append({"block_id": block_id, "path": path, "label": label,
                          "x": [], "y": [], "line": line})
        self.axes.legend(loc="best", fontsize=7)
        self.canvas.draw_idle()

    def append_sample(self, t):
        changed = False
        for p in self.pens:
            block = self.controller.graph.get_node(p["block_id"])
            try:
                value = resolve(block, p["path"]) if block is not None else None
            except (KeyError, IndexError):
                value = None
            if not is_scalar(value):
                continue
            p["x"].append(t)
            p["y"].append(float(value))
            p["line"].set_data(p["x"], p["y"])
            changed = True
        if changed:
            self.axes.relim()
            self.axes.autoscale_view()
            self.canvas.draw_idle()

    def clear_data(self):
        for p in self.pens:
            p["x"].clear()
            p["y"].clear()
            p["line"].set_data([], [])
        self.canvas.draw_idle()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(VAR_MIME) or event.mimeData().hasFormat(CHART_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(VAR_MIME) or event.mimeData().hasFormat(CHART_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(VAR_MIME):
            block_id, path = json.loads(bytes(md.data(VAR_MIME)).decode())
            block = self.controller.graph.get_node(block_id)
            if block is not None:
                label = ".".join([block.name] + path)
                self.add_pen(block_id, path, label)
            event.acceptProposedAction()
        elif md.hasFormat(CHART_MIME):
            source_uid = bytes(md.data(CHART_MIME)).decode()
            if source_uid != self.uid:
                self.reorder_requested.emit(source_uid, self.uid)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class TrendsWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.charts = []
        self.columns = 2

        layout = QHBoxLayout(self)

        left = QWidget()
        left.setFixedWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(QLabel("Process Variables"))
        self.tree = VariableTree(controller)
        self.tree.refresh()
        left_layout.addWidget(self.tree)
        refresh_btn = QPushButton("Refresh Variables")
        refresh_btn.clicked.connect(self.tree.refresh)
        left_layout.addWidget(refresh_btn)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        toolbar = QHBoxLayout()
        add_btn = QPushButton("+ Add Chart")
        add_btn.clicked.connect(self.add_chart)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(QLabel("Columns:"))
        self.col_spin = QSpinBox()
        self.col_spin.setRange(1, 6)
        self.col_spin.setValue(self.columns)
        self.col_spin.valueChanged.connect(self.set_columns)
        toolbar.addWidget(self.col_spin)
        toolbar.addStretch(1)
        right_layout.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(6)
        self.scroll.setWidget(self.grid_host)
        right_layout.addWidget(self.scroll)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def add_chart(self):
        title = f"Chart {len(self.charts) + 1}"
        tile = ChartTile(self.controller, title)
        tile.reorder_requested.connect(self.reorder)
        tile.close_requested.connect(self._remove_chart)
        self.charts.append(tile)
        self._relayout()
        return tile

    def _remove_chart(self, uid):
        tile = next((c for c in self.charts if c.uid == uid), None)
        if tile is None:
            return
        self.charts.remove(tile)
        self._relayout()
        tile.deleteLater()

    def _relayout(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        for i, tile in enumerate(self.charts):
            self.grid.addWidget(tile, i // self.columns, i % self.columns)

    def set_columns(self, value):
        self.columns = value
        self._relayout()

    def reorder(self, source_uid, target_uid):
        idx_s = next((i for i, c in enumerate(self.charts) if c.uid == source_uid), None)
        idx_t = next((i for i, c in enumerate(self.charts) if c.uid == target_uid), None)
        if idx_s is None or idx_t is None:
            return
        self.charts[idx_s], self.charts[idx_t] = self.charts[idx_t], self.charts[idx_s]
        self._relayout()

    def sample(self, t):
        for tile in self.charts:
            tile.append_sample(t)

    def clear_data(self):
        """Drop the recorded samples but keep the charts and their pens."""
        for tile in self.charts:
            tile.clear_data()

    def clear_all(self):
        for tile in list(self.charts):
            tile.deleteLater()
        self.charts.clear()
        self._relayout()
