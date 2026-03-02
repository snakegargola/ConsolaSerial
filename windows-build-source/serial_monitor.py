"""
serial_monitor.py — Main application window (PyQt6).
"""

import threading
from datetime import datetime
import json
import random
import re
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QCheckBox, QTextEdit, QLineEdit,
    QStatusBar, QFileDialog, QMessageBox, QFrame, QSplitter,
    QColorDialog, QGroupBox, QSpinBox, QDoubleSpinBox, QToolBar,
    QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QProgressBar,
)
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QPalette, QShortcut, QKeySequence, QAction
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from .config_manager import ConfigManager
from .serial_worker import SerialWorker, list_ports
from .log_manager import LogManager

# ──────────────────────────────────────────────────────────────────────────────
BAUD_RATES = ["300","1200","2400","4800","9600","19200","38400","57600",
              "115200","230400","460800","921600"]
DATA_BITS  = ["5","6","7","8"]
PARITIES   = ["None","Even","Odd","Mark","Space"]
STOP_BITS  = ["1","1.5","2"]
FLOW_CTRL  = ["None","RTS/CTS","XON/XOFF"]
EOL_OPT    = ["None","LF","CR","CR+LF"]
EOL_TX_MAP = {"None": b"", "LF": b"\n", "CR": b"\r", "CR+LF": b"\r\n"}
SEND_FMTS  = ["ASCII","HEX"]


# Worker signals bridge (PyQt signals must live in QObject)
class _Signals(QObject):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)


class SerialMonitorApp(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.worker: SerialWorker | None = None
        self.log = LogManager()
        self._signals = _Signals()
        self._signals.data_received.connect(self._display_rx)
        self._signals.error_occurred.connect(self._handle_error)
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._send_data)
        
        # Sequence timer
        self._sequence_timer = QTimer(self)
        self._sequence_timer.timeout.connect(self._send_next_sequence_cmd)
        self._sequence_index = 0
        self._sequence_running = False
        self._sequence_cmd_counter = 0
        
        # Statistics
        self._stats_rx_bytes = 0
        self._stats_tx_bytes = 0
        self._stats_start_time = time.time()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_statistics)
        self._stats_timer.start(1000)  # Update every second
        
        # Search and filters
        self._search_text = ""
        self._filter_text = ""
        self._filter_regex = False
        self._full_log_buffer = []  # Full unfiltered log
        
        # Alerts
        self._alerts = []  # List of {"pattern": str, "regex": bool, "sound": bool}

        # Colors
        self._color_rx = self.config.get("color_rx", "#00FF7F")
        self._color_tx = self.config.get("color_tx", "#00BFFF")
        self._color_bg = self.config.get("color_bg", "#1C1C1C")

        self.setWindowTitle("Serial Monitor — Embedded Systems")
        self.resize(1150, 800)
        self._build_ui()
        self._load_config_into_ui()
        self._setup_shortcuts()

    # ──────────────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 4)

        root.addWidget(self._build_config_panel())
        
        # Create horizontal splitter for sequence panel and main content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sequence_panel())
        
        # Right side: monitor and send panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(4)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._build_monitor(), stretch=1)
        right_layout.addWidget(self._build_send_panel())
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)  # Sequence panel fixed width
        splitter.setStretchFactor(1, 1)  # Monitor expands
        splitter.setSizes([350, 800])    # Initial sizes
        
        root.addWidget(splitter, stretch=1)

        self._build_status_bar()

    # ── Config panel ──────────────────────────────────────────────────────────
    def _build_config_panel(self):
        box = QGroupBox("Serial Configuration")
        grid = QGridLayout(box)
        grid.setSpacing(4)

        def lbl(text): return QLabel(text)
        def combo(vals, width=90):
            c = QComboBox(); c.addItems(vals); c.setFixedWidth(width); return c

        # Tooltips descriptions
        tooltips = {
            "port": "Serial port to connect to (e.g., COM3, /dev/ttyUSB0)",
            "baud": "Transmission speed in bits per second (higher = faster)",
            "data": "Number of data bits per character (usually 8)",
            "parity": "Error checking method: None, Even, Odd, Mark, or Space",
            "stop": "Number of stop bits (1, 1.5, or 2)",
            "flow": "Flow control method for handshaking (None, RTS/CTS, XON/XOFF)",
            "eol_tx": "Line ending to append when transmitting (None, LF, CR, CR+LF)",
            "eol_rx": "Line ending format expected from received data",
            "ascii": "Display received data as text characters",
            "hex": "Display received data in hexadecimal format",
            "timestamp": "Show timestamp for each message",
            "colors": "Customize colors for RX (received), TX (transmitted), and background"
        }

        # Row 0 - Port and communication settings
        r = 0
        port_label = lbl("Port: 🔹")
        port_label.setToolTip(tooltips["port"])
        grid.addWidget(port_label, r, 0)
        self.port_combo = combo([], 110)
        self.port_combo.setToolTip(tooltips["port"])
        grid.addWidget(self.port_combo, r, 1)
        btn_refresh = QPushButton("⟳"); btn_refresh.setFixedWidth(28)
        btn_refresh.setToolTip("Refresh available ports")
        btn_refresh.clicked.connect(self._refresh_ports)
        grid.addWidget(btn_refresh, r, 2)

        baud_label = lbl("Baud: 🔹")
        baud_label.setToolTip(tooltips["baud"])
        grid.addWidget(baud_label, r, 3)
        self.baud_combo = combo(BAUD_RATES, 100)
        self.baud_combo.setToolTip(tooltips["baud"])
        grid.addWidget(self.baud_combo, r, 4)

        data_label = lbl("Data: 🔹")
        data_label.setToolTip(tooltips["data"])
        grid.addWidget(data_label, r, 5)
        self.databits_combo = combo(DATA_BITS, 55)
        self.databits_combo.setToolTip(tooltips["data"])
        grid.addWidget(self.databits_combo, r, 6)

        parity_label = lbl("Parity: 🔹")
        parity_label.setToolTip(tooltips["parity"])
        grid.addWidget(parity_label, r, 7)
        self.parity_combo = combo(PARITIES, 80)
        self.parity_combo.setToolTip(tooltips["parity"])
        grid.addWidget(self.parity_combo, r, 8)

        stop_label = lbl("Stop: 🔹")
        stop_label.setToolTip(tooltips["stop"])
        grid.addWidget(stop_label, r, 9)
        self.stopbits_combo = combo(STOP_BITS, 55)
        self.stopbits_combo.setToolTip(tooltips["stop"])
        grid.addWidget(self.stopbits_combo, r, 10)

        flow_label = lbl("Flow: 🔹")
        flow_label.setToolTip(tooltips["flow"])
        grid.addWidget(flow_label, r, 11)
        self.flow_combo = combo(FLOW_CTRL, 90)
        self.flow_combo.setToolTip(tooltips["flow"])
        grid.addWidget(self.flow_combo, r, 12)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(100)
        self.connect_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self.connect_btn.setToolTip("Establish or close serial connection")
        self.connect_btn.clicked.connect(self._toggle_connection)
        grid.addWidget(self.connect_btn, r, 13, 1, 2)

        # Row 1 - EOL, Display options, and Colors
        r = 1
        eol_tx_label = lbl("EOL TX: 🔹")
        eol_tx_label.setToolTip(tooltips["eol_tx"])
        grid.addWidget(eol_tx_label, r, 0)
        self.eol_tx_combo = combo(EOL_OPT, 80)
        self.eol_tx_combo.setToolTip(tooltips["eol_tx"])
        grid.addWidget(self.eol_tx_combo, r, 1)

        eol_rx_label = lbl("EOL RX: 🔹")
        eol_rx_label.setToolTip(tooltips["eol_rx"])
        grid.addWidget(eol_rx_label, r, 3)
        self.eol_rx_combo = combo(EOL_OPT, 80)
        self.eol_rx_combo.setToolTip(tooltips["eol_rx"])
        grid.addWidget(self.eol_rx_combo, r, 4)

        show_label = lbl("Show: 🔹")
        show_label.setToolTip("Select display formats for received data")
        grid.addWidget(show_label, r, 5)
        self.chk_ascii = QCheckBox("ASCII"); self.chk_ascii.setChecked(True)
        self.chk_ascii.setToolTip(tooltips["ascii"])
        self.chk_hex   = QCheckBox("HEX")
        self.chk_hex.setToolTip(tooltips["hex"])
        self.chk_ts    = QCheckBox("Timestamp"); self.chk_ts.setChecked(True)
        self.chk_ts.setToolTip(tooltips["timestamp"])
        grid.addWidget(self.chk_ascii, r, 6)
        grid.addWidget(self.chk_hex,   r, 7)
        grid.addWidget(self.chk_ts,    r, 8)

        colors_label = lbl("Colors: 🔹")
        colors_label.setToolTip("Click buttons to customize display colors")
        grid.addWidget(colors_label, r, 9)
        self.btn_crx = QPushButton("RX"); self.btn_crx.setFixedWidth(44)
        self.btn_crx.setToolTip("Color for received data (RX)")
        self.btn_ctx = QPushButton("TX"); self.btn_ctx.setFixedWidth(44)
        self.btn_ctx.setToolTip("Color for transmitted data (TX)")
        self.btn_cbg = QPushButton("BG"); self.btn_cbg.setFixedWidth(44)
        self.btn_cbg.setToolTip("Color for console background")
        self._apply_color_btn(self.btn_crx, self._color_rx)
        self._apply_color_btn(self.btn_ctx, self._color_tx)
        self._apply_color_btn(self.btn_cbg, self._color_bg)
        self.btn_crx.clicked.connect(lambda: self._pick_color("rx"))
        self.btn_ctx.clicked.connect(lambda: self._pick_color("tx"))
        self.btn_cbg.clicked.connect(lambda: self._pick_color("bg"))
        grid.addWidget(self.btn_crx, r, 10)
        grid.addWidget(self.btn_ctx, r, 11)
        grid.addWidget(self.btn_cbg, r, 12)

        # Theme toggle
        self.theme_btn = QPushButton("☀ Light")
        self.theme_btn.setFixedWidth(80)
        self.theme_btn.setToolTip("Toggle between light and dark theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        grid.addWidget(self.theme_btn, r, 13)

        return box

    # ── Sequence panel ────────────────────────────────────────────────────────
    def _build_sequence_panel(self):
        box = QGroupBox("Command Sequence")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(4)
        
        # Command list table
        self.seq_table = QTableWidget()
        self.seq_table.setColumnCount(5)
        self.seq_table.setHorizontalHeaderLabels(["", "Command", "▶", "↑↓", "✕"])
        self.seq_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.seq_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.seq_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.seq_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.seq_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.seq_table.setColumnWidth(0, 30)
        self.seq_table.setColumnWidth(2, 32)
        self.seq_table.setColumnWidth(3, 60)
        self.seq_table.setColumnWidth(4, 35)
        self.seq_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.seq_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.seq_table.verticalHeader().setVisible(False)
        vbox.addWidget(self.seq_table)
        
        # Add command button
        btn_add = QPushButton("+ Add Command")
        btn_add.clicked.connect(self._add_sequence_command)
        vbox.addWidget(btn_add)
        
        # Interval and mode configuration
        config_layout = QGridLayout()
        config_layout.addWidget(QLabel("Interval (s):"), 0, 0)
        self.seq_interval_spin = QDoubleSpinBox()
        self.seq_interval_spin.setRange(0.1, 3600)
        self.seq_interval_spin.setSingleStep(0.5)
        self.seq_interval_spin.setValue(1.0)
        config_layout.addWidget(self.seq_interval_spin, 0, 1)
        
        config_layout.addWidget(QLabel("On finish:"), 1, 0)
        self.seq_mode_combo = QComboBox()
        self.seq_mode_combo.addItems(["Stop", "Restart"])
        config_layout.addWidget(self.seq_mode_combo, 1, 1)
        vbox.addLayout(config_layout)
        
        # Variables info
        var_info = QLabel("💡 Variables: {timestamp}, {counter}, {random}")
        var_info.setWordWrap(True)
        var_info.setStyleSheet("color: #888; font-size: 9px;")
        vbox.addWidget(var_info)
        
        # Export/Import buttons
        export_layout = QHBoxLayout()
        btn_export = QPushButton("📤 Export")
        btn_export.clicked.connect(self._export_sequence)
        btn_import = QPushButton("📥 Import")
        btn_import.clicked.connect(self._import_sequence)
        export_layout.addWidget(btn_export)
        export_layout.addWidget(btn_import)
        vbox.addLayout(export_layout)
        
        # Start/Stop button
        self.seq_start_btn = QPushButton("Start Sequence")
        self.seq_start_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self.seq_start_btn.clicked.connect(self._toggle_sequence)
        vbox.addWidget(self.seq_start_btn)
        
        box.setFixedWidth(340)
        return box

    # ── Monitor ───────────────────────────────────────────────────────────────
    def _build_monitor(self):
        frame = QGroupBox("Monitor")
        vbox = QVBoxLayout(frame)
        vbox.setSpacing(2)

        # Toolbar row
        toolbar = QHBoxLayout()
        btn_clear = QPushButton("Clear"); btn_clear.clicked.connect(self._clear_monitor)
        btn_log   = QPushButton("Save Log"); btn_log.clicked.connect(self._save_log)
        btn_cfg   = QPushButton("Save Config"); btn_cfg.clicked.connect(self._save_config)
        toolbar.addWidget(btn_clear)
        toolbar.addWidget(btn_log)
        toolbar.addWidget(btn_cfg)
        toolbar.addStretch()
        
        # Statistics labels
        self.speed_lbl = QLabel("Speed: 0 B/s")
        self.rx_lbl = QLabel("RX: 0 B")
        self.tx_lbl = QLabel("TX: 0 B")
        toolbar.addWidget(self.speed_lbl)
        toolbar.addWidget(self.tx_lbl)
        toolbar.addWidget(self.rx_lbl)
        vbox.addLayout(toolbar)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search in log...")
        self.search_edit.textChanged.connect(self._search_in_monitor)
        search_layout.addWidget(self.search_edit)
        
        self.btn_search_prev = QPushButton("◀")
        self.btn_search_prev.setFixedWidth(30)
        self.btn_search_prev.clicked.connect(self._search_previous)
        self.btn_search_next = QPushButton("▶")
        self.btn_search_next.setFixedWidth(30)
        self.btn_search_next.clicked.connect(self._search_next)
        search_layout.addWidget(self.btn_search_prev)
        search_layout.addWidget(self.btn_search_next)
        
        self.search_result_lbl = QLabel("")
        search_layout.addWidget(self.search_result_lbl)
        vbox.addLayout(search_layout)
        
        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("📌 Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter messages (leave empty to show all)...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_edit)
        
        self.filter_regex_chk = QCheckBox("Regex")
        self.filter_regex_chk.toggled.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_regex_chk)
        
        btn_filter_clear = QPushButton("Clear")
        btn_filter_clear.setFixedWidth(60)
        btn_filter_clear.clicked.connect(lambda: self.filter_edit.setText(""))
        filter_layout.addWidget(btn_filter_clear)
        vbox.addLayout(filter_layout)
        
        # Alert management
        alert_layout = QHBoxLayout()
        alert_layout.addWidget(QLabel("🔔 Alerts:"))
        btn_manage_alerts = QPushButton("Manage Alerts")
        btn_manage_alerts.clicked.connect(self._manage_alerts)
        alert_layout.addWidget(btn_manage_alerts)
        alert_layout.addStretch()
        vbox.addLayout(alert_layout)

        self.monitor = QTextEdit()
        self.monitor.setReadOnly(True)
        self.monitor.setFont(QFont("Courier New", 10))
        self.monitor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._apply_monitor_bg(self._color_bg)
        vbox.addWidget(self.monitor)
        return frame

    # ── Send panel ────────────────────────────────────────────────────────────
    def _build_send_panel(self):
        box = QGroupBox("Send")
        grid = QGridLayout(box)
        grid.setSpacing(4)

        grid.addWidget(QLabel("Data:"), 0, 0)
        self.send_edit = QLineEdit()
        self.send_edit.returnPressed.connect(self._send_data)
        grid.addWidget(self.send_edit, 0, 1, 1, 3)

        grid.addWidget(QLabel("Format:"), 0, 4)
        self.send_fmt = QComboBox(); self.send_fmt.addItems(SEND_FMTS); self.send_fmt.setFixedWidth(80)
        grid.addWidget(self.send_fmt, 0, 5)

        btn_send = QPushButton("Send"); btn_send.setFixedWidth(70)
        btn_send.clicked.connect(self._send_data)
        grid.addWidget(btn_send, 0, 6)

        grid.addWidget(QLabel("History:"), 0, 7)
        self.history_combo = QComboBox(); self.history_combo.setFixedWidth(200)
        self.history_combo.currentTextChanged.connect(self.send_edit.setText)
        grid.addWidget(self.history_combo, 0, 8)

        grid.setColumnStretch(1, 1)

        # Row 1 — auto send
        grid.addWidget(QLabel("Auto-send interval (s):"), 1, 0, 1, 2)
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 3600); self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(1.0); self.interval_spin.setFixedWidth(80)
        grid.addWidget(self.interval_spin, 1, 2)

        self.auto_btn = QPushButton("Start Auto"); self.auto_btn.setFixedWidth(100)
        self.auto_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self.auto_btn.clicked.connect(self._toggle_auto_send)
        grid.addWidget(self.auto_btn, 1, 3)

        return box

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.led_lbl = QLabel("●")
        self.led_lbl.setStyleSheet("color:#555555; font-size:18px;")
        self.conn_lbl = QLabel("Disconnected")
        sb.addWidget(self.led_lbl)
        sb.addWidget(self.conn_lbl)

    # ──────────────────────────────────────────────────────────────────────────
    # Config ↔ UI
    # ──────────────────────────────────────────────────────────────────────────

    def _load_config_into_ui(self):
        self._refresh_ports()
        self._set_combo(self.port_combo, self.config.get("port", ""))
        self._set_combo(self.baud_combo, str(self.config.get("baud", 115200)))
        self._set_combo(self.databits_combo, str(self.config.get("databits", 8)))
        self._set_combo(self.parity_combo, self.config.get("parity", "None"))
        self._set_combo(self.stopbits_combo, str(self.config.get("stopbits", "1")))
        self._set_combo(self.flow_combo, self.config.get("flowcontrol", "None"))
        self._set_combo(self.eol_tx_combo, self.config.get("eol_tx", "LF"))
        self._set_combo(self.eol_rx_combo, self.config.get("eol_rx", "LF"))
        self.chk_ascii.setChecked(self.config.get("show_ascii", True))
        self.chk_hex.setChecked(self.config.get("show_hex", False))
        self.chk_ts.setChecked(self.config.get("show_timestamp", True))
        self._set_combo(self.send_fmt, self.config.get("send_format", "ASCII"))
        self.interval_spin.setValue(float(self.config.get("auto_send_interval", 1.0)))
        self._update_history_combo()
        
        # Load sequence configuration
        self.seq_interval_spin.setValue(float(self.config.get("sequence_interval", 1.0)))
        self._set_combo(self.seq_mode_combo, self.config.get("sequence_mode", "Stop"))
        self._load_sequence_commands()
        
        # Load alerts
        self._alerts = self.config.get("alerts", [])
        
        if self.config.get("theme", "dark") == "light":
            self._apply_light_theme()

    def _collect_config(self):
        self.config.set("port", self.port_combo.currentText())
        self.config.set("baud", int(self.baud_combo.currentText()))
        self.config.set("databits", int(self.databits_combo.currentText()))
        self.config.set("parity", self.parity_combo.currentText())
        self.config.set("stopbits", self.stopbits_combo.currentText())
        self.config.set("flowcontrol", self.flow_combo.currentText())
        self.config.set("eol_tx", self.eol_tx_combo.currentText())
        self.config.set("eol_rx", self.eol_rx_combo.currentText())
        self.config.set("show_ascii", self.chk_ascii.isChecked())
        self.config.set("show_hex", self.chk_hex.isChecked())
        self.config.set("show_timestamp", self.chk_ts.isChecked())
        self.config.set("send_format", self.send_fmt.currentText())
        self.config.set("color_rx", self._color_rx)
        self.config.set("color_tx", self._color_tx)
        self.config.set("color_bg", self._color_bg)
        self.config.set("auto_send_interval", self.interval_spin.value())
        
        # Save sequence configuration
        self.config.set("sequence_interval", self.seq_interval_spin.value())
        self.config.set("sequence_mode", self.seq_mode_combo.currentText())
        self._save_sequence_commands()

    def _save_config(self):
        self._collect_config()
        if self.config.save():
            self.statusBar().showMessage("Config saved.", 3000)
        else:
            QMessageBox.critical(self, "Error", "Could not save config.json")

    # ──────────────────────────────────────────────────────────────────────────
    # Port helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_ports(self):
        current = self.port_combo.currentText()
        ports = list_ports()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current in ports:
            self._set_combo(self.port_combo, current)
        elif ports:
            self.port_combo.setCurrentIndex(0)

    # ──────────────────────────────────────────────────────────────────────────
    # Connection
    # ──────────────────────────────────────────────────────────────────────────

    def _toggle_connection(self):
        if self.worker and self.worker.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, "No Port", "Please select a serial port.")
            return
        self.worker = SerialWorker(
            port=port,
            baud=int(self.baud_combo.currentText()),
            databits=int(self.databits_combo.currentText()),
            parity=self.parity_combo.currentText(),
            stopbits=self.stopbits_combo.currentText(),
            flowcontrol=self.flow_combo.currentText(),
            eol_rx=self.eol_rx_combo.currentText(),
            on_data=lambda d: self._signals.data_received.emit(d),
            on_error=lambda e: self._signals.error_occurred.emit(e),
        )
        self.worker.start()
        QTimer.singleShot(300, self._check_connected)

    def _check_connected(self):
        if self.worker and self.worker.is_connected:
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("background:#8B0000; color:white; font-weight:bold;")
            self.led_lbl.setStyleSheet("color:#00FF7F; font-size:18px;")
            self.conn_lbl.setText(f"Connected — {self.port_combo.currentText()}")
        else:
            self._disconnect()

    def _disconnect(self):
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=2)
            self.worker = None
        self._auto_timer.stop()
        self.auto_btn.setText("Start Auto")
        self.auto_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self.connect_btn.setText("Connect")
        self.connect_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self.led_lbl.setStyleSheet("color:#555555; font-size:18px;")
        self.conn_lbl.setText("Disconnected")

    # ──────────────────────────────────────────────────────────────────────────
    # Data reception
    # ──────────────────────────────────────────────────────────────────────────

    def _display_rx(self, data: bytes):
        line = self._format_line(data, "RX")
        self._append(line, self._color_rx)
        self.log.append(line)
        
        # Check alerts
        self._check_alerts(line)
        
        if self.worker:
            self.rx_lbl.setText(f"RX: {self._human(self.worker.rx_bytes)}")

    def _handle_error(self, error: str):
        self._disconnect()
        QMessageBox.critical(self, "Serial Error", error)

    def _format_line(self, data: bytes, direction: str) -> str:
        parts = []
        if self.chk_ts.isChecked():
            parts.append(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]")
        parts.append(direction)
        show_ascii = self.chk_ascii.isChecked()
        show_hex   = self.chk_hex.isChecked()
        if not show_ascii and not show_hex:
            show_ascii = True
        if show_ascii:
            text = data.decode("utf-8", errors="replace").rstrip("\r\n")
            parts.append(f"ASCII: {text}")
        if show_hex:
            parts.append(f"HEX: {data.hex(' ').upper()}")
        return "  ".join(parts) + "\n"

    def _append(self, text: str, color: str):
        # Add to full buffer
        self._full_log_buffer.append((text, color))
        
        # Only display if matches filter
        if self._filter_matches(text):
            self._append_raw(text, color)

    # ──────────────────────────────────────────────────────────────────────────
    # Sending
    # ──────────────────────────────────────────────────────────────────────────

    def _send_data(self):
        if not self.worker or not self.worker.is_connected:
            QMessageBox.warning(self, "Not Connected", "Connect to a serial port first.")
            return
        text = self.send_edit.text()
        if not text:
            return
        eol = EOL_TX_MAP.get(self.eol_tx_combo.currentText(), b"\n")
        try:
            if self.send_fmt.currentText() == "HEX":
                payload = bytes.fromhex(text.replace(" ", ""))
            else:
                payload = text.encode("utf-8")
            payload += eol
        except ValueError:
            QMessageBox.critical(self, "Format Error",
                                 "Invalid HEX string. Use space-separated bytes: AA BB CC")
            return
        self.worker.send(payload)
        line = self._format_line(payload, "TX")
        self._append(line, self._color_tx)
        self.log.append(line)
        self.tx_lbl.setText(f"TX: {self._human(self.worker.tx_bytes)}")
        self.config.add_to_history(text)
        self._update_history_combo()

    def _update_history_combo(self):
        history = self.config.get("cmd_history", [])
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        self.history_combo.addItems(history)
        self.history_combo.blockSignals(False)

    # ──────────────────────────────────────────────────────────────────────────
    # Auto send
    # ──────────────────────────────────────────────────────────────────────────

    def _toggle_auto_send(self):
        if self._auto_timer.isActive():
            self._auto_timer.stop()
            self.auto_btn.setText("Start Auto")
            self.auto_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        else:
            if not self.worker or not self.worker.is_connected:
                QMessageBox.warning(self, "Not Connected", "Connect first.")
                return
            ms = int(self.interval_spin.value() * 1000)
            self._auto_timer.start(ms)
            self.auto_btn.setText("Stop Auto")
            self.auto_btn.setStyleSheet("background:#8B0000; color:white; font-weight:bold;")

    # ──────────────────────────────────────────────────────────────────────────
    # Command Sequence
    # ──────────────────────────────────────────────────────────────────────────
    
    def _add_sequence_command(self):
        """Add a new empty command to the sequence"""
        row = self.seq_table.rowCount()
        self.seq_table.insertRow(row)
        
        # Number column
        num_item = QTableWidgetItem(str(row + 1))
        num_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.seq_table.setItem(row, 0, num_item)
        
        # Command column (editable)
        cmd_item = QTableWidgetItem("")
        self.seq_table.setItem(row, 1, cmd_item)
        
        # Send button column
        btn_send = QPushButton("▶")
        btn_send.setFixedSize(28, 25)
        btn_send.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        btn_send.clicked.connect(lambda: self._send_sequence_command_manual(row))
        self.seq_table.setCellWidget(row, 2, btn_send)
        
        # Move buttons column
        move_widget = QWidget()
        move_layout = QHBoxLayout(move_widget)
        move_layout.setContentsMargins(2, 2, 2, 2)
        move_layout.setSpacing(2)
        
        btn_up = QPushButton("↑")
        btn_up.setFixedSize(25, 25)
        btn_up.clicked.connect(lambda: self._move_sequence_command_up(row))
        btn_down = QPushButton("↓")
        btn_down.setFixedSize(25, 25)
        btn_down.clicked.connect(lambda: self._move_sequence_command_down(row))
        
        move_layout.addWidget(btn_up)
        move_layout.addWidget(btn_down)
        self.seq_table.setCellWidget(row, 3, move_widget)
        
        # Delete button column
        btn_delete = QPushButton("✕")
        btn_delete.setFixedSize(30, 25)
        btn_delete.setStyleSheet("background:#8B0000; color:white; font-weight:bold;")
        btn_delete.clicked.connect(lambda: self._remove_sequence_command(row))
        self.seq_table.setCellWidget(row, 4, btn_delete)
    
    def _remove_sequence_command(self, row: int):
        """Remove a command from the sequence"""
        if row < self.seq_table.rowCount():
            self.seq_table.removeRow(row)
            self._update_sequence_numbers()
            # Reconnect buttons after removal
            self._reconnect_sequence_buttons()
    
    def _move_sequence_command_up(self, row: int):
        """Move command up in the sequence"""
        if row <= 0:
            return
        self._swap_sequence_rows(row, row - 1)
        self.seq_table.selectRow(row - 1)
    
    def _move_sequence_command_down(self, row: int):
        """Move command down in the sequence"""
        if row >= self.seq_table.rowCount() - 1:
            return
        self._swap_sequence_rows(row, row + 1)
        self.seq_table.selectRow(row + 1)
    
    def _swap_sequence_rows(self, row1: int, row2: int):
        """Swap two rows in the sequence table"""
        # Swap command text
        text1 = self.seq_table.item(row1, 1).text()
        text2 = self.seq_table.item(row2, 1).text()
        self.seq_table.item(row1, 1).setText(text2)
        self.seq_table.item(row2, 1).setText(text1)
        
        self._update_sequence_numbers()
        self._reconnect_sequence_buttons()
    
    def _update_sequence_numbers(self):
        """Update the number column after changes"""
        for i in range(self.seq_table.rowCount()):
            self.seq_table.item(i, 0).setText(str(i + 1))
    
    def _reconnect_sequence_buttons(self):
        """Reconnect all button signals after row changes"""
        for row in range(self.seq_table.rowCount()):
            # Reconnect send button
            btn_send = self.seq_table.cellWidget(row, 2)
            if btn_send:
                try:
                    btn_send.clicked.disconnect()
                except:
                    pass
                btn_send.clicked.connect(lambda checked, r=row: self._send_sequence_command_manual(r))
            
            # Reconnect move buttons
            move_widget = self.seq_table.cellWidget(row, 3)
            if move_widget:
                layout = move_widget.layout()
                btn_up = layout.itemAt(0).widget()
                btn_down = layout.itemAt(1).widget()
                try:
                    btn_up.clicked.disconnect()
                    btn_down.clicked.disconnect()
                except:
                    pass
                btn_up.clicked.connect(lambda checked, r=row: self._move_sequence_command_up(r))
                btn_down.clicked.connect(lambda checked, r=row: self._move_sequence_command_down(r))
            
            # Reconnect delete button
            btn_delete = self.seq_table.cellWidget(row, 4)
            if btn_delete:
                try:
                    btn_delete.clicked.disconnect()
                except:
                    pass
                btn_delete.clicked.connect(lambda checked, r=row: self._remove_sequence_command(r))
    
    def _toggle_sequence(self):
        """Start or stop the command sequence"""
        if self._sequence_running:
            self._stop_sequence()
        else:
            self._start_sequence()
    
    def _start_sequence(self):
        """Start the command sequence"""
        if not self.worker or not self.worker.is_connected:
            QMessageBox.warning(self, "Not Connected", "Connect to a serial port first.")
            return
        
        if self.seq_table.rowCount() == 0:
            QMessageBox.warning(self, "Empty Sequence", "Add commands to the sequence first.")
            return
        
        self._sequence_running = True
        self._sequence_index = 0
        self.seq_start_btn.setText("Stop Sequence")
        self.seq_start_btn.setStyleSheet("background:#8B0000; color:white; font-weight:bold;")
        
        # Send first command immediately
        self._send_sequence_command(self._sequence_index)
        
        # Start timer for subsequent commands
        ms = int(self.seq_interval_spin.value() * 1000)
        self._sequence_timer.start(ms)
    
    def _stop_sequence(self):
        """Stop the command sequence"""
        self._sequence_running = False
        self._sequence_timer.stop()
        self.seq_start_btn.setText("Start Sequence")
        self.seq_start_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self._clear_sequence_highlight()
    
    def _send_next_sequence_cmd(self):
        """Send the next command in the sequence (called by timer)"""
        if not self._sequence_running:
            return
        
        self._sequence_index += 1
        
        # Check if we've reached the end
        if self._sequence_index >= self.seq_table.rowCount():
            mode = self.seq_mode_combo.currentText()
            if mode == "Restart":
                self._sequence_index = 0
            else:  # Stop
                self._stop_sequence()
                return
        
        self._send_sequence_command(self._sequence_index)
    
    def _send_sequence_command(self, index: int):
        """Send a specific command from the sequence"""
        if index < 0 or index >= self.seq_table.rowCount():
            return
        
        # Highlight the current row
        self._highlight_sequence_row(index)
        
        # Get the command text
        cmd_text = self.seq_table.item(index, 1).text()
        if not cmd_text:
            return
        
        # Expand variables
        cmd_text = self._expand_variables(cmd_text)
        self._sequence_cmd_counter += 1
        
        # Send the command (reuse the existing send logic)
        eol = EOL_TX_MAP.get(self.eol_tx_combo.currentText(), b"\n")
        try:
            if self.send_fmt.currentText() == "HEX":
                payload = bytes.fromhex(cmd_text.replace(" ", ""))
            else:
                payload = cmd_text.encode("utf-8")
            payload += eol
        except ValueError:
            self.statusBar().showMessage(f"Invalid command at row {index + 1}", 3000)
            return
        
        if self.worker and self.worker.is_connected:
            self.worker.send(payload)
            line = self._format_line(payload, "TX")
            self._append(line, self._color_tx)
            self.log.append(line)
            self.tx_lbl.setText(f"TX: {self._human(self.worker.tx_bytes)}")
    
    def _send_sequence_command_manual(self, index: int):
        """Send a specific command manually (without affecting sequence cycle)"""
        if not self.worker or not self.worker.is_connected:
            QMessageBox.warning(self, "Not Connected", "Connect to a serial port first.")
            return
        
        if index < 0 or index >= self.seq_table.rowCount():
            return
        
        # Get the command text
        cmd_text = self.seq_table.item(index, 1).text()
        if not cmd_text:
            return
        
        # Expand variables (but don't increment sequence counter)
        expanded = cmd_text.replace("{timestamp}", str(int(time.time())))
        expanded = expanded.replace("{random}", str(random.randint(0, 999)))
        # Use sequence counter but don't increment
        expanded = expanded.replace("{counter}", str(self._sequence_cmd_counter))
        
        # Send the command
        eol = EOL_TX_MAP.get(self.eol_tx_combo.currentText(), b"\n")
        try:
            if self.send_fmt.currentText() == "HEX":
                payload = bytes.fromhex(expanded.replace(" ", ""))
            else:
                payload = expanded.encode("utf-8")
            payload += eol
        except ValueError:
            self.statusBar().showMessage(f"Invalid command at row {index + 1}", 3000)
            return
        
        self.worker.send(payload)
        line = self._format_line(payload, "TX")
        self._append(line, self._color_tx)
        self.log.append(line)
        self.tx_lbl.setText(f"TX: {self._human(self.worker.tx_bytes)}")
        
        # Brief visual feedback
        self._highlight_sequence_row(index)
        QTimer.singleShot(200, self._clear_sequence_highlight)

    def _highlight_sequence_row(self, row: int):
        """Highlight a specific row in the sequence table"""
        self._clear_sequence_highlight()
        if row >= 0 and row < self.seq_table.rowCount():
            for col in range(self.seq_table.columnCount()):
                item = self.seq_table.item(row, col)
                if item:
                    item.setBackground(QColor("#FFD700"))  # Gold color
    
    def _clear_sequence_highlight(self):
        """Clear all highlights in the sequence table"""
        for row in range(self.seq_table.rowCount()):
            for col in range(self.seq_table.columnCount()):
                item = self.seq_table.item(row, col)
                if item:
                    item.setBackground(QColor("transparent"))
    
    def _load_sequence_commands(self):
        """Load sequence commands from config into the table"""
        commands = self.config.get("sequence_commands", [])
        for cmd in commands:
            row = self.seq_table.rowCount()
            self.seq_table.insertRow(row)
            
            # Number column
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.seq_table.setItem(row, 0, num_item)
            
            # Command column (editable)
            cmd_item = QTableWidgetItem(cmd)
            self.seq_table.setItem(row, 1, cmd_item)
            
            # Send button column
            btn_send = QPushButton("▶")
            btn_send.setFixedSize(28, 25)
            btn_send.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
            btn_send.clicked.connect(lambda checked, r=row: self._send_sequence_command_manual(r))
            self.seq_table.setCellWidget(row, 2, btn_send)
            
            # Move buttons column
            move_widget = QWidget()
            move_layout = QHBoxLayout(move_widget)
            move_layout.setContentsMargins(2, 2, 2, 2)
            move_layout.setSpacing(2)
            
            btn_up = QPushButton("↑")
            btn_up.setFixedSize(25, 25)
            btn_up.clicked.connect(lambda checked, r=row: self._move_sequence_command_up(r))
            btn_down = QPushButton("↓")
            btn_down.setFixedSize(25, 25)
            btn_down.clicked.connect(lambda checked, r=row: self._move_sequence_command_down(r))
            
            move_layout.addWidget(btn_up)
            move_layout.addWidget(btn_down)
            self.seq_table.setCellWidget(row, 3, move_widget)
            
            # Delete button column
            btn_delete = QPushButton("✕")
            btn_delete.setFixedSize(30, 25)
            btn_delete.setStyleSheet("background:#8B0000; color:white; font-weight:bold;")
            btn_delete.clicked.connect(lambda checked, r=row: self._remove_sequence_command(r))
            self.seq_table.setCellWidget(row, 4, btn_delete)
    
    def _save_sequence_commands(self):
        """Save sequence commands from table to config"""
        commands = []
        for row in range(self.seq_table.rowCount()):
            cmd_item = self.seq_table.item(row, 1)
            if cmd_item:
                commands.append(cmd_item.text())
        self.config.set("sequence_commands", commands)

    # ──────────────────────────────────────────────────────────────────────────
    # Export/Import Sequences
    # ──────────────────────────────────────────────────────────────────────────
    
    def _export_sequence(self):
        """Export current sequence to a file"""
        if self.seq_table.rowCount() == 0:
            QMessageBox.information(self, "Empty Sequence", "No commands to export.")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Sequence", "", "Sequence files (*.seq);;JSON files (*.json);;All (*)")
        if not path:
            return
        
        commands = []
        for row in range(self.seq_table.rowCount()):
            cmd_item = self.seq_table.item(row, 1)
            if cmd_item:
                commands.append(cmd_item.text())
        
        data = {
            "commands": commands,
            "interval": self.seq_interval_spin.value(),
            "mode": self.seq_mode_combo.currentText()
        }
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(f"Sequence exported: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Could not export sequence: {e}")
    
    def _import_sequence(self):
        """Import sequence from a file"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Sequence", "", "Sequence files (*.seq);;JSON files (*.json);;All (*)")
        if not path:
            return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if "commands" not in data:
                raise ValueError("Invalid sequence file format")
            
            # Clear current sequence
            self.seq_table.setRowCount(0)
            
            # Load commands
            for cmd in data["commands"]:
                self._add_sequence_command()
                row = self.seq_table.rowCount() - 1
                self.seq_table.item(row, 1).setText(cmd)
            
            # Load settings
            if "interval" in data:
                self.seq_interval_spin.setValue(float(data["interval"]))
            if "mode" in data:
                idx = self.seq_mode_combo.findText(data["mode"])
                if idx >= 0:
                    self.seq_mode_combo.setCurrentIndex(idx)
            
            self.statusBar().showMessage(f"Sequence imported: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Could not import sequence: {e}")
    
    # ──────────────────────────────────────────────────────────────────────────
    # Variable Expansion
    # ──────────────────────────────────────────────────────────────────────────
    
    def _expand_variables(self, text: str) -> str:
        """Expand variables in command text"""
        # {timestamp} - Unix timestamp
        text = text.replace("{timestamp}", str(int(time.time())))
        
        # {counter} - Sequence command counter
        text = text.replace("{counter}", str(self._sequence_cmd_counter))
        
        # {random} - Random number 0-999
        text = text.replace("{random}", str(random.randint(0, 999)))
        
        return text
    
    # ──────────────────────────────────────────────────────────────────────────
    # Search in Monitor
    # ──────────────────────────────────────────────────────────────────────────
    
    def _search_in_monitor(self):
        """Search for text in monitor"""
        self._search_text = self.search_edit.text()
        if not self._search_text:
            self.search_result_lbl.setText("")
            self._clear_search_highlights()
            return
        
        # Find all matches
        text = self.monitor.toPlainText()
        if self._search_text.lower() in text.lower():
            matches = text.lower().count(self._search_text.lower())
            self.search_result_lbl.setText(f"{matches} matches")
            self._highlight_search_matches()
        else:
            self.search_result_lbl.setText("No matches")
            self._clear_search_highlights()
    
    def _highlight_search_matches(self):
        """Highlight all search matches in monitor"""
        if not self._search_text:
            return
        
        cursor = self.monitor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        
        # Format for highlighting
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFFF00"))  # Yellow background
        fmt.setForeground(QColor("#000000"))  # Black text
        
        # Find and highlight all matches
        while True:
            cursor = self.monitor.document().find(self._search_text, cursor)
            if cursor.isNull():
                break
            cursor.mergeCharFormat(fmt)
    
    def _clear_search_highlights(self):
        """Clear search highlights"""
        cursor = self.monitor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        cursor.setCharFormat(fmt)
        self.monitor.setTextCursor(cursor)
    
    def _search_next(self):
        """Find next search match"""
        if not self._search_text:
            return
        cursor = self.monitor.textCursor()
        found_cursor = self.monitor.document().find(self._search_text, cursor)
        if not found_cursor.isNull():
            self.monitor.setTextCursor(found_cursor)
        else:
            # Wrap to beginning
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            found_cursor = self.monitor.document().find(self._search_text, cursor)
            if not found_cursor.isNull():
                self.monitor.setTextCursor(found_cursor)
    
    def _search_previous(self):
        """Find previous search match"""
        if not self._search_text:
            return
        cursor = self.monitor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Left)
        found_cursor = self.monitor.document().find(
            self._search_text, cursor, 
            self.monitor.document().FindFlag.FindBackward
        )
        if not found_cursor.isNull():
            self.monitor.setTextCursor(found_cursor)
        else:
            # Wrap to end
            cursor.movePosition(QTextCursor.MoveOperation.End)
            found_cursor = self.monitor.document().find(
                self._search_text, cursor,
                self.monitor.document().FindFlag.FindBackward
            )
            if not found_cursor.isNull():
                self.monitor.setTextCursor(found_cursor)
    
    # ──────────────────────────────────────────────────────────────────────────
    # Filters
    # ──────────────────────────────────────────────────────────────────────────
    
    def _apply_filter(self):
        """Apply filter to monitor display"""
        self._filter_text = self.filter_edit.text()
        self._filter_regex = self.filter_regex_chk.isChecked()
        
        if not self._filter_text:
            # Show all
            self.monitor.clear()
            for line in self._full_log_buffer:
                self._append_raw(line[0], line[1])  # text, color
            return
        
        # Filter and display
        self.monitor.clear()
        for line in self._full_log_buffer:
            text = line[0]
            if self._filter_matches(text):
                self._append_raw(text, line[1])
    
    def _filter_matches(self, text: str) -> bool:
        """Check if text matches current filter"""
        if not self._filter_text:
            return True
        
        if self._filter_regex:
            try:
                return bool(re.search(self._filter_text, text, re.IGNORECASE))
            except re.error:
                return False
        else:
            return self._filter_text.lower() in text.lower()
    
    def _append_raw(self, text: str, color: str):
        """Append text to monitor without adding to buffer"""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.monitor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, fmt)
        self.monitor.setTextCursor(cursor)
        self.monitor.ensureCursorVisible()
    
    # ──────────────────────────────────────────────────────────────────────────
    # Alerts
    # ──────────────────────────────────────────────────────────────────────────
    
    def _manage_alerts(self):
        """Open dialog to manage alerts"""
        from PyQt6.QtWidgets import QDialog, QListWidget, QListWidgetItem
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Alerts")
        dialog.setGeometry(100, 100, 500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Title
        title = QLabel("Alert Management - Configure patterns to trigger notifications")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        
        # Current alerts list
        layout.addWidget(QLabel("Active Alerts:"))
        self.alerts_list = QListWidget()
        self._refresh_alerts_list()
        layout.addWidget(self.alerts_list)
        
        # New alert form
        layout.addWidget(QLabel("Add New Alert:"))
        form_layout = QGridLayout()
        
        form_layout.addWidget(QLabel("Pattern:"), 0, 0)
        pattern_input = QLineEdit()
        pattern_input.setPlaceholderText("e.g., ERROR, FATAL, ^.*CRITICAL.*$")
        form_layout.addWidget(pattern_input, 0, 1)
        
        form_layout.addWidget(QLabel("Use Regex:"), 1, 0)
        regex_check = QCheckBox("Enable regex pattern matching")
        form_layout.addWidget(regex_check, 1, 1)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        btn_add = QPushButton("+ Add Alert")
        btn_add.setStyleSheet("background:#2E8B57; color:white;")
        def add_alert():
            pattern = pattern_input.text().strip()
            if not pattern:
                QMessageBox.warning(dialog, "Empty Pattern", "Please enter a pattern.")
                return
            
            # Check if pattern already exists
            for alert in self._alerts:
                if alert["pattern"] == pattern:
                    QMessageBox.warning(dialog, "Duplicate", "This pattern already exists.")
                    return
            
            # Validate regex if enabled
            if regex_check.isChecked():
                try:
                    re.compile(pattern)
                except re.error as e:
                    QMessageBox.critical(dialog, "Invalid Regex", f"Regex error: {e}")
                    return
            
            self._alerts.append({
                "pattern": pattern,
                "regex": regex_check.isChecked(),
                "sound": False
            })
            
            pattern_input.clear()
            regex_check.setChecked(False)
            self._refresh_alerts_list()
        
        btn_add.clicked.connect(add_alert)
        button_layout.addWidget(btn_add)
        
        btn_delete = QPushButton("🗑 Delete Selected")
        btn_delete.setStyleSheet("background:#8B0000; color:white;")
        def delete_alert():
            current = self.alerts_list.currentRow()
            if current < 0:
                QMessageBox.warning(dialog, "No Selection", "Select an alert to delete.")
                return
            self._alerts.pop(current)
            self._refresh_alerts_list()
        
        btn_delete.clicked.connect(delete_alert)
        button_layout.addWidget(btn_delete)
        
        btn_save = QPushButton("💾 Save Configuration")
        btn_save.setStyleSheet("background:#4682B4; color:white;")
        def save_alerts():
            self.config.set("alerts", self._alerts)
            if self.config.save():
                QMessageBox.information(dialog, "Saved", "Alerts configuration saved to config.json")
            else:
                QMessageBox.critical(dialog, "Error", "Could not save configuration.")
        
        btn_save.clicked.connect(save_alerts)
        button_layout.addWidget(btn_save)
        
        layout.addLayout(button_layout)
        
        # Close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        
        dialog.exec()
    
    def _refresh_alerts_list(self):
        """Update the alerts list widget"""
        self.alerts_list.clear()
        for alert in self._alerts:
            pattern = alert["pattern"]
            alert_type = " [REGEX]" if alert["regex"] else " [TEXT]"
            item_text = pattern + alert_type
            item = QListWidgetItem(item_text)
            self.alerts_list.addItem(item)
    
    def _check_alerts(self, text: str):
        """Check if received data matches any alert pattern"""
        for alert in self._alerts:
            pattern = alert["pattern"]
            is_regex = alert.get("regex", False)
            
            match = False
            if is_regex:
                try:
                    match = bool(re.search(pattern, text, re.IGNORECASE))
                except re.error:
                    pass
            else:
                match = pattern.lower() in text.lower()
            
            if match:
                # Trigger alert
                self.statusBar().showMessage(f"🔔 ALERT: {pattern}", 5000)
                # Could add sound here if needed
                break
    
    # ──────────────────────────────────────────────────────────────────────────
    # Statistics
    # ──────────────────────────────────────────────────────────────────────────
    
    def _update_statistics(self):
        """Update transmission statistics"""
        if not self.worker:
            return
        
        elapsed = time.time() - self._stats_start_time
        if elapsed > 0:
            rx_bytes = self.worker.rx_bytes
            tx_bytes = self.worker.tx_bytes
            
            # Calculate speed (bytes per second)
            total_bytes = rx_bytes + tx_bytes
            speed = total_bytes / elapsed
            
            # Update labels
            self.speed_lbl.setText(f"Speed: {self._human(int(speed))}/s")
            self.rx_lbl.setText(f"RX: {self._human(rx_bytes)}")
            self.tx_lbl.setText(f"TX: {self._human(tx_bytes)}")
    
    # ──────────────────────────────────────────────────────────────────────────
    # Keyboard Shortcuts
    # ──────────────────────────────────────────────────────────────────────────
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Ctrl+Enter: Send command
        QShortcut(QKeySequence("Ctrl+Return"), self, self._send_data)
        
        # Ctrl+L: Clear monitor
        QShortcut(QKeySequence("Ctrl+L"), self, self._clear_monitor)
        
        # Ctrl+K: Toggle connection
        QShortcut(QKeySequence("Ctrl+K"), self, self._toggle_connection)
        
        # Ctrl+S: Save config
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_config)
        
        # Ctrl+F: Focus search
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search_edit.setFocus())
        
        # F1-F5: Quick commands (if configured)
        for i in range(1, 6):
            key = f"F{i}"
            QShortcut(QKeySequence(key), self, lambda n=i: self._send_quick_command(n))
    
    def _send_quick_command(self, num: int):
        """Send a quick command (F1-F5)"""
        quick_cmds = self.config.get("quick_commands", {})
        cmd = quick_cmds.get(f"F{num}", "")
        if cmd:
            self.send_edit.setText(cmd)
            self._send_data()

    # ──────────────────────────────────────────────────────────────────────────
    # Monitor controls
    # ──────────────────────────────────────────────────────────────────────────

    def _clear_monitor(self):
        self.monitor.clear()
        self.log.clear()
        self._full_log_buffer.clear()

    def _save_log(self):
        if len(self.log) == 0:
            QMessageBox.information(self, "Empty Log", "Nothing to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", "", "Log files (*.log);;Text files (*.txt);;All (*)")
        if path:
            if self.log.save(path):
                self.statusBar().showMessage(f"Log saved: {path}", 3000)
            else:
                QMessageBox.critical(self, "Error", "Could not write log file.")

    # ──────────────────────────────────────────────────────────────────────────
    # Colors
    # ──────────────────────────────────────────────────────────────────────────

    def _pick_color(self, target: str):
        initial = {"rx": self._color_rx, "tx": self._color_tx, "bg": self._color_bg}[target]
        color = QColorDialog.getColor(QColor(initial), self, f"Pick {target.upper()} color")
        if not color.isValid():
            return
        hex_color = color.name()
        if target == "rx":
            self._color_rx = hex_color
            self._apply_color_btn(self.btn_crx, hex_color)
        elif target == "tx":
            self._color_tx = hex_color
            self._apply_color_btn(self.btn_ctx, hex_color)
        else:
            self._color_bg = hex_color
            self._apply_color_btn(self.btn_cbg, hex_color)
            self._apply_monitor_bg(hex_color)

    def _apply_color_btn(self, btn: QPushButton, color: str):
        # Pick contrasting text color
        c = QColor(color)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        fg = "#000000" if lum > 128 else "#ffffff"
        btn.setStyleSheet(f"background:{color}; color:{fg}; font-weight:bold;")

    def _apply_monitor_bg(self, color: str):
        self.monitor.setStyleSheet(f"background-color: {color};")

    # ──────────────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────────────

    _dark_mode = True

    def _toggle_theme(self):
        if self._dark_mode:
            self._apply_light_theme()
            self.theme_btn.setText("🌙 Dark")
            self._dark_mode = False
            self.config.set("theme", "light")
        else:
            self._apply_dark_theme()
            self.theme_btn.setText("☀ Light")
            self._dark_mode = True
            self.config.set("theme", "dark")

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#2b2b2b; color:#e0e0e0; }
            QGroupBox { border:1px solid #555; margin-top:6px; color:#e0e0e0; }
            QGroupBox::title { subcontrol-origin:margin; left:8px; }
            QComboBox, QLineEdit, QDoubleSpinBox { background:#3c3c3c; color:#e0e0e0; border:1px solid #555; }
            QPushButton { background:#444; color:#e0e0e0; border:1px solid #666; padding:2px 6px; }
            QPushButton:hover { background:#555; }
            QCheckBox { color:#e0e0e0; }
            QLabel { color:#e0e0e0; }
        """)

    def _apply_light_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#f0f0f0; color:#1a1a1a; }
            QGroupBox { border:1px solid #aaa; margin-top:6px; color:#1a1a1a; }
            QGroupBox::title { subcontrol-origin:margin; left:8px; }
            QComboBox, QLineEdit, QDoubleSpinBox { background:#ffffff; color:#1a1a1a; border:1px solid #aaa; }
            QPushButton { background:#e0e0e0; color:#1a1a1a; border:1px solid #aaa; padding:2px 6px; }
            QPushButton:hover { background:#d0d0d0; }
            QCheckBox { color:#1a1a1a; }
            QLabel { color:#1a1a1a; }
        """)

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _human(n: int) -> str:
        if n < 1024: return f"{n} B"
        if n < 1048576: return f"{n/1024:.1f} KB"
        return f"{n/1048576:.1f} MB"

    @staticmethod
    def _set_combo(combo: QComboBox, value: str):
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def closeEvent(self, event):
        self._collect_config()
        self.config.save()
        if self.worker:
            self.worker.stop()
        event.accept()
