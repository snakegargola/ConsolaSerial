"""
serial_monitor.py — Main application window (PyQt6).
"""

import threading
import os
import getpass
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
    QTabBar, QInputDialog, QStackedWidget,
)
from PyQt6.QtGui import (QColor, QFont, QTextCharFormat, QTextCursor, QPalette,
                         QShortcut, QKeySequence, QAction, QImage, QPixmap,
                         QPainter, QTransform, QValidator)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from .config_manager import ConfigManager, ScopedConfig, DEFAULT_CONFIG
from .serial_worker import (
    SerialWorker, list_port_details, list_bridge_interface_ports,
)
from .i2c_worker import (
    I2cScanWorker, I2cTransactionWorker, Ssd1306Worker, I2cRawWriteWorker,
    I2cSequenceWorker, I2cMemoryWorker, list_i2c_bridge_devices,
    I2cLabWorker, I2cBusDiagnosticWorker, ssd1306_init_steps,
)
from .log_manager import LogManager
from .display_image_converter import convert_image
from .i2c_device_inspector import I2cDeviceInspector
from .i2c_transaction_lab import I2cTransactionLab
from .i2c_bus import I2cBusSettings
from .serial_payload import encode_serial_payload, format_payload_preview
from .uart_tools_widget import UartToolsPanel
from .spi_session_panel import SpiSessionPanel
from .gpio_session_panel import GpioSessionPanel
from .ui_theme import contrast_text, set_role, stylesheet
from .bridge_interface_manager import (
    InterfaceBusyError, UsbBridgeInterfaceManager,
)
from .usb_bridge import (
    GPIO, I2C, SPI, UART, capability_summary, discover_usb_bridges,
)

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


class HexByteValidator(QValidator):
    """Allow only whitespace-separated HEX digits in the send field."""

    def validate(self, text, position):
        if any(
            not character.isspace()
            and character not in "0123456789abcdefABCDEF"
            for character in text
        ):
            return QValidator.State.Invalid, text, position
        digits = "".join(text.split())
        state = (
            QValidator.State.Acceptable
            if digits and len(digits) % 2 == 0
            else QValidator.State.Intermediate
        )
        return state, text, position


# Worker signals bridge (PyQt signals must live in QObject)
class _Signals(QObject):
    data_received = pyqtSignal(bytes)
    raw_data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    i2c_found = pyqtSignal(int)
    i2c_progress = pyqtSignal(int, int)
    i2c_done = pyqtSignal(list, bool, float)
    i2c_error = pyqtSignal(str)
    i2c_inspector_error = pyqtSignal(str, object)
    i2c_transaction_done = pyqtSignal(str, bytes, object)
    i2c_memory_done = pyqtSignal(str, bytes)
    i2c_display_done = pyqtSignal(str)
    i2c_sequence_step = pyqtSignal(int)
    i2c_sequence_done = pyqtSignal(bool)
    i2c_lab_done = pyqtSignal(object)
    i2c_lab_error = pyqtSignal(object)
    i2c_diagnostic_done = pyqtSignal(object)
    usb_bridges_discovered = pyqtSignal(object, str)


class SerialMonitorApp(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self._manages_usb_bridges = not hasattr(self, "channel_manager")
        if self._manages_usb_bridges:
            self.usb_bridge_detection_error = "Detecting adapters…"
            self.usb_bridge_adapters = []
            self.active_bridge = None
            self.channel_manager = UsbBridgeInterfaceManager(capabilities={})
            self._bridge_refresh_running = False
            self._bridge_refresh_was_manual = False
            self._closing = False
        self.worker: SerialWorker | None = None
        self._connection_established = False
        self.i2c_worker: I2cScanWorker | None = None
        self.log = LogManager()
        self._signals = _Signals()
        self._signals.data_received.connect(self._display_rx)
        self._signals.raw_data_received.connect(self._process_uart_loopback_rx)
        self._signals.error_occurred.connect(self._handle_error)
        self._signals.i2c_found.connect(self._i2c_device_found)
        self._signals.i2c_progress.connect(self._i2c_scan_progress)
        self._signals.i2c_done.connect(self._i2c_scan_done)
        self._signals.i2c_error.connect(self._i2c_scan_error)
        self._signals.i2c_inspector_error.connect(self._i2c_inspector_error)
        self._signals.i2c_transaction_done.connect(self._i2c_transaction_done)
        self._signals.i2c_memory_done.connect(self._i2c_memory_done)
        self._signals.i2c_display_done.connect(self._i2c_display_done)
        self._signals.i2c_sequence_step.connect(self._i2c_sequence_step_done)
        self._signals.i2c_sequence_done.connect(self._i2c_sequence_finished)
        self._signals.i2c_lab_done.connect(self._i2c_lab_done)
        self._signals.i2c_lab_error.connect(self._i2c_lab_error)
        self._signals.i2c_diagnostic_done.connect(self._i2c_diagnostic_done)
        if self._manages_usb_bridges:
            self._signals.usb_bridges_discovered.connect(
                self._usb_bridge_discovery_finished
            )
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
        
        # Simple literal search
        self._search_text = ""
        self._search_results = []
        self._search_result_index = -1
        
        # Alerts
        self._alerts = []  # List of {"pattern": str, "regex": bool, "sound": bool}

        # Colors
        self._color_rx = self.config.get("color_rx", "#00FF7F")
        self._color_tx = self.config.get("color_tx", "#00BFFF")
        self._color_bg = self.config.get("color_bg", "#1C1C1C")

        self.setWindowTitle("Serial Monitor — Embedded Systems")
        self.setMinimumSize(1080, 700)
        self.resize(1440, 900)
        self._build_ui()
        self._load_config_into_ui()
        self._polish_widget_tree()
        self._setup_shortcuts()
        if self._manages_usb_bridges:
            self._bridge_monitor_timer = QTimer(self)
            self._bridge_monitor_timer.setInterval(3000)
            self._bridge_monitor_timer.timeout.connect(self._refresh_usb_bridges)
            self._bridge_monitor_timer.start()
            QTimer.singleShot(0, self._refresh_usb_bridges)

    # ──────────────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("appSurface")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 4)
        root.addWidget(self._build_usb_bridge_mode_panel())
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        root.addWidget(self.main_tabs, stretch=1)

        serial_tab = QWidget()
        serial_root = QVBoxLayout(serial_tab)
        serial_root.setSpacing(4)
        serial_root.setContentsMargins(0, 0, 0, 0)
        serial_root.addWidget(self._build_config_panel())
        serial_root.addWidget(self._build_uart_tools_panel())
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        self.main_splitter = splitter
        sequence = self._build_sequence_panel()
        sequence.setMinimumWidth(320)
        sequence.setMaximumWidth(520)
        splitter.addWidget(sequence)
        right = QWidget()
        right_root = QVBoxLayout(right)
        right_root.setSpacing(4)
        right_root.setContentsMargins(0, 0, 0, 0)
        right_root.addWidget(self._build_monitor(), stretch=1)
        right_root.addWidget(self._build_send_panel())
        right.setMinimumWidth(420)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        width = max(320, min(520, int(self.config.get("sequence_panel_width", 360))))
        splitter.setSizes([width, 900])
        serial_root.addWidget(splitter, stretch=1)

        self.main_tabs.addTab(serial_tab, "Serial console")
        self.main_tabs.addTab(self._build_usb_bridge_workspace(), "Protocol bridge")
        self._build_status_bar()
        self.main_tabs.currentChanged.connect(
            lambda index: self.statusBar().setVisible(index == 0)
        )

    def _build_usb_bridge_mode_panel(self):
        box = QGroupBox("USB protocol bridge")
        box.setToolTip("Select one physical bridge and assign a protocol to each independent interface.")
        outer = QVBoxLayout(box)
        selector = QHBoxLayout()
        selector.addWidget(QLabel("Adapter:"))
        self.usb_bridge_combo = QComboBox()
        for bridge in self.usb_bridge_adapters:
            self.usb_bridge_combo.addItem(bridge.label, bridge)
        if not self.usb_bridge_adapters:
            message = self.usb_bridge_detection_error or "No supported adapter detected"
            self.usb_bridge_combo.addItem(message, None)
        selector.addWidget(self.usb_bridge_combo, stretch=1)
        self.usb_bridge_refresh_btn = QPushButton("Refresh")
        self.usb_bridge_refresh_btn.clicked.connect(
            lambda: self._refresh_usb_bridges(manual=True)
        )
        selector.addWidget(self.usb_bridge_refresh_btn)
        outer.addLayout(selector)
        self.usb_bridge_capabilities = QLabel()
        self.usb_bridge_capabilities.setWordWrap(True)
        outer.addWidget(self.usb_bridge_capabilities)
        self.usb_bridge_modes_widget = QWidget()
        self.usb_bridge_modes_layout = QHBoxLayout(self.usb_bridge_modes_widget)
        self.usb_bridge_modes_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.usb_bridge_modes_widget)
        self.usb_bridge_combo.currentIndexChanged.connect(
            self._usb_bridge_adapter_changed
        )
        return box

    def _build_usb_bridge_workspace(self):
        """Create sessions from the interfaces advertised by the adapter."""
        workspace = QWidget()
        root = QVBoxLayout(workspace)
        root.setContentsMargins(10, 10, 10, 10)
        header = QLabel("Protocol bridge workspace")
        header.setObjectName("pageTitle")
        root.addWidget(header)
        self.usb_bridge_note = QLabel()
        self.usb_bridge_note.setObjectName("pageSubtitle")
        self.usb_bridge_note.setWordWrap(True)
        root.addWidget(self.usb_bridge_note)
        self.usb_bridge_channel_tabs = QTabWidget()
        self.usb_bridge_channel_tabs.setDocumentMode(True)
        root.addWidget(self.usb_bridge_channel_tabs, stretch=1)
        self._rebuild_usb_bridge_workspace()
        return workspace

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_usb_bridge_workspace(self):
        """Recreate interface panels after selecting a physical adapter."""
        for session in getattr(self, "usb_bridge_uart_sessions", {}).values():
            session.shutdown_session()
        for session in getattr(self, "usb_bridge_i2c_sessions", {}).values():
            session.shutdown_session()
        for session in getattr(self, "usb_bridge_spi_sessions", {}).values():
            session.shutdown_session()
        for session in getattr(self, "usb_bridge_gpio_sessions", {}).values():
            session.shutdown_session()
        self.usb_bridge_channel_tabs.clear()
        self._clear_layout(self.usb_bridge_modes_layout)
        self.usb_bridge_mode_combos = {}
        self.usb_bridge_channel_stacks = {}
        self.usb_bridge_uart_sessions = {}
        self.usb_bridge_i2c_sessions = {}
        self.usb_bridge_spi_sessions = {}
        self.usb_bridge_gpio_sessions = {}
        bridge = self.usb_bridge_combo.currentData()
        self.active_bridge = bridge
        if bridge is None:
            self.channel_manager = UsbBridgeInterfaceManager(capabilities={})
            self.usb_bridge_capabilities.setText(
                "Connect a supported bridge; detection updates automatically."
            )
            self.usb_bridge_note.setText(
                "The general USB serial tab remains available for ordinary adapters."
            )
            return

        capabilities = {
            interface.name: interface.capabilities
            for interface in bridge.interfaces
        }
        saved_modes = self.config.get("usb_bridge_modes", {}).get(bridge.key, {})
        if not saved_modes and bridge.pid in (0x6011, 0x6043, 0x6048):
            saved_modes = {
                "A": self.config.get("ft4232_channel_a_mode", I2C),
                "B": self.config.get("ft4232_channel_b_mode", I2C),
            }
        requested_modes = {}
        for interface in bridge.interfaces:
            default_mode = I2C if I2C in interface.capabilities else UART
            requested = str(saved_modes.get(interface.name, default_mode)).upper()
            implemented = {UART, I2C, SPI, GPIO} & interface.capabilities
            requested_modes[interface.name] = (
                requested if requested in implemented else default_mode
            )
        self.channel_manager = UsbBridgeInterfaceManager(
            requested_modes, capabilities=capabilities
        )
        self.usb_bridge_capabilities.setText(
            f"Detected: {bridge.label} — {capability_summary(bridge)}"
        )
        self.usb_bridge_note.setText(
            "Each interface is independent. Only capabilities reported for this "
            "chip are shown. GPIO is available as a dedicated mode on every "
            "compatible interface and as auxiliary pins inside SPI."
        )

        for interface in bridge.interfaces:
            channel = interface.name
            implemented = [
                protocol for protocol in (UART, I2C, SPI, GPIO)
                if protocol in interface.capabilities
            ]
            self.usb_bridge_modes_layout.addWidget(QLabel(f"Interface {channel}:"))
            combo = QComboBox()
            combo.addItems(implemented)
            combo.setCurrentText(self.channel_manager.mode(channel))
            combo.currentTextChanged.connect(self._usb_bridge_modes_changed)
            self.usb_bridge_modes_layout.addWidget(combo)
            self.usb_bridge_mode_combos[channel] = combo

            page = QWidget()
            page_root = QVBoxLayout(page)
            page_root.setContentsMargins(0, 0, 0, 0)
            stack = QStackedWidget()
            self.usb_bridge_channel_stacks[channel] = stack
            if UART in interface.capabilities:
                uart_config = ScopedConfig(
                    self.config,
                    ("usb_bridge_sessions", bridge.key, channel, "uart"),
                    DEFAULT_CONFIG,
                )
                uart = UartSessionPanel(
                    interface, bridge, uart_config, self.channel_manager
                )
                self.usb_bridge_uart_sessions[channel] = uart
                stack.addWidget(uart)
            if I2C in interface.capabilities:
                i2c_config = ScopedConfig(
                    self.config,
                    ("usb_bridge_sessions", bridge.key, channel, "i2c"),
                    DEFAULT_CONFIG,
                )
                i2c = I2cSessionPanel(
                    interface, bridge, i2c_config, self.channel_manager
                )
                self.usb_bridge_i2c_sessions[channel] = i2c
                stack.addWidget(i2c)
            if SPI in interface.capabilities:
                spi_config = ScopedConfig(
                    self.config,
                    ("usb_bridge_sessions", bridge.key, channel, "spi"),
                    DEFAULT_CONFIG,
                )
                spi = SpiSessionPanel(
                    interface, bridge, spi_config, self.channel_manager
                )
                self.usb_bridge_spi_sessions[channel] = spi
                stack.addWidget(spi)
            if GPIO in interface.capabilities:
                gpio_config = ScopedConfig(
                    self.config,
                    ("usb_bridge_sessions", bridge.key, channel, "gpio"),
                    DEFAULT_CONFIG,
                )
                gpio = GpioSessionPanel(
                    interface, bridge, gpio_config, self.channel_manager
                )
                self.usb_bridge_gpio_sessions[channel] = gpio
                stack.addWidget(gpio)
            page_root.addWidget(stack)
            self.usb_bridge_channel_tabs.addTab(page, f"Interface {channel}")
        self.usb_bridge_modes_layout.addStretch()
        self._apply_usb_bridge_workspace_modes(show_error=False)
        self._polish_widget_tree()

    def _apply_usb_bridge_workspace_modes(self, show_error=True):
        """Switch a panel only when its outgoing session is idle."""
        if not hasattr(self, "usb_bridge_channel_stacks"):
            return
        for tab_index, (channel, combo) in enumerate(
            self.usb_bridge_mode_combos.items()
        ):
            desired = combo.currentText().upper()
            current = self.channel_manager.mode(channel)
            if desired != current:
                current_session = self._usb_bridge_session(channel, current)
                if current_session.is_session_active():
                    combo.blockSignals(True)
                    combo.setCurrentText(current)
                    combo.blockSignals(False)
                    if show_error:
                        QMessageBox.warning(
                            self, "Adapter interface busy",
                            f"Disconnect or stop interface {channel} before changing "
                            f"from {current} to {desired}.",
                        )
                    desired = current
                else:
                    current_session.shutdown_session()
                    try:
                        self.channel_manager.set_mode(channel, desired)
                    except InterfaceBusyError as exc:
                        combo.blockSignals(True)
                        combo.setCurrentText(current)
                        combo.blockSignals(False)
                        if show_error:
                            QMessageBox.warning(self, "Adapter interface busy", str(exc))
                        desired = current
            stack = self.usb_bridge_channel_stacks[channel]
            target = self._usb_bridge_session(channel, desired)
            stack.setCurrentWidget(target)
            if desired in (I2C, SPI, GPIO):
                target.activate_session()
            self.usb_bridge_channel_tabs.setTabText(
                tab_index, f"Interface {channel} — {desired}"
            )

    def _usb_bridge_session(self, channel, mode):
        """Return the session widget for one implemented protocol mode."""
        sessions = {
            UART: self.usb_bridge_uart_sessions,
            I2C: self.usb_bridge_i2c_sessions,
            SPI: self.usb_bridge_spi_sessions,
            GPIO: self.usb_bridge_gpio_sessions,
        }
        return sessions.get(mode, {}).get(channel)

    def _build_i2c_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        config_box = QGroupBox("USB bridge MPSSE configuration")
        grid = QGridLayout(config_box)
        grid.addWidget(QLabel("Device:"), 0, 0)
        self.i2c_device_combo = QComboBox()
        self.i2c_device_combo.setToolTip("Detected USB bridges with I²C capability")
        grid.addWidget(self.i2c_device_combo, 0, 1, 1, 2)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_i2c_devices)
        grid.addWidget(refresh, 0, 3)
        grid.addWidget(QLabel("Channel:"), 1, 0)
        self.i2c_channel_combo = QComboBox()
        self.i2c_channel_combo.addItem("A (MPSSE interface 1)", 1)
        self.i2c_channel_combo.addItem("B (MPSSE interface 2)", 2)
        grid.addWidget(self.i2c_channel_combo, 1, 1)
        grid.addWidget(QLabel("Clock:"), 1, 2)
        self.i2c_frequency_combo = QComboBox()
        self.i2c_frequency_combo.addItem("10 kHz", 10_000)
        self.i2c_frequency_combo.addItem("50 kHz", 50_000)
        self.i2c_frequency_combo.addItem("100 kHz", 100_000)
        self.i2c_frequency_combo.addItem("400 kHz", 400_000)
        self.i2c_frequency_combo.addItem("1 MHz", 1_000_000)
        self.i2c_frequency_combo.setEditable(True)
        self.i2c_frequency_combo.setToolTip(
            "Select a preset or type a frequency such as 250 kHz or 100000 Hz."
        )
        grid.addWidget(self.i2c_frequency_combo, 1, 3)
        self.i2c_clock_stretching = QCheckBox("Clock stretching")
        self.i2c_clock_stretching.setToolTip(
            "Requires xDBUS7 connected to SCL. Check the adapter wiring note."
        )
        grid.addWidget(self.i2c_clock_stretching, 1, 4)
        grid.addWidget(QLabel("Retries:"), 1, 5)
        self.i2c_retry_count = QSpinBox()
        self.i2c_retry_count.setRange(1, 16)
        self.i2c_retry_count.setValue(3)
        grid.addWidget(self.i2c_retry_count, 1, 6)
        addressing = QLabel("Device addressing: 7-bit")
        addressing.setProperty("role", "hint")
        grid.addWidget(addressing, 2, 0, 1, 7)
        root.addWidget(config_box)

        wiring = QLabel(
            "MPSSE wiring: xDBUS0 = SCL, xDBUS1 + xDBUS2 = SDA. Use pull-up "
            "resistors on SCL/SDA; x is the selected interface letter."
        )
        wiring.setWordWrap(True)
        root.addWidget(wiring)

        self.i2c_tools_tabs = QTabWidget()
        scanner_tab = QWidget()
        scanner_root = QVBoxLayout(scanner_tab)
        lab_tab = QWidget()
        lab_root = QVBoxLayout(lab_tab)
        read_write_tab = QWidget()
        read_write_root = QVBoxLayout(read_write_tab)
        display_tab = QWidget()
        display_root = QVBoxLayout(display_tab)
        trace_tab = QWidget()
        trace_root = QVBoxLayout(trace_tab)
        self.i2c_tools_tabs.addTab(scanner_tab, "Scanner")
        self.i2c_tools_tabs.addTab(lab_tab, "Transaction Lab")
        self.i2c_tools_tabs.addTab(read_write_tab, "Device Inspector")
        self.i2c_tools_tabs.addTab(display_tab, "Display Test")
        self.i2c_tools_tabs.addTab(trace_tab, "Sequence Builder")
        root.addWidget(self.i2c_tools_tabs, stretch=1)

        controls = QHBoxLayout()
        self.i2c_scan_btn = QPushButton("Scan I²C bus")
        self.i2c_scan_btn.clicked.connect(self._toggle_i2c_scan)
        controls.addWidget(self.i2c_scan_btn)
        self.i2c_progress_bar = QProgressBar()
        self.i2c_progress_bar.setRange(0, 117)
        controls.addWidget(self.i2c_progress_bar, stretch=1)
        scanner_root.addLayout(controls)
        self.i2c_matrix = QTableWidget(8, 16)
        self.i2c_matrix.setHorizontalHeaderLabels([f"{value:X}" for value in range(16)])
        self.i2c_matrix.setVerticalHeaderLabels([f"{value:02X}:" for value in range(0, 0x80, 0x10)])
        self.i2c_matrix.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.i2c_matrix.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.i2c_matrix.cellClicked.connect(self._i2c_matrix_address_clicked)
        self.i2c_matrix.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.i2c_matrix.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.i2c_matrix.setFont(QFont("Courier New", 10))
        scanner_root.addWidget(self.i2c_matrix, stretch=1)
        self.i2c_summary = QLabel("Press Scan I²C bus to search addresses 0x03–0x77.")
        self.i2c_summary.setWordWrap(True)
        scanner_root.addWidget(self.i2c_summary)

        self.i2c_transaction_lab = I2cTransactionLab()
        self.i2c_transaction_lab.transaction_requested.connect(
            self._start_i2c_lab_transaction
        )
        self.i2c_transaction_lab.diagnostic_requested.connect(
            self._start_i2c_diagnostic
        )
        lab_root.addWidget(self.i2c_transaction_lab)

        self.i2c_device_inspector = I2cDeviceInspector()
        self.i2c_device_inspector.register_read_requested.connect(
            lambda request: self._start_i2c_inspector_transaction("read", request)
        )
        self.i2c_device_inspector.register_write_requested.connect(
            lambda request: self._start_i2c_inspector_transaction("write", request)
        )
        self.i2c_device_inspector.memory_read_requested.connect(
            lambda request: self._start_i2c_memory_operation("read", request)
        )
        self.i2c_device_inspector.memory_write_requested.connect(
            lambda request: self._start_i2c_memory_operation("write", request)
        )
        read_write_root.addWidget(self.i2c_device_inspector)

        display_box = QGroupBox("SSD1306 quick test")
        display = QGridLayout(display_box)
        display.addWidget(QLabel("Address:"), 0, 0)
        self.i2c_display_address = QComboBox()
        self.i2c_display_address.setEditable(True)
        self.i2c_display_address.setCurrentText("0x3C")
        display.addWidget(self.i2c_display_address, 0, 1)
        display.addWidget(QLabel("Controller:"), 0, 2)
        self.i2c_display_controller = QComboBox()
        self.i2c_display_controller.addItem("SSD1306")
        self.i2c_display_controller.addItem("Custom / Unknown")
        display.addWidget(self.i2c_display_controller, 0, 3)
        display.addWidget(QLabel("Resolution:"), 0, 4)
        self.i2c_display_resolution = QComboBox()
        self.i2c_display_resolution.addItem("128 × 64", (128, 64))
        self.i2c_display_resolution.addItem("128 × 32", (128, 32))
        display.addWidget(self.i2c_display_resolution, 0, 5)

        display_actions = (
            ("Initialize", "initialize"), ("Clear", "clear"),
            ("All pixels", "all_on"), ("Border", "border"),
            ("Grid", "grid"), ("Bars", "bars"),
            ("Invert", "invert"), ("Normal", "normal"),
            ("Display ON", "display_on"), ("Display OFF", "display_off"),
        )
        self.i2c_display_buttons = []
        for index, (label, action) in enumerate(display_actions):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, selected=action: self._start_i2c_display_test(selected)
            )
            display.addWidget(button, 1 + index // 5, index % 5)
            self.i2c_display_buttons.append(button)
        self.i2c_display_status = QLabel(
            "Select an address, initialize the display, then try a test pattern."
        )
        self.i2c_display_status.setWordWrap(True)
        display.addWidget(self.i2c_display_status, 3, 0, 1, 6)
        warning = QLabel(
            "Use only with SSD1306-compatible displays. A wrong controller preset "
            "may produce no image or unexpected commands."
        )
        warning.setWordWrap(True)
        warning.setProperty("role", "warning")
        display.addWidget(warning, 4, 0, 1, 6)
        display.addWidget(QLabel("Text:"), 5, 0)
        self.i2c_display_text = QLineEdit("Hello I2C")
        display.addWidget(self.i2c_display_text, 5, 1, 1, 2)
        display.addWidget(QLabel("Font:"), 5, 3)
        self.i2c_display_font_size = QSpinBox()
        self.i2c_display_font_size.setRange(6, 48)
        self.i2c_display_font_size.setValue(14)
        display.addWidget(self.i2c_display_font_size, 5, 4)
        preview_text = QPushButton("Preview text")
        preview_text.clicked.connect(self._preview_i2c_display_text)
        display.addWidget(preview_text, 5, 5)
        load_image = QPushButton("Load image")
        load_image.clicked.connect(self._load_i2c_display_image)
        display.addWidget(load_image, 6, 0)
        display.addWidget(QLabel("Brightness:"), 6, 1)
        self.i2c_image_threshold = QSpinBox()
        self.i2c_image_threshold.setRange(0, 255)
        self.i2c_image_threshold.setValue(128)
        display.addWidget(self.i2c_image_threshold, 6, 2)
        self.i2c_image_invert = QCheckBox("Invert pixels")
        display.addWidget(self.i2c_image_invert, 6, 3)
        self.i2c_image_auto_background = QCheckBox("Auto dark background")
        self.i2c_image_auto_background.setChecked(True)
        display.addWidget(self.i2c_image_auto_background, 6, 4)
        send_canvas = QPushButton("Send preview")
        send_canvas.clicked.connect(self._send_i2c_display_canvas)
        display.addWidget(send_canvas, 6, 5)
        example_text = QPushButton("Example text")
        example_text.clicked.connect(self._load_i2c_example_text)
        display.addWidget(example_text, 7, 0, 1, 2)
        example_image = QPushButton("Example image")
        example_image.clicked.connect(self._load_i2c_example_image)
        display.addWidget(example_image, 7, 2, 1, 2)
        example_hint = QLabel("Built-in examples: preview them, then press Send preview.")
        display.addWidget(example_hint, 7, 4, 1, 2)
        display.addWidget(QLabel("Conversion:"), 8, 0)
        self.i2c_image_conversion = QComboBox()
        self.i2c_image_conversion.addItems([
            "Floyd-Steinberg (best detail)", "Threshold (sharp)"
        ])
        display.addWidget(self.i2c_image_conversion, 8, 1, 1, 2)
        display.addWidget(QLabel("Scaling:"), 8, 3)
        self.i2c_image_scaling = QComboBox()
        self.i2c_image_scaling.addItems([
            "Stretch to 128×64 (whole image)",
            "Fit whole image (keep proportions)",
            "Fill / crop (detail)",
        ])
        display.addWidget(self.i2c_image_scaling, 8, 4, 1, 2)
        display.addWidget(QLabel("Orientation:"), 9, 0)
        self.i2c_display_orientation = QComboBox()
        self.i2c_display_orientation.addItem("Horizontal (128×64)", "horizontal")
        self.i2c_display_orientation.addItem(
            "Vertical clockwise (64×128)", "clockwise"
        )
        self.i2c_display_orientation.addItem(
            "Vertical counter-clockwise (64×128)", "counter_clockwise"
        )
        display.addWidget(self.i2c_display_orientation, 9, 1, 1, 3)
        orientation_hint = QLabel("Vertical modes are for a physically rotated display.")
        display.addWidget(orientation_hint, 9, 4, 1, 2)
        self.i2c_display_preview = QLabel("No preview")
        self.i2c_display_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.i2c_display_preview.setMinimumSize(256, 128)
        self.i2c_display_preview.setStyleSheet("background:#000; color:#888; border:1px solid #555;")
        display.addWidget(self.i2c_display_preview, 10, 0, 1, 6)
        self._i2c_loaded_image_path = None
        self._i2c_source_image = None
        self._i2c_source_light_background = None
        self._i2c_source_is_binary = False
        self._i2c_canvas_image = None
        self._i2c_preview_kind = None
        self.i2c_image_threshold.valueChanged.connect(self._image_conversion_controls_changed)
        self.i2c_image_invert.toggled.connect(self._refresh_i2c_binary_preview)
        self.i2c_image_auto_background.toggled.connect(self._image_conversion_controls_changed)
        self.i2c_image_conversion.currentTextChanged.connect(self._image_conversion_controls_changed)
        self.i2c_image_scaling.currentTextChanged.connect(self._rebuild_i2c_loaded_image)
        self.i2c_display_orientation.currentIndexChanged.connect(
            self._image_orientation_changed
        )
        display_root.addWidget(display_box)
        display_root.addStretch()

        trace_config = QHBoxLayout()
        trace_config.addWidget(QLabel("Address:"))
        self.i2c_sequence_address = QComboBox()
        self.i2c_sequence_address.setEditable(True)
        self.i2c_sequence_address.setCurrentText("0x3C")
        trace_config.addWidget(self.i2c_sequence_address)
        trace_config.addWidget(QLabel("Command prefix:"))
        self.i2c_command_prefix = QLineEdit("00")
        self.i2c_command_prefix.setFixedWidth(70)
        trace_config.addWidget(self.i2c_command_prefix)
        trace_config.addWidget(QLabel("Data prefix:"))
        self.i2c_data_prefix = QLineEdit("40")
        self.i2c_data_prefix.setFixedWidth(70)
        trace_config.addWidget(self.i2c_data_prefix)
        trace_config.addWidget(QLabel("Use Raw for no prefix"))
        trace_config.addStretch()
        trace_root.addLayout(trace_config)

        trace_toolbar = QHBoxLayout()
        load_trace = QPushButton("Load SSD1306 preset")
        load_trace.clicked.connect(self._load_ssd1306_trace)
        add_trace = QPushButton("Add step")
        add_trace.clicked.connect(self._add_i2c_trace_step)
        remove_trace = QPushButton("Remove")
        remove_trace.clicked.connect(self._remove_i2c_trace_step)
        move_up = QPushButton("↑")
        move_up.clicked.connect(lambda: self._move_i2c_trace_step(-1))
        move_down = QPushButton("↓")
        move_down.clicked.connect(lambda: self._move_i2c_trace_step(1))
        run_step = QPushButton("Run selected step")
        run_step.clicked.connect(self._run_i2c_trace_step)
        self.i2c_run_sequence_btn = QPushButton("Run all")
        self.i2c_run_sequence_btn.clicked.connect(self._toggle_i2c_sequence)
        export_json = QPushButton("Export JSON")
        export_json.clicked.connect(lambda: self._export_i2c_trace("json"))
        export_c = QPushButton("Export C array")
        export_c.clicked.connect(lambda: self._export_i2c_trace("c"))
        trace_toolbar.addWidget(load_trace)
        trace_toolbar.addWidget(add_trace)
        trace_toolbar.addWidget(remove_trace)
        trace_toolbar.addWidget(move_up)
        trace_toolbar.addWidget(move_down)
        trace_toolbar.addWidget(run_step)
        trace_toolbar.addWidget(self.i2c_run_sequence_btn)
        trace_toolbar.addWidget(export_json)
        trace_toolbar.addWidget(export_c)
        trace_toolbar.addStretch()
        trace_root.addLayout(trace_toolbar)
        profile_toolbar = QHBoxLayout()
        self.i2c_profile_tabs = QTabBar()
        self.i2c_profile_tabs.setTabsClosable(True)
        self.i2c_profile_tabs.setMovable(False)
        self.i2c_profile_tabs.currentChanged.connect(self._switch_i2c_profile)
        self.i2c_profile_tabs.tabCloseRequested.connect(self._close_i2c_profile)
        profile_toolbar.addWidget(self.i2c_profile_tabs, stretch=1)
        new_profile = QPushButton("New profile")
        new_profile.clicked.connect(self._new_i2c_profile)
        duplicate_profile = QPushButton("Duplicate")
        duplicate_profile.clicked.connect(self._duplicate_i2c_profile)
        rename_profile = QPushButton("Rename")
        rename_profile.clicked.connect(self._rename_i2c_profile)
        save_profile = QPushButton("Save profile")
        save_profile.clicked.connect(self._save_i2c_profile)
        open_profile = QPushButton("Open profile")
        open_profile.clicked.connect(self._open_i2c_profile)
        for button in (new_profile, duplicate_profile, rename_profile,
                       save_profile, open_profile):
            profile_toolbar.addWidget(button)
        trace_root.addLayout(profile_toolbar)
        self.i2c_trace_table = QTableWidget(0, 5)
        self.i2c_trace_table.setHorizontalHeaderLabels(
            ["Step", "Action", "Type", "Bytes / delay ms", "Notes"]
        )
        trace_header = self.i2c_trace_table.horizontalHeader()
        trace_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        trace_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        trace_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        trace_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        trace_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.i2c_trace_table.setColumnWidth(3, 180)
        self.i2c_trace_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.i2c_trace_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        trace_root.addWidget(self.i2c_trace_table, stretch=1)
        self.i2c_trace_status = QLabel(
            "Build a sequence from the display datasheet, or load the SSD1306 preset. "
            "Types: Command, Data, Raw, Delay."
        )
        self.i2c_trace_status.setWordWrap(True)
        trace_root.addWidget(self.i2c_trace_status)
        self._i2c_profiles = []
        self._i2c_active_profile = -1
        self._i2c_profile_switching = False
        self._new_i2c_profile("SSD1306 Example", load_preset=True)
        self._reset_i2c_matrix()
        self._refresh_i2c_devices()
        self.i2c_device_combo.currentIndexChanged.connect(self._clear_i2c_scanned_addresses)
        self.i2c_channel_combo.currentIndexChanged.connect(self._clear_i2c_scanned_addresses)
        return tab

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
        port_label = lbl("Port:")
        port_label.setToolTip(tooltips["port"])
        grid.addWidget(port_label, r, 0)
        self.port_combo = combo([], 110)
        self.port_combo.setToolTip(tooltips["port"])
        grid.addWidget(self.port_combo, r, 1)
        btn_refresh = QPushButton("Refresh"); btn_refresh.setMinimumWidth(68)
        btn_refresh.setToolTip("Refresh available ports")
        btn_refresh.clicked.connect(self._refresh_ports)
        grid.addWidget(btn_refresh, r, 2)

        baud_label = lbl("Baud:")
        baud_label.setToolTip(tooltips["baud"])
        grid.addWidget(baud_label, r, 3)
        self.baud_combo = combo(BAUD_RATES, 100)
        self.baud_combo.setToolTip(tooltips["baud"])
        grid.addWidget(self.baud_combo, r, 4)

        data_label = lbl("Data:")
        data_label.setToolTip(tooltips["data"])
        grid.addWidget(data_label, r, 5)
        self.databits_combo = combo(DATA_BITS, 55)
        self.databits_combo.setToolTip(tooltips["data"])
        grid.addWidget(self.databits_combo, r, 6)

        parity_label = lbl("Parity:")
        parity_label.setToolTip(tooltips["parity"])
        grid.addWidget(parity_label, r, 7)
        self.parity_combo = combo(PARITIES, 80)
        self.parity_combo.setToolTip(tooltips["parity"])
        grid.addWidget(self.parity_combo, r, 8)

        stop_label = lbl("Stop:")
        stop_label.setToolTip(tooltips["stop"])
        grid.addWidget(stop_label, r, 9)
        self.stopbits_combo = combo(STOP_BITS, 55)
        self.stopbits_combo.setToolTip(tooltips["stop"])
        grid.addWidget(self.stopbits_combo, r, 10)

        flow_label = lbl("Flow:")
        flow_label.setToolTip(tooltips["flow"])
        grid.addWidget(flow_label, r, 11)
        self.flow_combo = combo(FLOW_CTRL, 90)
        self.flow_combo.setToolTip(tooltips["flow"])
        grid.addWidget(self.flow_combo, r, 12)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(100)
        set_role(self.connect_btn, "primary")
        self.connect_btn.setToolTip("Establish or close serial connection")
        self.connect_btn.clicked.connect(self._toggle_connection)
        grid.addWidget(self.connect_btn, r, 13, 1, 2)

        # Row 1 - EOL, Display options, and Colors
        r = 1
        eol_tx_label = lbl("EOL TX:")
        eol_tx_label.setToolTip(tooltips["eol_tx"])
        grid.addWidget(eol_tx_label, r, 0)
        self.eol_tx_combo = combo(EOL_OPT, 80)
        self.eol_tx_combo.setToolTip(tooltips["eol_tx"])
        grid.addWidget(self.eol_tx_combo, r, 1)

        eol_rx_label = lbl("EOL RX:")
        eol_rx_label.setToolTip(tooltips["eol_rx"])
        grid.addWidget(eol_rx_label, r, 3)
        self.eol_rx_combo = combo(EOL_OPT, 80)
        self.eol_rx_combo.setToolTip(tooltips["eol_rx"])
        grid.addWidget(self.eol_rx_combo, r, 4)

        show_label = lbl("Display:")
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

        colors_label = lbl("Colors:")
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
        self.theme_btn = QPushButton("Light theme")
        self.theme_btn.setMinimumWidth(104)
        self.theme_btn.setToolTip("Toggle between light and dark theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        grid.addWidget(self.theme_btn, r, 13)

        return box

    # ── Sequence panel ────────────────────────────────────────────────────────
    def _build_uart_tools_panel(self):
        self.uart_tools = UartToolsPanel(
            can_start_loopback=self._can_start_uart_loopback,
            status_callback=lambda message: self.statusBar().showMessage(
                message, 6000
            ),
            parent=self,
        )
        self.flow_combo.currentTextChanged.connect(
            self.uart_tools.set_flow_control
        )
        return self.uart_tools

    def _can_start_uart_loopback(self):
        if self._auto_timer.isActive():
            return False, "Stop Auto-send before running loopback."
        if self._sequence_running:
            return False, "Stop Command Sequence before running loopback."
        return True, ""

    def _process_uart_loopback_rx(self, data):
        if hasattr(self, "uart_tools"):
            self.uart_tools.feed_raw_data(data)

    def _build_sequence_panel(self):
        box = QGroupBox("Command Sequence")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(4)
        box.setMinimumWidth(320)
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        
        # Command list table
        self.seq_table = QTableWidget()
        self.seq_table.setColumnCount(6)
        self.seq_table.setHorizontalHeaderLabels(["", "Command", "Fmt", "▶", "↑↓", "✕"])
        header = self.seq_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(28)
        self.seq_table.setColumnWidth(0, 30)
        self.seq_table.setColumnWidth(1, 220)
        self.seq_table.setColumnWidth(2, 70)
        self.seq_table.setColumnWidth(3, 32)
        self.seq_table.setColumnWidth(4, 60)
        self.seq_table.setColumnWidth(5, 35)
        self.seq_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.seq_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.seq_table.verticalHeader().setVisible(False)
        self.seq_table.horizontalHeader().setSectionsMovable(False)
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
        btn_export = QPushButton("Export")
        btn_export.clicked.connect(self._export_sequence)
        btn_import = QPushButton("Import")
        btn_import.clicked.connect(self._import_sequence)
        export_layout.addWidget(btn_export)
        export_layout.addWidget(btn_import)
        vbox.addLayout(export_layout)
        
        # Start/Stop button
        self.seq_start_btn = QPushButton("Start Sequence")
        set_role(self.seq_start_btn, "primary")
        self.seq_start_btn.clicked.connect(self._toggle_sequence)
        vbox.addWidget(self.seq_start_btn)

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
        search_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type text to find...")
        self.search_edit.setClearButtonEnabled(True)
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
        
        # Alert management
        alert_layout = QHBoxLayout()
        alert_layout.addWidget(QLabel("Alerts:"))
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

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedWidth(70)
        self.send_btn.clicked.connect(self._send_data)
        grid.addWidget(self.send_btn, 0, 6)

        grid.addWidget(QLabel("History:"), 0, 7)
        self.history_combo = QComboBox(); self.history_combo.setFixedWidth(200)
        self.history_combo.currentTextChanged.connect(self.send_edit.setText)
        grid.addWidget(self.history_combo, 0, 8)

        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("Will send (HEX):"), 1, 0)
        self.send_preview = QLineEdit()
        self.send_preview.setReadOnly(True)
        self.send_preview.setPlaceholderText("Enter data to see the exact bytes")
        self.send_preview.setToolTip(
            "Exact bytes that will be transmitted, including EOL TX."
        )
        grid.addWidget(self.send_preview, 1, 1, 1, 8)

        # Row 2 — auto send
        grid.addWidget(QLabel("Auto-send interval (s):"), 2, 0, 1, 2)
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 3600); self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(1.0); self.interval_spin.setFixedWidth(80)
        grid.addWidget(self.interval_spin, 2, 2)

        self.auto_btn = QPushButton("Start Auto"); self.auto_btn.setFixedWidth(100)
        set_role(self.auto_btn, "primary")
        self.auto_btn.clicked.connect(self._toggle_auto_send)
        grid.addWidget(self.auto_btn, 2, 3)

        self._hex_send_validator = HexByteValidator(self.send_edit)
        self.send_edit.textChanged.connect(self._update_send_preview)
        self.send_fmt.currentTextChanged.connect(self._send_format_changed)
        self.eol_tx_combo.currentTextChanged.connect(self._update_send_preview)
        self._send_format_changed()

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
        self._set_combo_data(self.port_combo, self.config.get("port", ""))
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
        self.uart_tools.load_config(self.config)
        self._set_combo(self.send_fmt, self.config.get("send_format", "ASCII"))
        self.interval_spin.setValue(float(self.config.get("auto_send_interval", 1.0)))
        self._update_history_combo()
        self.seq_interval_spin.setValue(float(self.config.get("sequence_interval", 1.0)))
        self._set_combo(self.seq_mode_combo, self.config.get("sequence_mode", "Stop"))
        self._load_sequence_commands()
        self.seq_table.setColumnWidth(
            1, max(120, min(1000, int(
                self.config.get("sequence_command_col_width", 220)
            )))
        )
        self._alerts = self.config.get("alerts", [])
        if self.config.get("theme", "dark") == "light":
            self._apply_light_theme()
        else:
            self._apply_dark_theme()
        self._apply_usb_bridge_workspace_modes(show_error=False)

    def _collect_config(self):
        self.config.set("port", self.port_combo.currentData() or "")
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
        self.uart_tools.collect_config(self.config)
        if self.active_bridge is not None:
            all_modes = dict(self.config.get("usb_bridge_modes", {}))
            all_modes[self.active_bridge.key] = {
                channel: combo.currentText()
                for channel, combo in self.usb_bridge_mode_combos.items()
            }
            self.config.set("usb_bridge_modes", all_modes)
        if hasattr(self, "usb_bridge_uart_sessions"):
            for session in self.usb_bridge_uart_sessions.values():
                session._collect_config()
            for session in self.usb_bridge_i2c_sessions.values():
                session._collect_config()
            for session in self.usb_bridge_spi_sessions.values():
                session._collect_config()
            for session in self.usb_bridge_gpio_sessions.values():
                session.config.set("gpio", session.settings_dict())
        self.config.set("sequence_interval", self.seq_interval_spin.value())
        self.config.set("sequence_mode", self.seq_mode_combo.currentText())
        self.config.set("sequence_command_col_width", self.seq_table.columnWidth(1))
        sizes = self.main_splitter.sizes()
        if sizes:
            self.config.set("sequence_panel_width", sizes[0])
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

    @staticmethod
    def _general_console_should_be_visible(has_protocol_bridge):
        """Show the generic console only when no protocol bridge is managed."""
        return not has_protocol_bridge

    def _update_console_tab_visibility(self):
        """Expose one unambiguous workspace for the detected hardware.

        A supported bridge owns its UART interfaces and belongs in USB Bridge.
        Without one, the generic console remains available for ordinary serial
        adapters and the empty bridge workspace stays out of the way.
        """
        if not hasattr(self, "main_tabs"):
            return
        has_protocol_bridge = bool(self.usb_bridge_adapters)
        general_visible = self._general_console_should_be_visible(
            has_protocol_bridge
        )
        self.main_tabs.setTabVisible(0, general_visible)
        self.main_tabs.setTabVisible(1, has_protocol_bridge)
        if general_visible:
            self.main_tabs.setTabToolTip(
                0,
                "Serial console for COM, ttyUSB, ttyACM, and USB-UART devices.",
            )
            self.main_tabs.setCurrentIndex(0)
        else:
            # The detected bridge owns its UART interfaces, so presenting the
            # same hardware again as General would be ambiguous.
            self.main_tabs.setCurrentIndex(1)

    def _refresh_ports(self):
        """List ordinary serial ports while reserving known USB bridges."""
        current = self.port_combo.currentData()
        self.port_combo.clear()
        # If PyFtdi/libusb is unavailable, do not hide usable FTDI VCP ports
        # from the ordinary serial console.
        reserve_detected_bridges = bool(self.usb_bridge_adapters)
        general_ports = list(list_port_details(
            include_usb_bridges=not reserve_detected_bridges
        ))
        for label, device in general_ports:
            self.port_combo.addItem(label, device)
        index = self.port_combo.findData(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        self._update_console_tab_visibility()

    def _usb_bridge_modes_changed(self):
        if hasattr(self, "port_combo"):
            self._refresh_ports()
        if hasattr(self, "i2c_channel_combo"):
            if self.i2c_worker and self.i2c_worker.is_alive():
                self.i2c_worker.stop()
            self._refresh_i2c_channels()
        self._apply_usb_bridge_workspace_modes()

    def _usb_bridge_adapter_changed(self):
        if hasattr(self, "usb_bridge_channel_tabs"):
            self._rebuild_usb_bridge_workspace()
            self._refresh_ports()

    def _refresh_usb_bridges(self, manual=False):
        """Request bridge discovery without blocking the Qt event loop."""
        if not self._manages_usb_bridges or self._closing:
            return
        if self._bridge_refresh_running:
            if manual:
                self.statusBar().showMessage("Adapter detection is already running.", 2000)
            return

        self._bridge_refresh_running = True
        self._bridge_refresh_was_manual = bool(manual)
        self.usb_bridge_refresh_btn.setEnabled(False)
        if manual:
            self.statusBar().showMessage("Detecting USB protocol bridges…")

        completion_signal = self._signals.usb_bridges_discovered

        def discover_in_background():
            try:
                bridges = discover_usb_bridges()
                error = ""
            except Exception as exc:
                bridges = []
                error = str(exc)
            completion_signal.emit(bridges, error)

        threading.Thread(
            target=discover_in_background,
            name="usb-bridge-discovery",
            daemon=True,
        ).start()

    @staticmethod
    def _bridge_inventory_signature(bridges):
        """Return the hardware details that require rebuilding the workspace."""
        return tuple(
            (
                bridge.key,
                bridge.base_url,
                tuple(
                    (interface.name, tuple(sorted(interface.capabilities)))
                    for interface in bridge.interfaces
                ),
            )
            for bridge in bridges
        )

    def _usb_bridge_discovery_finished(self, bridges, error):
        """Apply a completed discovery result in the Qt GUI thread."""
        self._bridge_refresh_running = False
        if self._closing:
            return
        self.usb_bridge_refresh_btn.setEnabled(True)
        was_manual = self._bridge_refresh_was_manual
        self._bridge_refresh_was_manual = False

        if error:
            self.usb_bridge_detection_error = error
            # A transient libusb failure must not destroy working sessions.
            # With no prior inventory, keep General available and expose the
            # failure in the selector so it can be diagnosed.
            if not self.usb_bridge_adapters:
                self.usb_bridge_combo.blockSignals(True)
                self.usb_bridge_combo.clear()
                self.usb_bridge_combo.addItem(f"Detection error: {error}", None)
                self.usb_bridge_combo.blockSignals(False)
                self._update_console_tab_visibility()
            if was_manual:
                self.statusBar().showMessage(
                    f"USB bridge detection failed: {error}", 6000
                )
            return

        self.usb_bridge_detection_error = ""
        if self._bridge_inventory_signature(
            bridges
        ) == self._bridge_inventory_signature(self.usb_bridge_adapters):
            if not bridges:
                self.usb_bridge_combo.blockSignals(True)
                self.usb_bridge_combo.clear()
                self.usb_bridge_combo.addItem(
                    "No supported adapter detected", None
                )
                self.usb_bridge_combo.blockSignals(False)
                self._update_console_tab_visibility()
            if was_manual:
                self.statusBar().showMessage("USB adapter list is already current.", 2500)
            return

        previous_models = [bridge.model for bridge in self.usb_bridge_adapters]
        current_key = self.active_bridge.key if self.active_bridge else ""
        self.usb_bridge_adapters = list(bridges)
        self.usb_bridge_combo.blockSignals(True)
        self.usb_bridge_combo.clear()
        for bridge in bridges:
            self.usb_bridge_combo.addItem(bridge.label, bridge)
        if not bridges:
            self.usb_bridge_combo.addItem("No supported adapter detected", None)
        selected = next(
            (index for index, bridge in enumerate(bridges) if bridge.key == current_key),
            0,
        )
        self.usb_bridge_combo.setCurrentIndex(selected)
        self.usb_bridge_combo.blockSignals(False)
        self._rebuild_usb_bridge_workspace()
        self._refresh_ports()

        current_models = [bridge.model for bridge in bridges]
        if current_models:
            message = f"USB adapter detected: {', '.join(current_models)}"
        elif previous_models:
            message = "USB protocol bridge disconnected. General console enabled."
        else:
            message = "No supported USB protocol bridge detected."
        self.statusBar().showMessage(message, 4000)

    def _refresh_i2c_channels(self):
        current = self.i2c_channel_combo.currentData()
        self.i2c_channel_combo.clear()
        bridge = getattr(self, "active_bridge", None)
        for interface in bridge.interfaces if bridge else ():
            combo = self.usb_bridge_mode_combos.get(interface.name)
            if combo and combo.currentText() == I2C:
                self.i2c_channel_combo.addItem(
                    f"Interface {interface.name}", interface.index
                )
        index = self.i2c_channel_combo.findData(current)
        if index >= 0:
            self.i2c_channel_combo.setCurrentIndex(index)

    # ──────────────────────────────────────────────────────────────────────────
    # USB bridge I2C tools
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_i2c_devices(self):
        current = self.i2c_device_combo.currentData()
        self.i2c_device_combo.clear()
        try:
            bound = getattr(self, "bound_bridge", None)
            devices = (
                [(bound.label, bound.base_url)] if bound is not None
                else list_i2c_bridge_devices()
            )
        except Exception as exc:
            self.i2c_device_combo.addItem(f"USB detection error: {exc}", None)
            return
        for label, url in devices:
            self.i2c_device_combo.addItem(label, url)
        if not devices:
            self.i2c_device_combo.addItem("No I²C-capable USB bridge detected", None)
        else:
            index = self.i2c_device_combo.findData(current)
            if index >= 0:
                self.i2c_device_combo.setCurrentIndex(index)

    def _i2c_url(self):
        base = self.i2c_device_combo.currentData()
        return f"{base}/{self.i2c_channel_combo.currentData()}"

    def _i2c_bus_settings(self):
        """Validate the editable clock and return settings shared by all tools."""
        preset = self.i2c_frequency_combo.currentData()
        if preset is not None:
            frequency = int(preset)
        else:
            text = self.i2c_frequency_combo.currentText().strip().lower()
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(mhz|khz|hz)?", text)
            if not match:
                raise ValueError(
                    "Clock must look like 100 kHz, 1 MHz, or 100000 Hz."
                )
            value = float(match.group(1))
            unit = match.group(2)
            if unit == "mhz":
                frequency = round(value * 1_000_000)
            elif unit == "khz" or (unit is None and value <= 3400):
                frequency = round(value * 1_000)
            else:
                frequency = round(value)
        return I2cBusSettings(
            frequency=frequency,
            clock_stretching=self.i2c_clock_stretching.isChecked(),
            retry_count=self.i2c_retry_count.value(),
        )

    def _reset_i2c_matrix(self):
        for address in range(0x80):
            row, column = divmod(address, 16)
            item = QTableWidgetItem("" if address < 0x03 or address > 0x77 else "--")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if address < 0x03 or address > 0x77:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setBackground(QColor("#303030"))
            else:
                item.setForeground(QColor("#888888"))
            self.i2c_matrix.setItem(row, column, item)

    def _clear_i2c_scanned_addresses(self):
        if hasattr(self, "i2c_device_inspector"):
            self.i2c_device_inspector.set_addresses([])
        if hasattr(self, "i2c_transaction_lab"):
            self.i2c_transaction_lab.set_addresses([])
        if hasattr(self, "i2c_display_address"):
            current_display = self.i2c_display_address.currentText()
            self.i2c_display_address.clear()
            self.i2c_display_address.setCurrentText(current_display or "0x3C")
        if hasattr(self, "i2c_sequence_address"):
            current_sequence = self.i2c_sequence_address.currentText()
            self.i2c_sequence_address.clear()
            self.i2c_sequence_address.setCurrentText(current_sequence or "0x3C")

    def _i2c_matrix_address_clicked(self, row, column):
        address = row * 16 + column
        item = self.i2c_matrix.item(row, column)
        if item and item.text() == f"{address:02X}":
            self.i2c_device_inspector.select_address(address)
            self.i2c_transaction_lab.select_address(address)
            self.i2c_tools_tabs.setCurrentIndex(1)

    def _toggle_i2c_scan(self):
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_worker.stop()
            self.i2c_scan_btn.setEnabled(False)
            self.i2c_scan_btn.setText("Stopping…")
            return
        if not self.i2c_device_combo.currentData():
            QMessageBox.warning(self, "I²C", "No I²C-capable USB bridge is available.")
            return
        if self.i2c_channel_combo.currentData() is None:
            QMessageBox.warning(self, "I²C", "Assign channel A or B to I2C first.")
            return
        url = self._i2c_url()
        try:
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "I²C clock", str(exc))
            return
        self.i2c_device_inspector.pause_polling()
        self.i2c_device_inspector.setEnabled(False)
        self._reset_i2c_matrix()
        self.i2c_summary.setText(
            f"Scanning {url} at {settings.frequency / 1000:g} kHz…"
        )
        self.i2c_progress_bar.setValue(0)
        self.i2c_scan_btn.setText("Stop scan")
        self.i2c_worker = I2cScanWorker(
            url, settings,
            lambda address: self._signals.i2c_found.emit(address),
            lambda current, total: self._signals.i2c_progress.emit(current, total),
            lambda found, stopped, actual: self._signals.i2c_done.emit(found, stopped, actual),
            lambda error: self._signals.i2c_error.emit(error),
        )
        self.i2c_worker.start()

    def _i2c_device_found(self, address):
        row, column = divmod(address, 16)
        item = self.i2c_matrix.item(row, column)
        item.setText(f"{address:02X}")
        item.setForeground(QColor("#ffffff"))
        item.setBackground(QColor("#2E8B57"))
        item.setFont(QFont("Courier New", 10, QFont.Weight.Bold))

    def _i2c_scan_progress(self, current, total):
        self.i2c_progress_bar.setMaximum(total)
        self.i2c_progress_bar.setValue(current)

    def _i2c_scan_done(self, found, stopped, actual_frequency):
        state = "Scan stopped" if stopped else "Scan complete"
        addresses = ", ".join(f"0x{address:02X}" for address in found) or "none"
        self.i2c_summary.setText(
            f"{state}. Found {len(found)} device(s): {addresses}. "
            f"Actual clock: {actual_frequency / 1000:g} kHz."
        )
        self.i2c_device_inspector.set_addresses(found)
        self.i2c_transaction_lab.set_addresses(found)
        self.i2c_display_address.clear()
        self.i2c_display_address.addItems([f"0x{address:02X}" for address in found])
        self.i2c_sequence_address.clear()
        self.i2c_sequence_address.addItems([f"0x{address:02X}" for address in found])
        display_default = "0x3C"
        found_text = [f"0x{address:02X}" for address in found]
        if display_default in found_text:
            self.i2c_display_address.setCurrentText(display_default)
        elif found_text:
            self.i2c_display_address.setCurrentIndex(0)
        else:
            self.i2c_display_address.setCurrentText(display_default)
        if display_default in found_text:
            self.i2c_sequence_address.setCurrentText(display_default)
        elif found_text:
            self.i2c_sequence_address.setCurrentIndex(0)
        else:
            self.i2c_sequence_address.setCurrentText(display_default)
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_scan_btn.setText("Scan I²C bus")
        self.i2c_device_inspector.setEnabled(True)

    def _i2c_scan_error(self, error):
        self.i2c_summary.setText(f"ERROR: {error}")
        if hasattr(self, "i2c_device_inspector"):
            self.i2c_device_inspector.handle_error(error)
            self.i2c_device_inspector.setEnabled(True)
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_scan_btn.setText("Scan I²C bus")
        if hasattr(self, "i2c_display_buttons"):
            for button in self.i2c_display_buttons:
                button.setEnabled(True)
            self.i2c_display_status.setText(f"ERROR: {error}")
        if hasattr(self, "i2c_trace_status"):
            self.i2c_trace_status.setText(f"ERROR: {error}")
        if hasattr(self, "i2c_run_sequence_btn"):
            self.i2c_run_sequence_btn.setEnabled(True)
            self.i2c_run_sequence_btn.setText("Run all")
        QMessageBox.critical(self, "USB Bridge I²C error", error)

    @staticmethod
    def _parse_i2c_number(text, name):
        try:
            return int(text.strip(), 0)
        except ValueError as exc:
            raise ValueError(f"{name} must be decimal or hexadecimal (0x...).") from exc

    def _start_i2c_lab_transaction(self, request):
        """Run one Raw-I2C or SMBus request from Transaction Lab."""
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_transaction_lab.handle_error({
                **request, "status": "BUSY",
                "error": "Wait for the current I²C operation to finish.",
            })
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            self.i2c_transaction_lab.handle_error({
                **request, "status": "NO ADAPTER",
                "error": "Select an I²C-capable adapter interface first.",
            })
            return
        try:
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            self.i2c_transaction_lab.handle_error({
                **request, "status": "INVALID", "error": str(exc),
            })
            return
        self.i2c_device_inspector.pause_polling()
        self.i2c_scan_btn.setEnabled(False)
        self.i2c_worker = I2cLabWorker(
            self._i2c_url(), settings, request,
            lambda result: self._signals.i2c_lab_done.emit(result),
            lambda error: self._signals.i2c_lab_error.emit(error),
        )
        self.i2c_worker.start()

    def _i2c_lab_done(self, result):
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_transaction_lab.handle_result(result)

    def _i2c_lab_error(self, result):
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_transaction_lab.handle_error(result)

    def _start_i2c_diagnostic(self, action):
        """Check or recover the selected physical I2C lines."""
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_transaction_lab.handle_diagnostic({
                "action": action, "status": "BUSY",
                "error": "Wait for the current I²C operation to finish.",
            })
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            self.i2c_transaction_lab.handle_diagnostic({
                "action": action, "status": "NO ADAPTER",
                "error": "Select an I²C-capable adapter interface first.",
            })
            return
        self.i2c_transaction_lab.set_busy(True)
        self.i2c_device_inspector.pause_polling()
        self.i2c_scan_btn.setEnabled(False)
        self.i2c_worker = I2cBusDiagnosticWorker(
            self._i2c_url(), action,
            lambda result: self._signals.i2c_diagnostic_done.emit(result),
            lambda error: self._signals.i2c_diagnostic_done.emit(error),
        )
        self.i2c_worker.start()

    def _i2c_diagnostic_done(self, result):
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_transaction_lab.handle_diagnostic(result)

    def _start_i2c_inspector_transaction(self, operation, request):
        """Start one generic register transaction requested by the inspector."""
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_device_inspector.handle_operation_error(
                "Wait for the current I²C operation to finish.", request
            )
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            self.i2c_device_inspector.handle_operation_error(
                "Select an I²C-capable adapter interface first.",
                request,
            )
            return
        self.i2c_scan_btn.setEnabled(False)
        try:
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            self.i2c_device_inspector.handle_operation_error(str(exc), request)
            self.i2c_scan_btn.setEnabled(True)
            return
        self.i2c_worker = I2cTransactionWorker(
            self._i2c_url(), settings,
            operation, request["address"], request["register"],
            request["register_width"], request["big_endian"],
            request.get("payload", b""), request["length"],
            lambda action, data: self._signals.i2c_transaction_done.emit(
                action, data, request
            ),
            lambda error: self._signals.i2c_inspector_error.emit(error, request),
        )
        self.i2c_worker.start()

    def _i2c_transaction_done(self, operation, data, request):
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_device_inspector.handle_register_result(operation, data, request)

    def _start_i2c_memory_operation(self, operation, request):
        """Start a chunked memory read or a page-aware write with verification."""
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_device_inspector.handle_operation_error(
                "Wait for the current I²C operation to finish.", request
            )
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            self.i2c_device_inspector.handle_operation_error(
                "Select an I²C-capable adapter interface first.",
                request,
            )
            return
        self.i2c_scan_btn.setEnabled(False)
        try:
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            self.i2c_device_inspector.handle_operation_error(str(exc), request)
            self.i2c_scan_btn.setEnabled(True)
            return
        self.i2c_worker = I2cMemoryWorker(
            self._i2c_url(), settings,
            operation, request["address"], request["start"],
            request["register_width"], request["big_endian"],
            request["length"], request.get("payload", b""),
            request["page_size"], request["write_delay_ms"],
            request.get("bank_size", 0),
            lambda action, data: self._signals.i2c_memory_done.emit(action, data),
            lambda error: self._signals.i2c_inspector_error.emit(error, request),
        )
        self.i2c_worker.start()

    def _i2c_memory_done(self, operation, data):
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_device_inspector.handle_memory_result(operation, data)

    def _i2c_inspector_error(self, error, request):
        """Report inspector errors inline, including errors during live polling."""
        self.i2c_worker = None
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_device_inspector.setEnabled(True)
        self.i2c_device_inspector.handle_operation_error(error, request)

    def _start_i2c_display_test(self, action):
        if self.i2c_display_controller.currentText() != "SSD1306":
            QMessageBox.warning(
                self, "Display Test",
                "Quick patterns require SSD1306. Use Sequence Builder for a "
                "custom or unknown display."
            )
            return
        if self.i2c_worker and self.i2c_worker.is_alive():
            QMessageBox.warning(self, "I²C busy", "Wait for the current I²C operation.")
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            QMessageBox.warning(self, "I²C", "Select a device and an I²C channel first.")
            return
        try:
            address = self._parse_i2c_number(
                self.i2c_display_address.currentText(), "Display address"
            )
            if not 0x03 <= address <= 0x77:
                raise ValueError("The 7-bit display address must be from 0x03 to 0x77.")
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid I²C value", str(exc))
            return
        width, height = self.i2c_display_resolution.currentData()
        self.i2c_device_inspector.pause_polling()
        if action == "initialize":
            self._load_ssd1306_trace()
        for button in self.i2c_display_buttons:
            button.setEnabled(False)
        self.i2c_scan_btn.setEnabled(False)
        self.i2c_device_inspector.setEnabled(False)
        self.i2c_display_status.setText(f"SSD1306 {action} in progress…")
        self.i2c_worker = Ssd1306Worker(
            self._i2c_url(), settings,
            address, width, height, action,
            lambda completed: self._signals.i2c_display_done.emit(completed),
            lambda error: self._signals.i2c_error.emit(error),
        )
        self.i2c_worker.start()

    def _i2c_canvas_size(self):
        return self.i2c_display_resolution.currentData()

    def _i2c_logical_canvas_size(self):
        width, height = self._i2c_canvas_size()
        if self.i2c_display_orientation.currentData() == "horizontal":
            return width, height
        return height, width

    def _orient_i2c_qimage(self, image):
        orientation = self.i2c_display_orientation.currentData()
        if orientation == "clockwise":
            return image.transformed(QTransform().rotate(90))
        if orientation == "counter_clockwise":
            return image.transformed(QTransform().rotate(-90))
        return image

    def _image_orientation_changed(self):
        if self._i2c_preview_kind == "loaded" and self._i2c_loaded_image_path:
            self._rebuild_i2c_loaded_image()
        elif self._i2c_preview_kind == "example_image":
            self._load_i2c_example_image()
        elif self._i2c_preview_kind == "text":
            self._preview_i2c_display_text()

    def _set_i2c_canvas_preview(self, image, light_background=None, binary_source=False):
        self._i2c_source_image = image.convertToFormat(QImage.Format.Format_ARGB32)
        self._i2c_source_light_background = light_background
        self._i2c_source_is_binary = binary_source
        self._refresh_i2c_binary_preview()

    def _refresh_i2c_binary_preview(self):
        if self._i2c_source_image is None:
            return
        source = self._i2c_source_image
        width, height = source.width(), source.height()
        threshold = self.i2c_image_threshold.value()
        pixels = []
        bright_opaque_count = 0
        opaque_count = 0
        for y in range(height):
            row = []
            for x in range(width):
                pixel = source.pixel(x, y)
                alpha = (pixel >> 24) & 0xFF
                red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
                luminance = (red * 299 + green * 587 + blue * 114) // 1000
                opaque = alpha >= 16
                row.append((opaque, luminance))
                opaque_count += int(opaque)
                bright_opaque_count += int(opaque and luminance >= threshold)
            pixels.append(row)
        if self._i2c_source_light_background is None:
            light_background = bright_opaque_count > (opaque_count // 2) if opaque_count else False
        else:
            light_background = self._i2c_source_light_background
        use_light_background = self.i2c_image_auto_background.isChecked() and light_background
        manual_invert = self.i2c_image_invert.isChecked()
        use_dither = self.i2c_image_conversion.currentIndex() == 0
        bayer = (
            (0, 8, 2, 10), (12, 4, 14, 6),
            (3, 11, 1, 9), (15, 7, 13, 5),
        )
        binary = QImage(width, height, QImage.Format.Format_RGB32)
        binary.fill(QColor("black"))
        for y, row in enumerate(pixels):
            for x, (opaque, luminance) in enumerate(row):
                if not opaque:
                    lit = False
                elif self._i2c_source_is_binary:
                    lit = luminance >= 128
                elif use_dither:
                    ink = 255 - luminance if use_light_background else luminance
                    if ink <= 8:
                        lit = False
                    elif ink >= 247:
                        lit = True
                    else:
                        ink = max(0, min(255, ink + threshold - 128))
                        lit = ink > (bayer[y % 4][x % 4] * 16 + 7)
                elif use_light_background:
                    lit = luminance < threshold
                else:
                    lit = luminance >= threshold
                if manual_invert:
                    lit = not lit
                binary.setPixelColor(x, y, QColor("white" if lit else "black"))
        self._i2c_canvas_image = binary
        pixmap = QPixmap.fromImage(binary).scaled(
            self.i2c_display_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.i2c_display_preview.setPixmap(pixmap)

    def _preview_i2c_display_text(self):
        self._i2c_loaded_image_path = None
        self._i2c_preview_kind = "text"
        width, height = self._i2c_logical_canvas_size()
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("black"))
        painter = QPainter(image)
        painter.setPen(QColor("white"))
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        font = QFont("DejaVu Sans Mono", self.i2c_display_font_size.value())
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
        painter.setFont(font)
        painter.drawText(
            image.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.i2c_display_text.text(),
        )
        painter.end()
        image = self._orient_i2c_qimage(image)
        self._set_i2c_canvas_preview(image, light_background=False, binary_source=True)
        self.i2c_display_status.setText("Text preview generated. Press Send preview to test it.")

    def _load_i2c_example_text(self):
        self.i2c_display_text.setText("Hello I2C!\nSSD1306")
        self.i2c_display_font_size.setValue(12)
        self._preview_i2c_display_text()
        self.i2c_display_status.setText(
            "Example text ready. Press Send preview to write its framebuffer."
        )

    def _load_i2c_example_image(self):
        self._i2c_loaded_image_path = None
        self._i2c_preview_kind = "example_image"
        width, height = self._i2c_logical_canvas_size()
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("black"))
        painter = QPainter(image)
        painter.setPen(QColor("white"))
        painter.drawRect(0, 0, width - 1, height - 1)
        radius = max(6, min(width, height) // 5)
        center_x, center_y = width // 4, height // 2
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        painter.drawLine(center_x - radius // 2, center_y, center_x, center_y + radius // 2)
        painter.drawLine(center_x, center_y + radius // 2, center_x + radius, center_y - radius)
        painter.setFont(QFont("Sans Serif", max(7, height // 7), QFont.Weight.Bold))
        painter.drawText(
            width // 2, 0, width // 2 - 2, height,
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "I2C\nOK",
        )
        painter.end()
        image = self._orient_i2c_qimage(image)
        self._set_i2c_canvas_preview(image, light_background=False, binary_source=True)
        self.i2c_display_status.setText(
            "Example image ready. Press Send preview to write its framebuffer."
        )

    def _load_i2c_display_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load monochrome display image", "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All files (*)"
        )
        if not path:
            return
        source = QImage(path)
        if source.isNull():
            QMessageBox.warning(self, "Display image", "Could not load that image.")
            return
        self._i2c_loaded_image_path = path
        self._i2c_preview_kind = "loaded"
        self._rebuild_i2c_loaded_image()
        self.i2c_display_status.setText(f"Image loaded: {path}")

    def _image_conversion_controls_changed(self):
        if self._i2c_loaded_image_path:
            self._rebuild_i2c_loaded_image()
        else:
            self._refresh_i2c_binary_preview()

    def _rebuild_i2c_loaded_image(self):
        path = self._i2c_loaded_image_path
        if not path:
            return
        width, height = self._i2c_canvas_size()
        scaling_text = self.i2c_image_scaling.currentText()
        if scaling_text.startswith("Stretch"):
            scaling = "stretch"
        elif scaling_text.startswith("Fill"):
            scaling = "crop"
        else:
            scaling = "fit"
        try:
            pixels, metadata = convert_image(
                path, width, height, scaling=scaling,
                dither=self.i2c_image_conversion.currentIndex() == 0,
                brightness=self.i2c_image_threshold.value(),
                auto_background=self.i2c_image_auto_background.isChecked(),
                orientation=self.i2c_display_orientation.currentData(),
            )
        except Exception as exc:
            self.i2c_display_status.setText(f"Image conversion error: {exc}")
            return
        canvas = QImage(width, height, QImage.Format.Format_RGB32)
        canvas.fill(QColor("black"))
        for index, lit in enumerate(pixels):
            if lit:
                canvas.setPixelColor(index % width, index // width, QColor("white"))
        self._set_i2c_canvas_preview(
            canvas, light_background=False, binary_source=True
        )
        mode = {
            "stretch": "whole image stretched to 128×64",
            "crop": "cropped to fill",
            "fit": "whole image with original proportions",
        }[scaling]
        self.i2c_display_status.setText(
            f"Converted with Lanczos + autocontrast + "
            f"{'Floyd-Steinberg' if self.i2c_image_conversion.currentIndex() == 0 else 'threshold'} "
            f"({mode}, source {metadata['source_size'][0]}×{metadata['source_size'][1]})."
        )

    def _i2c_canvas_framebuffer(self):
        if self._i2c_canvas_image is None:
            raise ValueError("Generate a text preview or load an image first.")
        width, height = self._i2c_canvas_size()
        if (self._i2c_canvas_image.width(), self._i2c_canvas_image.height()) != (width, height):
            raise ValueError("Preview resolution changed; generate the preview again.")
        data = bytearray(width * (height // 8))
        for y in range(height):
            for x in range(width):
                pixel = self._i2c_canvas_image.pixel(x, y)
                red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
                lit = ((red * 299 + green * 587 + blue * 114) // 1000) >= 128
                if lit:
                    data[(y // 8) * width + x] |= 1 << (y % 8)
        return bytes(data)

    def _send_i2c_display_canvas(self):
        if self.i2c_display_controller.currentText() != "SSD1306":
            QMessageBox.warning(
                self, "Display preview",
                "Text and image framebuffers currently support SSD1306 only."
            )
            return
        if self.i2c_worker and self.i2c_worker.is_alive():
            QMessageBox.warning(self, "I²C busy", "Wait for the current I²C operation.")
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            QMessageBox.warning(self, "I²C", "Select a device and an I²C channel first.")
            return
        try:
            address = self._parse_i2c_number(
                self.i2c_display_address.currentText(), "Display address"
            )
            framebuffer = self._i2c_canvas_framebuffer()
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Display preview", str(exc))
            return
        width, height = self._i2c_canvas_size()
        self.i2c_device_inspector.pause_polling()
        self.i2c_device_inspector.setEnabled(False)
        self.i2c_display_status.setText("Sending preview framebuffer…")
        self.i2c_worker = Ssd1306Worker(
            self._i2c_url(), settings,
            address, width, height, "custom",
            lambda completed: self._signals.i2c_display_done.emit(completed),
            lambda error: self._signals.i2c_error.emit(error),
            framebuffer=framebuffer,
        )
        self.i2c_worker.start()

    def _i2c_display_done(self, action):
        labels = {
            "initialize": "Display initialized", "clear": "Display cleared",
            "all_on": "All-pixels pattern sent", "border": "Border pattern sent",
            "grid": "Grid pattern sent", "bars": "Bars pattern sent",
            "invert": "Display inverted", "normal": "Normal display mode restored",
            "display_on": "Display turned on", "display_off": "Display turned off",
            "trace_step": "Selected trace step sent",
            "custom": "Preview framebuffer sent",
        }
        self.i2c_display_status.setText(f"{labels[action]} (ACK).")
        if action == "trace_step":
            self.i2c_trace_status.setText("Selected command sent successfully (ACK).")
        self.i2c_worker = None
        for button in self.i2c_display_buttons:
            button.setEnabled(True)
        self.i2c_scan_btn.setEnabled(True)
        self.i2c_device_inspector.setEnabled(True)

    def _load_ssd1306_trace(self):
        _width, height = self.i2c_display_resolution.currentData()
        steps = ssd1306_init_steps(height)
        self.i2c_trace_table.setRowCount(0)
        read_only = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for index, (name, command, description) in enumerate(steps, start=1):
            row = self.i2c_trace_table.rowCount()
            self.i2c_trace_table.insertRow(row)
            values = (
                str(index), name, "Command",
                " ".join(f"{value:02X}" for value in command), description,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFlags(read_only)
                self.i2c_trace_table.setItem(row, column, item)
        self.i2c_trace_status.setText(
            f"Loaded {len(steps)} SSD1306 initialization steps for {height} rows. "
            "Only the Bytes column is editable."
        )

    def _capture_i2c_profile(self):
        rows = []
        for row in range(self.i2c_trace_table.rowCount()):
            rows.append([
                self.i2c_trace_table.item(row, column).text()
                if self.i2c_trace_table.item(row, column) else ""
                for column in range(1, 5)
            ])
        return {
            "format": "i2c-display-profile-v1",
            "name": self.i2c_profile_tabs.tabText(self._i2c_active_profile)
                    if self._i2c_active_profile >= 0 else "Display",
            "controller": self.i2c_display_controller.currentText(),
            "resolution": self.i2c_display_resolution.currentText(),
            "address": self.i2c_sequence_address.currentText(),
            "command_prefix": self.i2c_command_prefix.text(),
            "data_prefix": self.i2c_data_prefix.text(),
            "preview_text": self.i2c_display_text.text(),
            "preview_font_size": self.i2c_display_font_size.value(),
            "image_threshold": self.i2c_image_threshold.value(),
            "invert_pixels": self.i2c_image_invert.isChecked(),
            "auto_dark_background": self.i2c_image_auto_background.isChecked(),
            "image_conversion": self.i2c_image_conversion.currentText(),
            "image_scaling": self.i2c_image_scaling.currentText(),
            "orientation": self.i2c_display_orientation.currentData(),
            "steps": rows,
        }

    def _apply_i2c_profile(self, profile):
        self._i2c_profile_switching = True
        self.i2c_sequence_address.setCurrentText(profile.get("address", "0x3C"))
        self.i2c_command_prefix.setText(profile.get("command_prefix", "00"))
        self.i2c_data_prefix.setText(profile.get("data_prefix", "40"))
        self.i2c_display_text.setText(profile.get("preview_text", "Hello I2C"))
        self.i2c_display_font_size.setValue(int(profile.get("preview_font_size", 14)))
        self.i2c_image_threshold.setValue(int(profile.get("image_threshold", 128)))
        self.i2c_image_invert.setChecked(bool(profile.get("invert_pixels", False)))
        self.i2c_image_auto_background.setChecked(
            bool(profile.get("auto_dark_background", True))
        )
        self._set_combo(
            self.i2c_image_conversion,
            profile.get("image_conversion", "Floyd-Steinberg (best detail)")
        )
        self._set_combo(
            self.i2c_image_scaling,
            profile.get("image_scaling", "Stretch to 128×64 (whole image)")
        )
        orientation_index = self.i2c_display_orientation.findData(
            profile.get("orientation", "horizontal")
        )
        if orientation_index >= 0:
            self.i2c_display_orientation.setCurrentIndex(orientation_index)
        self._set_combo(self.i2c_display_controller, profile.get("controller", "SSD1306"))
        self._set_combo(self.i2c_display_resolution, profile.get("resolution", "128 × 64"))
        self.i2c_trace_table.setRowCount(0)
        for values in profile.get("steps", []):
            row = self.i2c_trace_table.rowCount()
            self.i2c_trace_table.insertRow(row)
            self.i2c_trace_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            for column, value in enumerate(values, start=1):
                self.i2c_trace_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._renumber_i2c_trace()
        self._i2c_profile_switching = False

    def _store_active_i2c_profile(self):
        if 0 <= self._i2c_active_profile < len(self._i2c_profiles):
            self._i2c_profiles[self._i2c_active_profile] = self._capture_i2c_profile()

    def _new_i2c_profile(self, name=None, load_preset=False):
        if isinstance(name, bool):
            name = None
        self._store_active_i2c_profile()
        name = name or f"Display {len(self._i2c_profiles) + 1}"
        profile = {
            "format": "i2c-display-profile-v1", "name": name,
            "controller": "SSD1306" if load_preset else "Custom / Unknown",
            "resolution": "128 × 64",
            "address": "0x3C", "command_prefix": "00",
            "data_prefix": "40", "preview_text": "Hello I2C",
            "preview_font_size": 14, "image_threshold": 128,
            "invert_pixels": False, "auto_dark_background": True,
            "image_conversion": "Floyd-Steinberg (best detail)",
            "image_scaling": "Stretch to 128×64 (whole image)",
            "orientation": "horizontal",
            "steps": [],
        }
        self._i2c_profiles.append(profile)
        self.i2c_profile_tabs.addTab(name)
        index = len(self._i2c_profiles) - 1
        self._i2c_active_profile = index
        self.i2c_profile_tabs.setCurrentIndex(index)
        self._apply_i2c_profile(profile)
        if load_preset:
            self._load_ssd1306_trace()
            self._load_i2c_example_image()
            self._store_active_i2c_profile()

    def _switch_i2c_profile(self, index):
        if self._i2c_profile_switching or index < 0 or index >= len(self._i2c_profiles):
            return
        self._store_active_i2c_profile()
        self._i2c_active_profile = index
        self._apply_i2c_profile(self._i2c_profiles[index])
        self.i2c_trace_status.setText(f"Profile: {self.i2c_profile_tabs.tabText(index)}")

    def _duplicate_i2c_profile(self):
        self._store_active_i2c_profile()
        if self._i2c_active_profile < 0:
            return
        source = json.loads(json.dumps(self._i2c_profiles[self._i2c_active_profile]))
        source["name"] = f"{source['name']} copy"
        self._i2c_profiles.append(source)
        index = self.i2c_profile_tabs.addTab(source["name"])
        self.i2c_profile_tabs.setCurrentIndex(index)

    def _rename_i2c_profile(self):
        index = self.i2c_profile_tabs.currentIndex()
        if index < 0:
            return
        current = self.i2c_profile_tabs.tabText(index)
        name, accepted = QInputDialog.getText(self, "Rename display profile", "Name:", text=current)
        if accepted and name.strip():
            self.i2c_profile_tabs.setTabText(index, name.strip())
            self._i2c_profiles[index]["name"] = name.strip()

    def _close_i2c_profile(self, index):
        if len(self._i2c_profiles) <= 1:
            QMessageBox.information(self, "Display profiles", "At least one profile must remain open.")
            return
        self._store_active_i2c_profile()
        self._i2c_profiles.pop(index)
        self.i2c_profile_tabs.removeTab(index)
        self._i2c_active_profile = self.i2c_profile_tabs.currentIndex()
        self._apply_i2c_profile(self._i2c_profiles[self._i2c_active_profile])

    def _save_i2c_profile(self):
        self._store_active_i2c_profile()
        if self._i2c_active_profile < 0:
            return
        profile = self._i2c_profiles[self._i2c_active_profile]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save display profile", f"{profile['name']}.i2cdisplay.json",
            "I2C display profile (*.i2cdisplay.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as output:
                json.dump(profile, output, indent=2, ensure_ascii=False)
                output.write("\n")
            self.i2c_trace_status.setText(f"Profile saved: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Save profile error", str(exc))

    def _open_i2c_profile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open display profile", "",
            "I2C display profile (*.i2cdisplay.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as source:
                profile = json.load(source)
            if profile.get("format") != "i2c-display-profile-v1":
                raise ValueError("Unsupported display profile format.")
            self._store_active_i2c_profile()
            self._i2c_profiles.append(profile)
            index = self.i2c_profile_tabs.addTab(profile.get("name", "Display"))
            self.i2c_profile_tabs.setCurrentIndex(index)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Open profile error", str(exc))

    def _trace_rows(self):
        rows = []
        for row in range(self.i2c_trace_table.rowCount()):
            step_type = self.i2c_trace_table.item(row, 2).text().strip().title()
            if step_type not in ("Command", "Data", "Raw", "Delay"):
                raise ValueError(
                    f"Step {row + 1} type must be Command, Data, Raw, or Delay."
                )
            value = self.i2c_trace_table.item(row, 3).text().strip()
            if step_type == "Delay":
                try:
                    milliseconds = int(value, 0)
                except ValueError as exc:
                    raise ValueError(f"Invalid delay in step {row + 1}.") from exc
                if milliseconds < 0:
                    raise ValueError(f"Delay in step {row + 1} cannot be negative.")
                payload = b""
            else:
                try:
                    payload = bytes.fromhex(value)
                except ValueError as exc:
                    raise ValueError(f"Invalid HEX bytes in step {row + 1}.") from exc
                if not payload:
                    raise ValueError(f"Step {row + 1} has no bytes.")
                milliseconds = 0
            rows.append({
                "step": row + 1,
                "action": self.i2c_trace_table.item(row, 1).text(),
                "type": step_type,
                "bytes": list(payload),
                "milliseconds": milliseconds,
                "description": self.i2c_trace_table.item(row, 4).text(),
            })
        return rows

    def _renumber_i2c_trace(self):
        for row in range(self.i2c_trace_table.rowCount()):
            item = QTableWidgetItem(str(row + 1))
            item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.i2c_trace_table.setItem(row, 0, item)

    def _add_i2c_trace_step(self):
        row = self.i2c_trace_table.currentRow()
        row = self.i2c_trace_table.rowCount() if row < 0 else row + 1
        self.i2c_trace_table.insertRow(row)
        for column, value in enumerate(("", "New step", "Command", "", "")):
            self.i2c_trace_table.setItem(row, column, QTableWidgetItem(value))
        self._renumber_i2c_trace()
        self.i2c_trace_table.selectRow(row)

    def _remove_i2c_trace_step(self):
        row = self.i2c_trace_table.currentRow()
        if row >= 0:
            self.i2c_trace_table.removeRow(row)
            self._renumber_i2c_trace()

    def _move_i2c_trace_step(self, direction):
        row = self.i2c_trace_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.i2c_trace_table.rowCount():
            return
        values = [self.i2c_trace_table.takeItem(row, col) for col in range(1, 5)]
        other = [self.i2c_trace_table.takeItem(target, col) for col in range(1, 5)]
        for col, item in enumerate(other, start=1):
            self.i2c_trace_table.setItem(row, col, item)
        for col, item in enumerate(values, start=1):
            self.i2c_trace_table.setItem(target, col, item)
        self.i2c_trace_table.selectRow(target)

    def _i2c_sequence_address_value(self):
        address = self._parse_i2c_number(
            self.i2c_sequence_address.currentText(), "Sequence address"
        )
        if not 0x03 <= address <= 0x77:
            raise ValueError("The 7-bit sequence address must be from 0x03 to 0x77.")
        return address

    def _i2c_sequence_prefixes(self):
        try:
            command = bytes.fromhex(self.i2c_command_prefix.text().strip())
            data = bytes.fromhex(self.i2c_data_prefix.text().strip())
        except ValueError as exc:
            raise ValueError("Command and data prefixes must contain HEX bytes.") from exc
        return command, data

    def _prepare_i2c_sequence_steps(self):
        rows = self._trace_rows()
        command_prefix, data_prefix = self._i2c_sequence_prefixes()
        prepared = []
        for row in rows:
            step = dict(row)
            raw = bytes(row["bytes"])
            if row["type"] == "Command":
                step["payload"] = command_prefix + raw
            elif row["type"] == "Data":
                step["payload"] = data_prefix + raw
            elif row["type"] == "Raw":
                step["payload"] = raw
            prepared.append(step)
        return prepared

    def _run_i2c_trace_step(self):
        row = self.i2c_trace_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Command Trace", "Select a trace row first.")
            return
        if self.i2c_worker and self.i2c_worker.is_alive():
            QMessageBox.warning(self, "I²C busy", "Wait for the current I²C operation.")
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            QMessageBox.warning(self, "I²C", "Select a device and an I²C channel first.")
            return
        try:
            address = self._i2c_sequence_address_value()
            step = self._prepare_i2c_sequence_steps()[row]
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid trace step", str(exc))
            return
        if step["type"] == "Delay":
            QTimer.singleShot(
                step["milliseconds"],
                lambda: self.i2c_trace_status.setText(
                    f"Delay step {row + 1} completed ({step['milliseconds']} ms)."
                ),
            )
            self.i2c_trace_status.setText(f"Waiting {step['milliseconds']} ms…")
            return
        self.i2c_device_inspector.pause_polling()
        self.i2c_device_inspector.setEnabled(False)
        self.i2c_trace_status.setText(f"Running step {row + 1}…")
        self.i2c_worker = I2cRawWriteWorker(
            self._i2c_url(), settings,
            address, step["payload"],
            lambda completed: self._signals.i2c_display_done.emit(completed),
            lambda error: self._signals.i2c_error.emit(error),
        )
        self.i2c_worker.start()

    def _toggle_i2c_sequence(self):
        if self.i2c_worker and self.i2c_worker.is_alive():
            if isinstance(self.i2c_worker, I2cSequenceWorker):
                self.i2c_worker.stop()
                self.i2c_run_sequence_btn.setEnabled(False)
                self.i2c_run_sequence_btn.setText("Stopping…")
            else:
                QMessageBox.warning(self, "I²C busy", "Wait for the current I²C operation.")
            return
        if not self.i2c_device_combo.currentData() or self.i2c_channel_combo.currentData() is None:
            QMessageBox.warning(self, "I²C", "Select a device and an I²C channel first.")
            return
        try:
            address = self._i2c_sequence_address_value()
            steps = self._prepare_i2c_sequence_steps()
            if not steps:
                raise ValueError("Add at least one sequence step.")
            settings = self._i2c_bus_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid sequence", str(exc))
            return
        self.i2c_device_inspector.pause_polling()
        self.i2c_device_inspector.setEnabled(False)
        self.i2c_run_sequence_btn.setText("Stop sequence")
        self.i2c_trace_status.setText(f"Running {len(steps)} steps…")
        self.i2c_worker = I2cSequenceWorker(
            self._i2c_url(), settings,
            address, steps,
            lambda index: self._signals.i2c_sequence_step.emit(index),
            lambda stopped: self._signals.i2c_sequence_done.emit(stopped),
            lambda error: self._signals.i2c_error.emit(error),
        )
        self.i2c_worker.start()

    def _i2c_sequence_step_done(self, index):
        self.i2c_trace_table.selectRow(index)
        self.i2c_trace_status.setText(
            f"Step {index + 1} completed (ACK or delay completed)."
        )

    def _i2c_sequence_finished(self, stopped):
        self.i2c_worker = None
        self.i2c_run_sequence_btn.setEnabled(True)
        self.i2c_run_sequence_btn.setText("Run all")
        self.i2c_device_inspector.setEnabled(True)
        self.i2c_trace_status.setText(
            "Sequence stopped by user." if stopped else "Sequence completed successfully."
        )

    def _export_i2c_trace(self, output_format):
        if not self.i2c_trace_table.rowCount():
            self._load_ssd1306_trace()
        try:
            rows = self._trace_rows()
        except ValueError as exc:
            QMessageBox.warning(self, "Command Trace", str(exc))
            return
        suffix = "json" if output_format == "json" else "h"
        file_filter = "JSON (*.json)" if output_format == "json" else "C header (*.h)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SSD1306 initialization", f"ssd1306_init.{suffix}", file_filter
        )
        if not path:
            return
        try:
            if output_format == "json":
                document = {
                    "controller": self.i2c_display_controller.currentText(),
                    "resolution": self.i2c_display_resolution.currentText(),
                    "i2c_address_7bit": self.i2c_sequence_address.currentText(),
                    "command_prefix_hex": self.i2c_command_prefix.text().strip(),
                    "data_prefix_hex": self.i2c_data_prefix.text().strip(),
                    "steps": rows,
                }
                content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
            else:
                lines = ["/* Generated by Serial Monitor - SSD1306 initialization */"]
                for entry in rows:
                    if entry["type"] == "Delay":
                        lines.append(
                            f"/* Step {entry['step']}: delay {entry['milliseconds']} ms - "
                            f"{entry['description']} */"
                        )
                        continue
                    values = ", ".join(f"0x{value:02X}" for value in entry["bytes"])
                    symbol = re.sub(r"[^a-z0-9]+", "_", entry["action"].lower()).strip("_")
                    lines.append(f"static const uint8_t ssd1306_{symbol}[] = {{ {values} }}; "
                                 f"/* {entry['description']} */")
                content = "\n".join(lines) + "\n"
            with open(path, "w", encoding="utf-8") as output:
                output.write(content)
            self.i2c_trace_status.setText(f"Trace exported to {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Export error", str(exc))

    # ──────────────────────────────────────────────────────────────────────────
    # Connection
    # ──────────────────────────────────────────────────────────────────────────

    def _toggle_connection(self):
        if self.worker and self.worker.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No Port", "Please select a serial port.")
            return
        if os.name != "nt" and not os.access(port, os.R_OK | os.W_OK):
            user = getpass.getuser()
            QMessageBox.warning(
                self,
                "Serial port permission required",
                f"Your Ubuntu user cannot access {port}.\n\n"
                f"Run this command in a terminal:\n"
                f"sudo usermod -aG dialout {user}\n\n"
                "Then sign out of Ubuntu completely and sign back in. "
                "This setup is only required once."
            )
            return
        self._connection_established = False
        initial_rts, initial_dtr = (
            self.uart_tools.output_states
            if hasattr(self, "uart_tools") else (True, True)
        )
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
            on_raw_data=lambda d: self._signals.raw_data_received.emit(d),
            initial_rts=initial_rts,
            initial_dtr=initial_dtr,
        )
        self.worker.start()
        QTimer.singleShot(300, self._check_connected)

    def _check_connected(self):
        if self.worker and self.worker.is_connected:
            self._connection_established = True
            if hasattr(self, "uart_tools"):
                self.uart_tools.set_connection(
                    self.worker, self.flow_combo.currentText()
                )
            self.connect_btn.setText("Disconnect")
            set_role(self.connect_btn, "danger")
            self.led_lbl.setStyleSheet("color:#00FF7F; font-size:18px;")
            self.conn_lbl.setText(f"Connected — {self.port_combo.currentText()}")
        else:
            self._disconnect()

    def _disconnect(self):
        self._connection_established = False
        if hasattr(self, "uart_tools"):
            self.uart_tools.set_connection(None, self.flow_combo.currentText())
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=2)
            self.worker = None
        self._auto_timer.stop()
        self.auto_btn.setText("Start Auto")
        set_role(self.auto_btn, "primary")
        self.connect_btn.setText("Connect")
        set_role(self.connect_btn, "primary")
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
        was_connected = self._connection_established
        self._disconnect()
        if was_connected:
            # Hot-unplug is expected during adapter replacement. Keep the GUI
            # responsive and report it without a modal dialog that looks like
            # an application freeze.
            message = f"Serial device disconnected: {error}"
            self.conn_lbl.setText("Disconnected — device removed")
            self.statusBar().showMessage(message, 6000)
            return
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
        self._append_raw(text, color)

    # ──────────────────────────────────────────────────────────────────────────
    # Sending
    # ──────────────────────────────────────────────────────────────────────────

    def _send_format_changed(self, *_args):
        """Apply strict HEX editing only while HEX format is selected."""
        is_hex = self.send_fmt.currentText() == "HEX"
        self.send_edit.setValidator(
            self._hex_send_validator if is_hex else None
        )
        self.send_edit.setPlaceholderText(
            "Example: AA 55 0D 0A" if is_hex else "Text to send"
        )
        self._update_send_preview()

    def _current_send_payload(self):
        eol = EOL_TX_MAP.get(self.eol_tx_combo.currentText(), b"\n")
        return encode_serial_payload(
            self.send_edit.text(), self.send_fmt.currentText(), eol
        )

    def _update_send_preview(self, *_args):
        """Show exact outgoing bytes and prevent incomplete transmissions."""
        try:
            payload = self._current_send_payload()
        except ValueError as exc:
            valid = False
            self.send_preview.setText(str(exc) if self.send_edit.text() else "")
            self.send_preview.setStyleSheet("color:#FF7777;")
        else:
            valid = True
            self.send_preview.setText(format_payload_preview(payload))
            self.send_preview.setStyleSheet("color:#70DB93;")

        if not valid and self._auto_timer.isActive():
            self._toggle_auto_send()
        self.send_btn.setEnabled(valid)
        self.auto_btn.setEnabled(valid or self._auto_timer.isActive())

    def _send_data(self):
        if not self.worker or not self.worker.is_connected:
            QMessageBox.warning(self, "Not Connected", "Connect to a serial port first.")
            return
        text = self.send_edit.text()
        if not text:
            return
        try:
            payload = self._current_send_payload()
        except ValueError as exc:
            self._update_send_preview()
            self.statusBar().showMessage(str(exc), 5000)
            return
        self.worker.send(payload)
        line = self._format_line(payload, "TX")
        self._append(line, self._color_tx)
        self.log.append(line)
        self.tx_lbl.setText(f"TX: {self._human(self.worker.tx_bytes)}")
        self.config.add_to_history(text)
        self._update_history_combo()
        if not self._auto_timer.isActive():
            self.send_edit.clear()

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
            set_role(self.auto_btn, "primary")
        else:
            if not self.worker or not self.worker.is_connected:
                QMessageBox.warning(self, "Not Connected", "Connect first.")
                return
            ms = int(self.interval_spin.value() * 1000)
            self._auto_timer.start(ms)
            self.auto_btn.setText("Stop Auto")
            set_role(self.auto_btn, "danger")

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

        # Format column (ASCII/HEX)
        fmt_combo = QComboBox()
        fmt_combo.addItems(SEND_FMTS)
        fmt_combo.setCurrentText("ASCII")
        self.seq_table.setCellWidget(row, 2, fmt_combo)
        
        # Send button column
        btn_send = QPushButton("▶")
        btn_send.setFixedSize(28, 25)
        set_role(btn_send, "success")
        btn_send.clicked.connect(lambda: self._send_sequence_command_manual(row))
        self.seq_table.setCellWidget(row, 3, btn_send)
        
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
        self.seq_table.setCellWidget(row, 4, move_widget)
        
        # Delete button column
        btn_delete = QPushButton("✕")
        btn_delete.setFixedSize(30, 25)
        set_role(btn_delete, "danger")
        btn_delete.clicked.connect(lambda: self._remove_sequence_command(row))
        self.seq_table.setCellWidget(row, 5, btn_delete)
    
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

        # Swap command formats
        fmt1 = self._get_sequence_command_format(row1)
        fmt2 = self._get_sequence_command_format(row2)
        combo1 = self.seq_table.cellWidget(row1, 2)
        combo2 = self.seq_table.cellWidget(row2, 2)
        if combo1:
            combo1.setCurrentText(fmt2)
        if combo2:
            combo2.setCurrentText(fmt1)
        
        self._update_sequence_numbers()
        self._reconnect_sequence_buttons()
    
    def _update_sequence_numbers(self):
        """Update the number column after changes"""
        for i in range(self.seq_table.rowCount()):
            self.seq_table.item(i, 0).setText(str(i + 1))

    def _get_sequence_command_format(self, row: int) -> str:
        combo = self.seq_table.cellWidget(row, 2)
        if combo:
            fmt = str(combo.currentText()).strip().upper()
            if fmt == "HEX":
                return "HEX"
        return "ASCII"
    
    def _reconnect_sequence_buttons(self):
        """Reconnect all button signals after row changes"""
        for row in range(self.seq_table.rowCount()):
            # Reconnect send button
            btn_send = self.seq_table.cellWidget(row, 3)
            if btn_send:
                try:
                    btn_send.clicked.disconnect()
                except:
                    pass
                btn_send.clicked.connect(lambda checked, r=row: self._send_sequence_command_manual(r))
            
            # Reconnect move buttons
            move_widget = self.seq_table.cellWidget(row, 4)
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
            btn_delete = self.seq_table.cellWidget(row, 5)
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
        set_role(self.seq_start_btn, "danger")
        
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
        set_role(self.seq_start_btn, "primary")
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
        fmt = self._get_sequence_command_format(index)
        try:
            payload = encode_serial_payload(cmd_text, fmt, eol)
        except ValueError as exc:
            if fmt == "HEX":
                self.statusBar().showMessage(
                    f"Invalid HEX at row {index + 1}: {exc}",
                    5000,
                )
            else:
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
        fmt = self._get_sequence_command_format(index)
        try:
            payload = encode_serial_payload(expanded, fmt, eol)
        except ValueError as exc:
            if fmt == "HEX":
                msg = (
                    f"El comando de la fila {index + 1} no es HEX válido: {exc}"
                )
                self.statusBar().showMessage(msg, 5000)
                QMessageBox.warning(self, "Formato HEX inválido", msg)
            else:
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

            if isinstance(cmd, dict):
                cmd_text = str(cmd.get("command", ""))
                cmd_format = str(cmd.get("format", "ASCII"))
            else:
                cmd_text = str(cmd)
                cmd_format = "ASCII"
            if cmd_format not in SEND_FMTS:
                cmd_format = "ASCII"
            
            # Number column
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.seq_table.setItem(row, 0, num_item)
            
            # Command column (editable)
            cmd_item = QTableWidgetItem(cmd_text)
            self.seq_table.setItem(row, 1, cmd_item)

            # Format column (ASCII/HEX)
            fmt_combo = QComboBox()
            fmt_combo.addItems(SEND_FMTS)
            fmt_combo.setCurrentText(cmd_format)
            self.seq_table.setCellWidget(row, 2, fmt_combo)
            
            # Send button column
            btn_send = QPushButton("▶")
            btn_send.setFixedSize(28, 25)
            set_role(btn_send, "success")
            btn_send.clicked.connect(lambda checked, r=row: self._send_sequence_command_manual(r))
            self.seq_table.setCellWidget(row, 3, btn_send)
            
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
            self.seq_table.setCellWidget(row, 4, move_widget)
            
            # Delete button column
            btn_delete = QPushButton("✕")
            btn_delete.setFixedSize(30, 25)
            set_role(btn_delete, "danger")
            btn_delete.clicked.connect(lambda checked, r=row: self._remove_sequence_command(r))
            self.seq_table.setCellWidget(row, 5, btn_delete)
    
    def _save_sequence_commands(self):
        """Save sequence commands from table to config"""
        commands = []
        for row in range(self.seq_table.rowCount()):
            cmd_item = self.seq_table.item(row, 1)
            if cmd_item:
                commands.append({
                    "command": cmd_item.text(),
                    "format": self._get_sequence_command_format(row)
                })
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
                commands.append({
                    "command": cmd_item.text(),
                    "format": self._get_sequence_command_format(row)
                })
        
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
                if isinstance(cmd, dict):
                    cmd_text = str(cmd.get("command", ""))
                    cmd_format = str(cmd.get("format", "ASCII"))
                else:
                    cmd_text = str(cmd)
                    cmd_format = "ASCII"
                if cmd_format not in SEND_FMTS:
                    cmd_format = "ASCII"
                self.seq_table.item(row, 1).setText(cmd_text)
                fmt_combo = self.seq_table.cellWidget(row, 2)
                if fmt_combo:
                    fmt_combo.setCurrentText(cmd_format)
            
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
        """Find literal text in the visible monitor, case-insensitively."""
        self._search_text = self.search_edit.text()
        self._search_result_index = -1
        self._refresh_search_results()

    def _refresh_search_results(self, preserve_index=False):
        """Rebuild non-destructive highlights for the current literal text."""
        previous_index = self._search_result_index if preserve_index else -1
        self._search_results = []
        if self._search_text:
            cursor = QTextCursor(self.monitor.document())
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            while True:
                cursor = self.monitor.document().find(self._search_text, cursor)
                if cursor.isNull():
                    break
                self._search_results.append(QTextCursor(cursor))

        if previous_index >= 0 and self._search_results:
            self._search_result_index = min(
                previous_index, len(self._search_results) - 1
            )
        elif not preserve_index:
            self._search_result_index = -1
        else:
            self._search_result_index = -1

        self._render_search_highlights()
        if not self._search_text:
            self.search_result_lbl.clear()
        elif self._search_results:
            if self._search_result_index >= 0:
                self.search_result_lbl.setText(
                    f"{self._search_result_index + 1}/{len(self._search_results)}"
                )
            else:
                self.search_result_lbl.setText(
                    f"{len(self._search_results)} match(es)"
                )
        else:
            self.search_result_lbl.setText("No matches")

    def _render_search_highlights(self):
        """Use extra selections so RX/TX text colors are never modified."""
        selections = []
        for index, result_cursor in enumerate(self._search_results):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(result_cursor)
            selection.format.setBackground(QColor(
                "#FFB300" if index == self._search_result_index else "#FFFF00"
            ))
            selection.format.setForeground(QColor("#000000"))
            selections.append(selection)
        self.monitor.setExtraSelections(selections)

    def _select_search_result(self, index):
        if not self._search_results:
            return
        self._search_result_index = index % len(self._search_results)
        cursor = QTextCursor(self._search_results[self._search_result_index])
        self.monitor.setTextCursor(cursor)
        self.monitor.ensureCursorVisible()
        self.search_result_lbl.setText(
            f"{self._search_result_index + 1}/{len(self._search_results)}"
        )
        self._render_search_highlights()
    
    def _search_next(self):
        """Select the next match, wrapping to the beginning."""
        if self._search_results:
            self._select_search_result(self._search_result_index + 1)
    
    def _search_previous(self):
        """Select the previous match, wrapping to the end."""
        if not self._search_results:
            return
        index = (
            len(self._search_results) - 1
            if self._search_result_index < 0
            else self._search_result_index - 1
        )
        self._select_search_result(index)
    
    def _append_raw(self, text: str, color: str):
        """Append colored text and refresh an active literal search."""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.monitor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, fmt)
        self.monitor.setTextCursor(cursor)
        self.monitor.ensureCursorVisible()
        if self._search_text:
            self._refresh_search_results(preserve_index=True)
    
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
        set_role(btn_add, "success")
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
        set_role(btn_delete, "danger")
        def delete_alert():
            current = self.alerts_list.currentRow()
            if current < 0:
                QMessageBox.warning(dialog, "No Selection", "Select an alert to delete.")
                return
            self._alerts.pop(current)
            self._refresh_alerts_list()
        
        btn_delete.clicked.connect(delete_alert)
        button_layout.addWidget(btn_delete)
        
        btn_save = QPushButton("Save configuration")
        set_role(btn_save, "primary")
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
        if not hasattr(self, "send_edit"):
            return
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
        self._search_results.clear()
        self._search_result_index = -1
        self._refresh_search_results()

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
        fg = contrast_text(color)
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
            self.config.set("theme", "light")
        else:
            self._apply_dark_theme()
            self.config.set("theme", "dark")

    def _apply_dark_theme(self):
        self.setStyleSheet(stylesheet("dark"))
        self._dark_mode = True
        if hasattr(self, "theme_btn"):
            self.theme_btn.setText("Light theme")

    def _apply_light_theme(self):
        self.setStyleSheet(stylesheet("light"))
        self._dark_mode = False
        if hasattr(self, "theme_btn"):
            self.theme_btn.setText("Dark theme")

    def _polish_widget_tree(self):
        """Apply usability defaults to static and dynamically-created panels."""
        for table in self.findChildren(QTableWidget):
            table.setAlternatingRowColors(True)
            table.setShowGrid(False)
            table.setWordWrap(False)
            table.verticalHeader().setDefaultSectionSize(34)
            table.horizontalHeader().setMinimumHeight(34)
        for tabs in self.findChildren(QTabWidget):
            tabs.setDocumentMode(True)
            tabs.tabBar().setExpanding(False)
            tabs.tabBar().setUsesScrollButtons(True)
            tabs.tabBar().setDrawBase(False)

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

    @staticmethod
    def _set_combo_data(combo: QComboBox, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def closeEvent(self, event):
        if self._manages_usb_bridges:
            self._closing = True
            self._bridge_monitor_timer.stop()
        self._collect_config()
        if hasattr(self, "uart_tools"):
            self.uart_tools.shutdown()
        if hasattr(self, "usb_bridge_uart_sessions"):
            for session in self.usb_bridge_uart_sessions.values():
                session.shutdown_session()
            for session in self.usb_bridge_i2c_sessions.values():
                session.shutdown_session()
            for session in self.usb_bridge_spi_sessions.values():
                session.shutdown_session()
            for session in self.usb_bridge_gpio_sessions.values():
                session.shutdown_session()
        self.config.save()
        if self.worker:
            self.worker.stop()
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_worker.stop()
        event.accept()


class UartSessionPanel(SerialMonitorApp):
    """Reusable full UART console bound to one physical bridge interface."""

    def __init__(self, interface, bridge, config, channel_manager):
        self.session_channel = interface.name
        self.session_interface = interface.index
        self.bound_bridge = bridge
        self.channel_manager = channel_manager
        self._channel_owner = f"UART session {self.session_channel}"
        super().__init__(config)
        self.setWindowTitle(
            f"{bridge.vendor} {bridge.model} interface {self.session_channel} — UART"
        )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.addWidget(self._build_config_panel())
        root.addWidget(self._build_uart_tools_panel())
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.main_splitter = splitter
        sequence = self._build_sequence_panel()
        sequence.setMinimumWidth(300)
        sequence.setMaximumWidth(520)
        splitter.addWidget(sequence)
        right = QWidget()
        right_root = QVBoxLayout(right)
        right_root.setContentsMargins(0, 0, 0, 0)
        right_root.addWidget(self._build_monitor(), stretch=1)
        right_root.addWidget(self._build_send_panel())
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        width = max(300, min(520, int(self.config.get("sequence_panel_width", 340))))
        splitter.setSizes([width, 900])
        root.addWidget(splitter, stretch=1)
        self._build_status_bar()

    def _load_config_into_ui(self):
        self._refresh_ports()
        self._set_combo_data(self.port_combo, self.config.get("port", ""))
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
        self.uart_tools.load_config(self.config)
        self._set_combo(self.send_fmt, self.config.get("send_format", "ASCII"))
        self.interval_spin.setValue(float(self.config.get("auto_send_interval", 1.0)))
        self._update_history_combo()
        self.seq_interval_spin.setValue(float(self.config.get("sequence_interval", 1.0)))
        self._set_combo(self.seq_mode_combo, self.config.get("sequence_mode", "Stop"))
        self._load_sequence_commands()
        self.seq_table.setColumnWidth(
            1, max(120, min(1000, int(self.config.get("sequence_command_col_width", 220))))
        )
        self._alerts = self.config.get("alerts", [])
        if self.config.get("theme", "dark") == "light":
            self._apply_light_theme()

    def _collect_config(self):
        self.config.set("port", self.port_combo.currentData() or "")
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
        self.uart_tools.collect_config(self.config)
        self.config.set("sequence_interval", self.seq_interval_spin.value())
        self.config.set("sequence_mode", self.seq_mode_combo.currentText())
        self.config.set("sequence_command_col_width", self.seq_table.columnWidth(1))
        sizes = self.main_splitter.sizes()
        if sizes:
            self.config.set("sequence_panel_width", sizes[0])
        self._save_sequence_commands()

    def _refresh_ports(self):
        current = self.port_combo.currentData()
        ports = list_bridge_interface_ports(
            self.session_channel,
            bridge_pid=self.bound_bridge.pid,
            bridge_serial=self.bound_bridge.serial or None,
        )
        self.port_combo.clear()
        for label, device in ports:
            self.port_combo.addItem(label, device)
        index = self.port_combo.findData(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def _connect(self):
        try:
            self.channel_manager.acquire(
                self.session_channel, "UART", self._channel_owner
            )
        except InterfaceBusyError as exc:
            QMessageBox.warning(self, "Adapter interface busy", str(exc))
            return
        super()._connect()
        if self.worker is None:
            self.channel_manager.release(self.session_channel, self._channel_owner)

    def _disconnect(self):
        super()._disconnect()
        self.channel_manager.release(self.session_channel, self._channel_owner)

    def _setup_shortcuts(self):
        # The parent window owns global shortcuts; child sessions use buttons.
        pass

    def is_session_active(self):
        return self.worker is not None

    def shutdown_session(self):
        if self._sequence_running:
            self._stop_sequence()
        self._collect_config()
        self._disconnect()

    def closeEvent(self, event):
        self.shutdown_session()
        event.accept()


class I2cSessionPanel(SerialMonitorApp):
    """Reusable complete I2C toolbox bound to one MPSSE interface."""

    def __init__(self, interface, bridge, config, channel_manager):
        self.session_channel = interface.name
        self.session_interface = interface.index
        self.bound_bridge = bridge
        self.channel_manager = channel_manager
        self._channel_owner = f"I2C session {self.session_channel}"
        super().__init__(config)
        self.setWindowTitle(
            f"{bridge.vendor} {bridge.model} interface {self.session_channel} — I²C"
        )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._build_i2c_tab())
        self._build_status_bar()

    def _refresh_i2c_channels(self):
        self.i2c_channel_combo.clear()
        self.i2c_channel_combo.addItem(
            f"Interface {self.session_channel}", self.session_interface
        )
        self.i2c_channel_combo.setEnabled(False)

    def _load_config_into_ui(self):
        self._refresh_i2c_channels()
        saved_url = self.config.get("i2c_device_url", "")
        index = self.i2c_device_combo.findData(saved_url)
        if index >= 0:
            self.i2c_device_combo.setCurrentIndex(index)
        index = self.i2c_frequency_combo.findData(
            int(self.config.get("i2c_frequency", 100000))
        )
        if index >= 0:
            self.i2c_frequency_combo.setCurrentIndex(index)
        else:
            self.i2c_frequency_combo.setEditText(
                f"{int(self.config.get('i2c_frequency', 100000))} Hz"
            )
        self.i2c_clock_stretching.setChecked(
            bool(self.config.get("i2c_clock_stretching", False))
        )
        self.i2c_retry_count.setValue(
            int(self.config.get("i2c_retry_count", 3))
        )
        if self.config.get("theme", "dark") == "light":
            self._apply_light_theme()

    def _collect_config(self):
        self.config.set("i2c_device_url", self.i2c_device_combo.currentData() or "")
        self.config.set("i2c_channel", self.session_interface)
        try:
            settings = self._i2c_bus_settings()
        except ValueError:
            settings = I2cBusSettings()
        self.config.set("i2c_frequency", settings.frequency)
        self.config.set("i2c_clock_stretching", settings.clock_stretching)
        self.config.set("i2c_retry_count", settings.retry_count)

    def _setup_shortcuts(self):
        pass

    def activate_session(self):
        try:
            self.channel_manager.acquire(
                self.session_channel, "I2C", self._channel_owner
            )
            return True
        except InterfaceBusyError as exc:
            self.i2c_summary.setText(f"ERROR: {exc}")
            return False

    def is_session_active(self):
        return bool(self.i2c_worker and self.i2c_worker.is_alive())

    def shutdown_session(self):
        self._collect_config()
        if hasattr(self, "i2c_device_inspector"):
            self.i2c_device_inspector.pause_polling()
        if self.i2c_worker and self.i2c_worker.is_alive():
            self.i2c_worker.stop()
        self.channel_manager.release(self.session_channel, self._channel_owner)

    def closeEvent(self, event):
        self.shutdown_session()
        event.accept()
