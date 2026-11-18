from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QLabel,
    QPlainTextEdit,
)

from core.variables import block_variables, writable_variables, resolve, apply, is_scalar
from plcio import (
    IOManager,
    IOTag,
    DataType,
    Direction,
    SignalType,
    BACKEND_TYPES,
    create_backend,
    openplc_location,
)


class IOPLCWidget(QWidget):
    """I/O configuration panel for OpenPLC / OPC UA / Modbus.

    Tags are classified by PLC signal type (AI / AO / DI / DO); the signal type
    drives the direction, data type and default Modbus register table. The I/O
    manager runs on a background thread; live values refresh every solver step.
    """

    log_signal = pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.manager = IOManager(scan_interval=0.5)
        self.manager.on_log = self.log_signal.emit
        self.log_signal.connect(self._append_log)

        root = QVBoxLayout(self)

        # ---- Backends ------------------------------------------------------
        backend_box = QGroupBox("Connections / Backends")
        bv = QVBoxLayout(backend_box)
        form = QGridLayout()
        self.btype_combo = QComboBox()
        self.btype_combo.addItems(list(BACKEND_TYPES))
        self.btype_combo.currentTextChanged.connect(self._backend_type_changed)
        self.bname_edit = QLineEdit()
        self.bname_edit.setPlaceholderText("name")
        self.endpoint_edit = QLineEdit("127.0.0.1")
        self.endpoint_edit.setPlaceholderText("host / serial port / url")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        self.endpoint_label = QLabel("Host:")
        add_backend_btn = QPushButton("+ Add Backend")
        add_backend_btn.clicked.connect(self.add_backend)

        form.addWidget(QLabel("Type:"), 0, 0)
        form.addWidget(self.btype_combo, 0, 1)
        form.addWidget(QLabel("Name:"), 0, 2)
        form.addWidget(self.bname_edit, 0, 3)
        form.addWidget(self.endpoint_label, 0, 4)
        form.addWidget(self.endpoint_edit, 0, 5)
        form.addWidget(QLabel("Port/Baud:"), 0, 6)
        form.addWidget(self.port_spin, 0, 7)
        form.addWidget(add_backend_btn, 0, 8)
        bv.addLayout(form)

        self.backend_table = QTableWidget(0, 4)
        self.backend_table.setHorizontalHeaderLabels(["Name", "Type", "Endpoint", "Status"])
        self.backend_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.backend_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        bv.addWidget(self.backend_table)

        bb = QHBoxLayout()
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_backend)
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.clicked.connect(self.disconnect_backend)
        remove_backend_btn = QPushButton("Remove")
        remove_backend_btn.clicked.connect(self.remove_backend)
        bb.addWidget(connect_btn)
        bb.addWidget(disconnect_btn)
        bb.addWidget(remove_backend_btn)
        bb.addStretch(1)
        bv.addLayout(bb)
        root.addWidget(backend_box)

        # ---- Tag map -------------------------------------------------------
        tag_box = QGroupBox("Tag Map")
        tv = QVBoxLayout(tag_box)
        tform = QGridLayout()
        self.sig_combo = QComboBox()
        for s in (SignalType.AI, SignalType.AO, SignalType.DI, SignalType.DO):
            self.sig_combo.addItem(s.label, s)
        self.sig_combo.currentIndexChanged.connect(self._on_sig_changed)
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("TAG")
        self.backend_combo = QComboBox()
        self.backend_combo.currentTextChanged.connect(self._suggest_address)
        self.addr_edit = QLineEdit()
        self.addr_edit.setPlaceholderText("0 / %IW0 / ns=2;i=5")
        self.var_combo = QComboBox()
        self.var_combo.setMinimumWidth(220)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(-1e12, 1e12)
        self.scale_spin.setValue(1.0)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e12, 1e12)
        self.offset_spin.setValue(0.0)
        add_tag_btn = QPushButton("+ Add Tag")
        add_tag_btn.clicked.connect(self.add_tag)

        tform.addWidget(QLabel("Signal:"), 0, 0)
        tform.addWidget(self.sig_combo, 0, 1)
        tform.addWidget(QLabel("Tag:"), 0, 2)
        tform.addWidget(self.tag_edit, 0, 3)
        tform.addWidget(QLabel("Backend:"), 0, 4)
        tform.addWidget(self.backend_combo, 0, 5)
        tform.addWidget(QLabel("Address:"), 1, 0)
        tform.addWidget(self.addr_edit, 1, 1)
        tform.addWidget(QLabel("Scale:"), 1, 2)
        tform.addWidget(self.scale_spin, 1, 3)
        tform.addWidget(QLabel("Offset:"), 1, 4)
        tform.addWidget(self.offset_spin, 1, 5)
        tform.addWidget(QLabel("Variable:"), 2, 0)
        tform.addWidget(self.var_combo, 2, 1, 1, 5)
        tform.addWidget(add_tag_btn, 2, 6)
        tv.addLayout(tform)

        self.tag_table = QTableWidget(0, 7)
        self.tag_table.setHorizontalHeaderLabels(["Tag", "Signal", "Backend", "Address", "Type", "Variable", "Live"])
        self.tag_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tag_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tv.addWidget(self.tag_table)

        tb = QHBoxLayout()
        remove_tag_btn = QPushButton("Remove Tag")
        remove_tag_btn.clicked.connect(self.remove_tag)
        tb.addWidget(remove_tag_btn)
        tb.addStretch(1)
        tv.addLayout(tb)
        root.addWidget(tag_box)

        # ---- scan controls + log ------------------------------------------
        ctrl = QHBoxLayout()
        self.scan_btn = QPushButton("Start Scan")
        self.scan_btn.setCheckable(True)
        self.scan_btn.clicked.connect(self.toggle_scan)
        ctrl.addWidget(self.scan_btn)
        ctrl.addWidget(QLabel("Scan interval (s):"))
        self.scan_spin = QDoubleSpinBox()
        self.scan_spin.setRange(0.05, 60.0)
        self.scan_spin.setValue(0.5)
        self.scan_spin.valueChanged.connect(self._set_scan)
        ctrl.addWidget(self.scan_spin)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        root.addWidget(self.log, 1)

        self._refresh_backends()
        self._refresh_vars()

    # -- log ----------------------------------------------------------------
    def _append_log(self, msg):
        self.log.appendPlainText(msg)

    # -- backends -----------------------------------------------------------
    def _backend_type_changed(self, key):
        if key == "Modbus RTU":
            self.endpoint_label.setText("Serial:")
            self.port_spin.setValue(19200)
        elif key == "OPC UA":
            self.endpoint_label.setText("URL:")
            self.endpoint_edit.setText("opc.tcp://127.0.0.1:4840")
        else:
            self.endpoint_label.setText("Host:")

    def _endpoint_config(self):
        key = self.btype_combo.currentText()
        kind = BACKEND_TYPES[key][0]
        name = self.bname_edit.text().strip() or f"{kind}-{len(self.manager.backends) + 1}"
        cfg = {"name": name}
        if key == "Modbus RTU":
            cfg.update(serial_port=self.endpoint_edit.text().strip(), baudrate=self.port_spin.value())
        elif key == "OPC UA":
            cfg.update(url=self.endpoint_edit.text().strip())
        elif key == "OpenPLC":
            cfg.update(host=self.endpoint_edit.text().strip(), port=self.port_spin.value(), http_port=8080)
        else:
            cfg.update(host=self.endpoint_edit.text().strip(), port=self.port_spin.value())
        return cfg

    def add_backend(self):
        cfg = self._endpoint_config()
        if cfg["name"] in self.manager.backends:
            self._append_log(f"a backend named '{cfg['name']}' already exists")
            return
        backend = create_backend(self.btype_combo.currentText(), cfg)
        self.manager.add_backend(backend)
        self._refresh_backends()
        self._append_log(f"added backend {backend.name} ({backend.type})")

    def _refresh_backends(self):
        selected = self.backend_combo.currentText()
        self.backend_combo.blockSignals(True)
        self.backend_table.setRowCount(0)
        self.backend_combo.clear()
        for b in self.manager.backends.values():
            row = self.backend_table.rowCount()
            self.backend_table.insertRow(row)
            self.backend_table.setItem(row, 0, QTableWidgetItem(b.name))
            self.backend_table.setItem(row, 1, QTableWidgetItem(b.type))
            self.backend_table.setItem(row, 2, QTableWidgetItem(self._endpoint_text(b)))
            self.backend_table.setItem(row, 3, QTableWidgetItem(b.status))
            self.backend_combo.addItem(b.name)
        if selected:
            self.backend_combo.setCurrentText(selected)
        self.backend_combo.blockSignals(False)

    @staticmethod
    def _endpoint_text(b):
        c = b.config
        if b.type == "modbus" and c.get("protocol") == "rtu":
            return f"{c.get('serial_port', '?')}@{c.get('baudrate', '?')}"
        if b.type == "opcua":
            return c.get("url", "?")
        if b.type == "openplc":
            return f"{c.get('host', '?')}:{c.get('port', 502)} (http {c.get('http_port', 8080)})"
        if b.type == "virtual":
            return "in-memory"
        return f"{c.get('host', '?')}:{c.get('port', '?')}"

    def _selected_backend(self):
        row = self.backend_table.currentRow()
        if row < 0 or row >= len(self.manager.backends):
            return None
        return list(self.manager.backends.values())[row]

    def _scanning(self):
        return self.manager._thread is not None and self.manager._thread.is_alive()

    def connect_backend(self):
        b = self._selected_backend()
        if b is not None:
            b.enabled = True
            if self._scanning():
                # the scan thread owns the transport; it connects on its next pass
                self._append_log(f"{b.name}: connecting on next scan")
            else:
                with b.lock:
                    try:
                        if not b.is_connected:
                            b.connect()
                        self._append_log(f"{b.name}: connected")
                    except Exception as e:
                        self._append_log(f"{b.name}: {e}")
        self._refresh_backends()

    def disconnect_backend(self):
        b = self._selected_backend()
        if b is not None:
            b.enabled = False   # keep the scan thread from reconnecting it
            with b.lock:
                b.disconnect()
            self._append_log(f"{b.name}: disconnected")
        self._refresh_backends()

    def remove_backend(self):
        b = self._selected_backend()
        if b is not None:
            self.manager.remove_backend(b.name)
            self._refresh_backends()

    # -- tags ---------------------------------------------------------------
    def _on_sig_changed(self):
        self._refresh_vars()
        self._suggest_address()

    def _suggest_address(self):
        backend = self.backend_combo.currentText()
        b = self.manager.get_backend(backend)
        if b is not None and b.type == "openplc":
            sig = self.sig_combo.currentData()
            used = {t.address for t in self.manager.tags if t.backend == backend}
            index = 0
            while openplc_location(sig, index) in used:
                index += 1
            self.addr_edit.setText(openplc_location(sig, index))
        elif self.addr_edit.text().strip() == "" or self.addr_edit.text().strip().startswith("%"):
            self.addr_edit.clear()

    def _refresh_vars(self):
        self.var_combo.clear()
        direction = self.sig_combo.currentData().direction
        for block in self.controller.graph.nodes:
            vars_ = writable_variables(block) if direction is Direction.IN else block_variables(block)
            for display, path in vars_:
                self.var_combo.addItem(display, (block.instance_id, path))

    def add_tag(self):
        sig = self.sig_combo.currentData()
        data = self.var_combo.currentData()
        if data is None:
            self._append_log("no variable selected")
            return
        block_id, path = data
        b = self.manager.get_backend(self.backend_combo.currentText())
        # OpenPLC %IW/%QW are single 16-bit registers
        dtype = DataType.UINT16 if (b is not None and b.type == "openplc" and sig.is_analog) else None
        tag = IOTag(
            name=self.tag_edit.text().strip() or "TAG",
            signal_type=sig,
            backend=self.backend_combo.currentText(),
            address=self.addr_edit.text().strip(),
            scale=self.scale_spin.value(),
            offset=self.offset_spin.value(),
            block_id=block_id,
            path=path,
            dtype=dtype,
        )
        self.manager.add_tag(tag)
        self._refresh_tags()
        self._append_log(f"added tag {tag.name} ({sig.short})")
        if not self.manager._thread or not self.manager._thread.is_alive():
            self.manager.start()
            self.scan_btn.setChecked(True)
            self.scan_btn.setText("Stop Scan")

    def remove_tag(self):
        row = self.tag_table.currentRow()
        if 0 <= row < len(self.manager.tags):
            tag = self.manager.tags[row]
            self.manager.remove_tag(tag.name)
            self._refresh_tags()

    def clear_workspace(self):
        """Drop every tag mapping; the backends themselves are kept."""
        for tag in list(self.manager.tags):
            self.manager.remove_tag(tag.name)
        self._refresh_tags()

    def _refresh_tags(self):
        self.tag_table.setRowCount(0)
        for tag in self.manager.tags:
            row = self.tag_table.rowCount()
            self.tag_table.insertRow(row)
            self.tag_table.setItem(row, 0, QTableWidgetItem(tag.name))
            self.tag_table.setItem(row, 1, QTableWidgetItem(tag.signal_type.short))
            self.tag_table.setItem(row, 2, QTableWidgetItem(tag.backend))
            self.tag_table.setItem(row, 3, QTableWidgetItem(tag.address))
            self.tag_table.setItem(row, 4, QTableWidgetItem(tag.data_type.value))
            self.tag_table.setItem(row, 5, QTableWidgetItem(self._var_label(tag)))
            self.tag_table.setItem(row, 6, QTableWidgetItem(""))

    def _var_label(self, tag):
        block = self.controller.graph.get_node(tag.block_id)
        if block is None:
            return "?"
        return ".".join([block.name, *tag.path])

    # -- scan ---------------------------------------------------------------
    def toggle_scan(self):
        if self.scan_btn.isChecked():
            self.manager.start()
            self.scan_btn.setText("Stop Scan")
            self._append_log("scan started")
        else:
            self.manager.stop()
            self.scan_btn.setText("Start Scan")
            self._append_log("scan stopped")

    def _set_scan(self, value):
        self.manager.scan_interval = value

    # -- per-step data exchange (GUI thread) --------------------------------
    def refresh_from_sim(self):
        for tag in self.manager.tags:
            if tag.direction is Direction.OUT:
                block = self.controller.graph.get_node(tag.block_id)
                if block is not None:
                    v = self._resolve(block, tag.path)
                    if is_scalar(v):
                        self.manager.set_output(tag.name, v)

    def apply_to_sim(self):
        for tag in self.manager.tags:
            if tag.direction is Direction.IN:
                block = self.controller.graph.get_node(tag.block_id)
                if block is not None:
                    v = self.manager.get_input(tag.name)
                    if v is not None:
                        apply(block, tag.path, v)

    def update_live_values(self):
        for row, tag in enumerate(self.manager.tags):
            item = self.tag_table.item(row, 6)
            if item is None:
                continue
            if tag.direction is Direction.OUT:
                block = self.controller.graph.get_node(tag.block_id)
                v = self._resolve(block, tag.path) if block is not None else None
            else:
                v = self.manager.get_input(tag.name)
            item.setText(f"{v:.6g}" if is_scalar(v) else ("" if v is None else str(v)))
        self._refresh_backend_status()

    @staticmethod
    def _resolve(block, path):
        try:
            return resolve(block, path)
        except (KeyError, IndexError):
            return None

    def _refresh_backend_status(self):
        for row, b in enumerate(self.manager.backends.values()):
            item = self.backend_table.item(row, 3)
            if item is not None:
                item.setText(b.status)

    def refresh_combos(self):
        self._refresh_vars()
        self._refresh_backends()

    def shutdown(self):
        self.manager.stop()
