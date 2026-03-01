"""
serial_monitor.py — Main application window (PyQt6).
"""

import threading
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QCheckBox, QTextEdit, QLineEdit,
    QStatusBar, QFileDialog, QMessageBox, QFrame, QSplitter,
    QColorDialog, QGroupBox, QSpinBox, QDoubleSpinBox, QToolBar,
    QSizePolicy,
)
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QPalette
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

        # Colors
        self._color_rx = self.config.get("color_rx", "#00FF7F")
        self._color_tx = self.config.get("color_tx", "#00BFFF")
        self._color_bg = self.config.get("color_bg", "#1C1C1C")

        self.setWindowTitle("Serial Monitor — Embedded Systems")
        self.resize(1150, 800)
        self._build_ui()
        self._load_config_into_ui()

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
        root.addWidget(self._build_monitor(), stretch=1)
        root.addWidget(self._build_send_panel())

        self._build_status_bar()

    # ── Config panel ──────────────────────────────────────────────────────────
    def _build_config_panel(self):
        box = QGroupBox("Serial Configuration")
        grid = QGridLayout(box)
        grid.setSpacing(4)

        def lbl(text): return QLabel(text)
        def combo(vals, width=90):
            c = QComboBox(); c.addItems(vals); c.setFixedWidth(width); return c

        # Row 0
        r = 0
        grid.addWidget(lbl("Port:"), r, 0)
        self.port_combo = combo([], 110)
        grid.addWidget(self.port_combo, r, 1)
        btn_refresh = QPushButton("⟳"); btn_refresh.setFixedWidth(28)
        btn_refresh.clicked.connect(self._refresh_ports)
        grid.addWidget(btn_refresh, r, 2)

        grid.addWidget(lbl("Baud:"), r, 3)
        self.baud_combo = combo(BAUD_RATES, 100)
        grid.addWidget(self.baud_combo, r, 4)

        grid.addWidget(lbl("Data:"), r, 5)
        self.databits_combo = combo(DATA_BITS, 55)
        grid.addWidget(self.databits_combo, r, 6)

        grid.addWidget(lbl("Parity:"), r, 7)
        self.parity_combo = combo(PARITIES, 80)
        grid.addWidget(self.parity_combo, r, 8)

        grid.addWidget(lbl("Stop:"), r, 9)
        self.stopbits_combo = combo(STOP_BITS, 55)
        grid.addWidget(self.stopbits_combo, r, 10)

        grid.addWidget(lbl("Flow:"), r, 11)
        self.flow_combo = combo(FLOW_CTRL, 90)
        grid.addWidget(self.flow_combo, r, 12)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(100)
        self.connect_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        self.connect_btn.clicked.connect(self._toggle_connection)
        grid.addWidget(self.connect_btn, r, 13, 1, 2)

        # Row 1
        r = 1
        grid.addWidget(lbl("EOL TX:"), r, 0)
        self.eol_tx_combo = combo(EOL_OPT, 80)
        grid.addWidget(self.eol_tx_combo, r, 1)

        grid.addWidget(lbl("EOL RX:"), r, 3)
        self.eol_rx_combo = combo(EOL_OPT, 80)
        grid.addWidget(self.eol_rx_combo, r, 4)

        grid.addWidget(lbl("Show:"), r, 5)
        self.chk_ascii = QCheckBox("ASCII"); self.chk_ascii.setChecked(True)
        self.chk_hex   = QCheckBox("HEX")
        self.chk_ts    = QCheckBox("Timestamp"); self.chk_ts.setChecked(True)
        grid.addWidget(self.chk_ascii, r, 6)
        grid.addWidget(self.chk_hex,   r, 7)
        grid.addWidget(self.chk_ts,    r, 8)

        grid.addWidget(lbl("Colors:"), r, 9)
        self.btn_crx = QPushButton("RX"); self.btn_crx.setFixedWidth(44)
        self.btn_ctx = QPushButton("TX"); self.btn_ctx.setFixedWidth(44)
        self.btn_cbg = QPushButton("BG"); self.btn_cbg.setFixedWidth(44)
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
        self.theme_btn.clicked.connect(self._toggle_theme)
        grid.addWidget(self.theme_btn, r, 13)

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
        self.rx_lbl = QLabel("RX: 0 B")
        self.tx_lbl = QLabel("TX: 0 B")
        toolbar.addWidget(self.tx_lbl)
        toolbar.addWidget(self.rx_lbl)
        vbox.addLayout(toolbar)

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
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.monitor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, fmt)
        self.monitor.setTextCursor(cursor)
        self.monitor.ensureCursorVisible()

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
    # Monitor controls
    # ──────────────────────────────────────────────────────────────────────────

    def _clear_monitor(self):
        self.monitor.clear()
        self.log.clear()

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
