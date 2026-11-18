from __future__ import annotations

import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QSplitter,
    QWidget,
    QHBoxLayout,
    QToolBar,
    QPushButton,
    QLabel,
    QDoubleSpinBox,
    QFileDialog,
    QMessageBox,
)

from core.controller import SimulationController
from .theme import Theme
from .canvas import CanvasScene, CanvasView
from .sidebar import Sidebar
from .trends import TrendsWidget
from .io_plc import IOPLCWidget
from .config_dialog import ConfigDialog
from .examples import EXAMPLES_DIR, list_examples, load_file, save_file, close_flowsheet


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CompSim — Dynamic Process Simulator")
        self.resize(1360, 860)

        self.controller = SimulationController(dt=1.0)
        self.running = False
        self._current_path = None

        self.scene = CanvasScene(self.controller)
        self.view = CanvasView(self.scene)
        self.sidebar = Sidebar()
        self.sidebar.add_block.connect(self.add_block_at_center)
        self.scene.node_config_requested.connect(self._edit_block)
        self._config_panels = {}   # instance_id -> open ConfigDialog
        self.scene.blocks_changed.connect(self._on_blocks_changed)

        process_tab = QWidget()
        process_layout = QHBoxLayout(process_tab)
        process_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(1, 1)
        process_layout.addWidget(splitter)

        self.trends = TrendsWidget(self.controller)
        self.ioplc = IOPLCWidget(self.controller)

        self.tabs = QTabWidget()
        self.tabs.addTab(process_tab, "Process")
        self.tabs.addTab(self.trends, "Trends")
        self.tabs.addTab(self.ioplc, "I/O OpenPLC")
        self.setCentralWidget(self.tabs)

        self._build_toolbar()
        self._build_file_menu()
        self._build_statusbar()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        delete_action = QAction(self)
        delete_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        delete_action.triggered.connect(self._delete_selection)
        self.addAction(delete_action)

    # -- toolbar & status ---------------------------------------------------
    def _build_toolbar(self):
        toolbar = QToolBar("Simulation")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.play_btn = QPushButton("Play")
        self.play_btn.setCheckable(True)
        self.play_btn.clicked.connect(self.toggle_play)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset)

        toolbar.addWidget(self.play_btn)
        toolbar.addWidget(self.stop_btn)
        toolbar.addWidget(self.reset_btn)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  dt (s): "))
        self.dt_spin = QDoubleSpinBox()
        self.dt_spin.setRange(0.01, 3600.0)
        self.dt_spin.setValue(self.controller.dt)
        self.dt_spin.setDecimals(3)
        self.dt_spin.valueChanged.connect(self._set_dt)
        toolbar.addWidget(self.dt_spin)
        toolbar.addSeparator()

        self.theme_btn = QPushButton("Light/Dark")
        self.theme_btn.clicked.connect(self._toggle_theme)
        toolbar.addWidget(self.theme_btn)

    def _build_statusbar(self):
        self.time_label = QLabel()
        self.statusBar().addWidget(self.time_label)
        # own label for notices: QStatusBar.showMessage draws over time_label
        self.msg_label = QLabel()
        self.statusBar().addWidget(self.msg_label, 1)
        self._msg_timer = QTimer(self)
        self._msg_timer.setSingleShot(True)
        self._msg_timer.timeout.connect(self.msg_label.clear)
        self.statusBar().addPermanentWidget(QLabel("CompSim core v0.1"))

    # -- simulation controls -------------------------------------------------
    def toggle_play(self):
        if self.running:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self._check_ready():
            self.play_btn.setChecked(False)
            return
        self.running = True
        self.play_btn.setChecked(True)
        self.play_btn.setText("Pause")
        self._apply_interval()

    def _check_ready(self):
        """Run the pre-run sanity check; report and return False on problems."""
        problems = self.controller.check_ready()
        if not problems:
            return True
        shown = problems[:15]
        if len(problems) > len(shown):
            shown.append(f"... and {len(problems) - len(shown)} more")
        QMessageBox.warning(
            self, "Cannot run simulation",
            "Fix these problems before running. Every material (stream) inlet "
            "and outlet must be connected; signal ports are optional.\n\n"
            + "\n".join(f"• {p}" for p in shown))
        self.notify(f"Not started: {len(problems)} problem(s) in the flowsheet", 15000)
        return False

    def pause(self):
        self.running = False
        self.play_btn.setChecked(False)
        self.play_btn.setText("Play")
        self.timer.stop()

    def stop(self):
        self.pause()
        self.reset()

    def reset(self):
        self.controller.reset()
        self.trends.clear_data()
        self.scene.refresh_values()
        self._update_status()

    def _tick(self):
        # An exception escaping a Qt slot aborts a PyQt6 application, so a
        # failing step pauses the simulation and reports instead.
        try:
            self.ioplc.refresh_from_sim()
            self.controller.step()
            t = self.controller.simulator.time
            self.ioplc.apply_to_sim()
            self.trends.sample(t)
            self.ioplc.update_live_values()
            self.scene.refresh_values()
            self._update_status()
        except Exception as e:
            self.pause()
            traceback.print_exc()
            self.notify(f"Simulation paused - error: {e}", 15000)

    def _apply_interval(self):
        ms = max(20, int(self.controller.dt * 1000))
        self.timer.start(ms)

    def _set_dt(self, value):
        self.controller.dt = value
        if self.running:
            self._apply_interval()

    def notify(self, text, timeout_ms=8000):
        self.msg_label.setText(f"   |   {text}")
        self._msg_timer.start(timeout_ms)

    def _update_status(self):
        sim = self.controller.simulator
        n_nodes = len(self.controller.graph.nodes)
        n_edges = len(self.controller.graph.edges)
        self.time_label.setText(
            f"  t = {sim.time:.2f} s   |   step = {sim.iteration}   |   blocks = {n_nodes}   |   streams = {n_edges}"
        )

    # -- canvas helpers ------------------------------------------------------
    def add_block_at_center(self, block_type):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.scene.create_block(block_type, center)

    def _on_blocks_changed(self):
        # close panels of blocks that no longer exist
        alive = {n.instance_id for n in self.controller.graph.nodes}
        for iid in [i for i in self._config_panels if i not in alive]:
            self._config_panels.pop(iid).close()
        self.trends.tree.refresh()
        self.ioplc.refresh_combos()
        self._update_status()

    def _delete_selection(self):
        # only act on the canvas: Delete on other tabs must not remove blocks
        if self.tabs.currentIndex() != 0:
            return
        self.scene.remove_selected()

    def _edit_block(self, block):
        """Open (or bring to front) the configuration panel of ``block``."""
        dlg = self._config_panels.get(block.instance_id)
        if dlg is None:
            dlg = ConfigDialog(block, self)
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dlg.applied.connect(self._on_config_applied)
            dlg.finished.connect(lambda _r, iid=block.instance_id: self._config_panels.pop(iid, None))
            self._config_panels[block.instance_id] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_config_applied(self, block):
        self.trends.tree.refresh()
        self.ioplc.refresh_combos()
        self.scene.refresh_values()
        self._update_status()

    # -- file menu ------------------------------------------------------------
    def _build_file_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.setToolTipsVisible(True)

        open_action = QAction("&Open…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_flowsheet)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_flowsheet)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as_flowsheet)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()
        close_action = QAction("&Close", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close_flowsheet)
        file_menu.addAction(close_action)

        delete_file_action = QAction("Delete file from folder…", self)
        delete_file_action.setToolTip(
            "Delete the current .sim file from disk and close the workspace"
        )
        delete_file_action.triggered.connect(self.delete_flowsheet_file)
        file_menu.addAction(delete_file_action)

        examples_menu = file_menu.addMenu("&Examples")
        for path in list_examples():
            action = examples_menu.addAction(path.stem.replace("_", " "))
            action.setToolTip(path.stem)
            action.triggered.connect(lambda _=False, p=path: self.open_example(p))

    def _confirm_discard(self, title):
        if not self.controller.graph.nodes:
            return True
        answer = QMessageBox.question(
            self, title, "Replace the current flowsheet?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def open_flowsheet(self):
        if not self._confirm_discard("Open flowsheet"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open flowsheet", str(EXAMPLES_DIR),
            "CompSim flowsheets (*.sim)",
        )
        if not path:
            return
        try:
            load_file(self, path)
            self._current_path = path
        except Exception as e:
            QMessageBox.warning(self, "Open flowsheet", f"Could not load:\n{e}")

    def open_example(self, path):
        if not self._confirm_discard("Load example"):
            return
        try:
            load_file(self, path)
            self._current_path = path
        except Exception as e:
            QMessageBox.warning(self, "Load example", f"Could not load:\n{e}")

    def save_flowsheet(self):
        if self._current_path is None:
            self.save_as_flowsheet()
            return
        try:
            save_file(self, self._current_path)
        except Exception as e:
            QMessageBox.warning(self, "Save flowsheet", f"Could not save:\n{e}")

    def save_as_flowsheet(self):
        start_dir = str(self._current_path or EXAMPLES_DIR)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save flowsheet as", start_dir,
            "CompSim flowsheets (*.sim)",
        )
        if not path:
            return
        if not path.endswith(".sim"):
            path += ".sim"
        try:
            save_file(self, path)
            self._current_path = path
        except Exception as e:
            QMessageBox.warning(self, "Save flowsheet", f"Could not save:\n{e}")

    def close_flowsheet(self):
        # closing is never destructive to saved work: just wipe the workspace
        close_flowsheet(self)
        self._current_path = None

    def delete_flowsheet_file(self):
        if self._current_path is None:
            QMessageBox.information(
                self, "Delete file", "No file is open (save the flowsheet first)."
            )
            return
        path = Path(self._current_path)
        answer = QMessageBox.question(
            self, "Delete file",
            f"Delete \"{path.name}\" from the folder?\n\n"
            f"{path}\n\nThis cannot be undone.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            QMessageBox.warning(self, "Delete file", f"Could not delete:\n{e}")
            return
        close_flowsheet(self)
        self._current_path = None
        self.notify(f"File deleted: {path.name}")

    # -- theme ---------------------------------------------------------------
    def _toggle_theme(self):
        Theme.toggle(QApplication.instance())
        self.scene.restyle()
        self.view.viewport().update()

    def closeEvent(self, event):
        for dlg in list(self._config_panels.values()):
            dlg.close()
        self.pause()
        self.ioplc.shutdown()
        event.accept()
