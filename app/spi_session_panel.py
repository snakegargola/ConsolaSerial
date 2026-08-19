"""Qt SPI master toolbox bound to one USB bridge interface."""

from __future__ import annotations

import csv
from datetime import datetime
import json
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .bridge_interface_manager import InterfaceBusyError
from .spi_bus import (
    SPI_MAX_PAYLOAD,
    SpiBusSettings,
    SpiTransaction,
    format_spi_hex,
    parse_spi_hex,
)
from .spi_worker import SpiTransactionWorker


OPERATION_LABELS = {
    "write": "Write",
    "read": "Read (dummy clocks)",
    "write_read": "Write → Read (same /CS)",
    "duplex": "Full duplex",
    "loopback": "Loopback",
    "jedec": "JEDEC ID (0x9F)",
}


class SpiSessionPanel(QWidget):
    """Interactive 8-bit, MSB-first SPI master session."""

    transaction_finished = pyqtSignal(object)

    def __init__(self, interface, bridge, config, channel_manager, parent=None):
        super().__init__(parent)
        self.session_channel = interface.name
        self.session_interface = interface.index
        self.bound_bridge = bridge
        self.config = config
        self.channel_manager = channel_manager
        self._channel_owner = f"SPI session {self.session_channel}"
        self._worker = None
        self._history = []
        self._shutting_down = False
        self.transaction_finished.connect(self._transaction_done)
        self._build_ui()
        self._load_config()
        self._update_operation_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.addWidget(self._build_configuration())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_transaction_tab(), "Transactions")
        self.tabs.addTab(self._build_quick_tests_tab(), "Quick tests")
        self.tabs.addTab(self._build_history_tab(), "History")
        root.addWidget(self.tabs, stretch=1)

    def _build_configuration(self):
        box = QGroupBox("SPI master configuration")
        grid = QGridLayout(box)
        grid.addWidget(QLabel("Adapter:"), 0, 0)
        adapter = QLabel(
            f"{self.bound_bridge.vendor} {self.bound_bridge.model} — "
            f"interface {self.session_channel}"
        )
        grid.addWidget(adapter, 0, 1, 1, 5)

        grid.addWidget(QLabel("Clock:"), 1, 0)
        self.frequency_combo = QComboBox()
        self.frequency_combo.setEditable(True)
        for label, value in (
            ("100 kHz", 100_000), ("500 kHz", 500_000),
            ("1 MHz", 1_000_000), ("5 MHz", 5_000_000),
            ("10 MHz", 10_000_000), ("20 MHz", 20_000_000),
            ("30 MHz", 30_000_000),
        ):
            self.frequency_combo.addItem(label, value)
        self.frequency_combo.setToolTip(
            "Select a preset or type a value such as 2.5 MHz or 2500000 Hz."
        )
        grid.addWidget(self.frequency_combo, 1, 1)

        grid.addWidget(QLabel("Mode:"), 1, 2)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("0 — CPOL 0, CPHA 0", 0)
        self.mode_combo.addItem("1 — CPOL 0, CPHA 1", 1)
        self.mode_combo.addItem("2 — CPOL 1, CPHA 0", 2)
        self.mode_combo.addItem("3 — CPOL 1, CPHA 1", 3)
        self.mode_combo.setToolTip(
            "PyFtdi marks modes 1 and 3 as unofficial; some modes also require "
            "an H-series FTDI controller."
        )
        grid.addWidget(self.mode_combo, 1, 3)

        grid.addWidget(QLabel("/CS lines:"), 1, 4)
        self.cs_count_spin = QSpinBox()
        self.cs_count_spin.setRange(1, 5)
        grid.addWidget(self.cs_count_spin, 1, 5)

        grid.addWidget(QLabel("Selected /CS:"), 2, 0)
        self.chip_select_combo = QComboBox()
        self.cs_count_spin.valueChanged.connect(self._update_chip_selects)
        grid.addWidget(self.chip_select_combo, 2, 1)
        grid.addWidget(QLabel("Dummy byte:"), 2, 2)
        self.dummy_edit = QLineEdit("00")
        self.dummy_edit.setMaxLength(4)
        self.dummy_edit.setToolTip(
            "Byte sent on MOSI while generating clocks for received data."
        )
        self.dummy_edit.textChanged.connect(self._update_wire_preview)
        grid.addWidget(self.dummy_edit, 2, 3)
        self.turbo_check = QCheckBox("Turbo")
        self.turbo_check.setToolTip(
            "Reduces USB validation overhead. Leave disabled while debugging."
        )
        grid.addWidget(self.turbo_check, 2, 4)

        warning = QLabel(
            "8-bit, MSB-first, active-low /CS. Wiring: xDBUS0=SCLK, "
            "xDBUS1=MOSI, xDBUS2=MISO, xDBUS3=/CS0, xDBUS4=/CS1… "
            "Connect GND between the adapter and target."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#D89000;")
        grid.addWidget(warning, 3, 0, 1, 6)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return box

    def _build_transaction_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel("Operation:"), 0, 0)
        self.operation_combo = QComboBox()
        for operation in ("write", "read", "write_read", "duplex"):
            self.operation_combo.addItem(OPERATION_LABELS[operation], operation)
        self.operation_combo.currentIndexChanged.connect(self._update_operation_ui)
        grid.addWidget(self.operation_combo, 0, 1)

        grid.addWidget(QLabel("TX (HEX):"), 1, 0)
        self.tx_edit = QLineEdit("9F")
        self.tx_edit.setPlaceholderText("Example: 9F 00 AA or 0x9F, 0x00")
        self.tx_edit.textChanged.connect(self._update_wire_preview)
        grid.addWidget(self.tx_edit, 1, 1, 1, 4)

        self.rx_length_label = QLabel("RX length:")
        grid.addWidget(self.rx_length_label, 2, 0)
        self.rx_length_spin = QSpinBox()
        self.rx_length_spin.setRange(0, SPI_MAX_PAYLOAD)
        self.rx_length_spin.setValue(3)
        self.rx_length_spin.setSuffix(" bytes")
        self.rx_length_spin.valueChanged.connect(self._update_wire_preview)
        grid.addWidget(self.rx_length_spin, 2, 1)

        self.run_btn = QPushButton("Run transaction")
        self.run_btn.clicked.connect(self._run_custom_transaction)
        grid.addWidget(self.run_btn, 2, 4)

        grid.addWidget(QLabel("MOSI on wire:"), 3, 0)
        self.wire_preview = QLineEdit()
        self.wire_preview.setReadOnly(True)
        grid.addWidget(self.wire_preview, 3, 1, 1, 4)

        grid.addWidget(QLabel("RX (HEX):"), 4, 0)
        self.rx_hex = QLineEdit()
        self.rx_hex.setReadOnly(True)
        grid.addWidget(self.rx_hex, 4, 1, 1, 4)
        grid.addWidget(QLabel("RX (ASCII):"), 5, 0)
        self.rx_ascii = QLineEdit()
        self.rx_ascii.setReadOnly(True)
        grid.addWidget(self.rx_ascii, 5, 1, 1, 4)

        self.status_label = QLabel("Ready.")
        self.status_label.setWordWrap(True)
        grid.addWidget(self.status_label, 6, 0, 1, 5)
        grid.setColumnStretch(3, 1)
        grid.setRowStretch(7, 1)
        return tab

    def _build_quick_tests_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        loopback_help = QLabel(
            "Loopback verifies SCLK, MOSI and MISO. Disconnect the target and "
            "connect xDBUS1 (MOSI) directly to xDBUS2 (MISO)."
        )
        loopback_help.setWordWrap(True)
        grid.addWidget(loopback_help, 0, 0, 1, 3)
        grid.addWidget(QLabel("Pattern (HEX):"), 1, 0)
        self.loopback_edit = QLineEdit("00 FF AA 55 12 34 56 78")
        grid.addWidget(self.loopback_edit, 1, 1)
        self.loopback_btn = QPushButton("Run loopback")
        self.loopback_btn.clicked.connect(self._run_loopback)
        grid.addWidget(self.loopback_btn, 1, 2)

        jedec_help = QLabel(
            "JEDEC sends command 0x9F and reads three bytes without releasing "
            "/CS. It is useful for compatible SPI flash memories."
        )
        jedec_help.setWordWrap(True)
        grid.addWidget(jedec_help, 2, 0, 1, 3)
        self.jedec_btn = QPushButton("Read JEDEC ID")
        self.jedec_btn.clicked.connect(self._run_jedec)
        grid.addWidget(self.jedec_btn, 3, 2)
        self.quick_result = QLabel("No test run yet.")
        self.quick_result.setWordWrap(True)
        grid.addWidget(self.quick_result, 4, 0, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(5, 1)
        return tab

    def _build_history_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        actions = QHBoxLayout()
        export_csv = QPushButton("Export CSV")
        export_csv.clicked.connect(lambda: self._export_history("csv"))
        actions.addWidget(export_csv)
        export_json = QPushButton("Export JSON")
        export_json.clicked.connect(lambda: self._export_history("json"))
        actions.addWidget(export_json)
        clear = QPushButton("Clear history")
        clear.clicked.connect(self._clear_history)
        actions.addWidget(clear)
        actions.addStretch()
        root.addLayout(actions)

        columns = (
            "Time", "Operation", "Mode", "Clock", "/CS", "TX", "RX",
            "Status", "Duration", "Details",
        )
        self.history_table = QTableWidget(0, len(columns))
        self.history_table.setHorizontalHeaderLabels(columns)
        self.history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.history_table)
        return tab

    def activate_session(self):
        """Reserve this physical interface for SPI while its panel is selected."""
        self._shutting_down = False
        try:
            self.channel_manager.acquire(
                self.session_channel, "SPI", self._channel_owner
            )
            return True
        except InterfaceBusyError as exc:
            self.status_label.setText(f"ERROR: {exc}")
            return False

    def is_session_active(self):
        return bool(self._worker and self._worker.is_alive())

    def shutdown_session(self):
        self._collect_config()
        self._shutting_down = True
        if not self.is_session_active():
            self.channel_manager.release(self.session_channel, self._channel_owner)

    def _settings(self):
        preset = self.frequency_combo.currentData()
        if preset is not None:
            frequency = int(preset)
        else:
            text = self.frequency_combo.currentText().strip().lower()
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(mhz|khz|hz)?", text)
            if not match:
                raise ValueError(
                    "Clock must look like 1 MHz, 500 kHz, or 1000000 Hz."
                )
            value = float(match.group(1))
            unit = match.group(2)
            if unit == "mhz":
                frequency = round(value * 1_000_000)
            elif unit == "khz" or (unit is None and value <= 30_000):
                frequency = round(value * 1_000)
            else:
                frequency = round(value)
        dummy = parse_spi_hex(self.dummy_edit.text(), allow_empty=False)
        if len(dummy) != 1:
            raise ValueError("Dummy byte must be exactly one HEX byte (00–FF).")
        return SpiBusSettings(
            frequency=frequency,
            mode=int(self.mode_combo.currentData()),
            cs_count=self.cs_count_spin.value(),
            chip_select=int(self.chip_select_combo.currentData()),
            turbo=self.turbo_check.isChecked(),
        ), dummy[0]

    def _custom_transaction(self):
        _settings, dummy = self._settings()
        operation = self.operation_combo.currentData()
        tx = parse_spi_hex(self.tx_edit.text())
        return SpiTransaction(
            operation,
            tx=tx,
            read_length=self.rx_length_spin.value(),
            dummy_byte=dummy,
        )

    def _run_custom_transaction(self):
        try:
            transaction = self._custom_transaction()
        except ValueError as exc:
            self.status_label.setText(f"INVALID: {exc}")
            return
        self._start_transaction(transaction)

    def _run_loopback(self):
        try:
            _settings, dummy = self._settings()
            payload = parse_spi_hex(self.loopback_edit.text(), allow_empty=False)
            transaction = SpiTransaction(
                "loopback", tx=payload, read_length=len(payload), dummy_byte=dummy
            )
        except ValueError as exc:
            self.quick_result.setText(f"INVALID: {exc}")
            return
        self._start_transaction(transaction)

    def _run_jedec(self):
        try:
            _settings, _dummy = self._settings()
            transaction = SpiTransaction(
                "jedec", tx=b"\x9F", read_length=3, dummy_byte=0xFF
            )
        except ValueError as exc:
            self.quick_result.setText(f"INVALID: {exc}")
            return
        self._start_transaction(transaction)

    def _start_transaction(self, transaction):
        if self.is_session_active():
            return
        try:
            settings, _dummy = self._settings()
            self.channel_manager.acquire(
                self.session_channel, "SPI", self._channel_owner
            )
        except (ValueError, InterfaceBusyError) as exc:
            self._show_result_error(str(exc))
            return
        self._set_busy(True)
        self.status_label.setText(
            f"Running {OPERATION_LABELS[transaction.operation]}…"
        )
        url = f"{self.bound_bridge.base_url}/{self.session_interface}"
        self._worker = SpiTransactionWorker(
            url, settings, transaction, self.transaction_finished.emit
        )
        self._worker.start()

    def _transaction_done(self, result):
        self._worker = None
        self._set_busy(False)
        self._append_history(result)
        received = bytes(result.get("rx", b""))
        self.rx_hex.setText(format_spi_hex(received))
        self.rx_ascii.setText("".join(
            chr(value) if 32 <= value < 127 else "." for value in received
        ))
        status = result.get("status", "ERROR")
        details = result.get("details") or result.get("error") or ""
        clock = result.get("actual_frequency") or result.get("frequency", 0)
        summary = (
            f"{status}: RX {len(received)} B, actual clock {clock:g} Hz, "
            f"{result.get('duration_ms', 0.0):.2f} ms"
        )
        if details:
            summary += f" — {details}"
        self.status_label.setText(summary)
        if result.get("operation") in ("loopback", "jedec"):
            self.quick_result.setText(summary)
        if self._shutting_down:
            self.channel_manager.release(self.session_channel, self._channel_owner)

    def _append_history(self, result):
        serializable = dict(result)
        serializable["tx"] = format_spi_hex(result.get("tx", b""))
        serializable["rx"] = format_spi_hex(result.get("rx", b""))
        self._history.append(serializable)
        values = (
            str(result.get("timestamp", ""))[11:23],
            OPERATION_LABELS.get(result.get("operation"), result.get("operation", "")),
            str(result.get("mode", "")),
            f"{result.get('actual_frequency') or result.get('frequency', 0):g} Hz",
            str(result.get("chip_select", "")),
            serializable["tx"], serializable["rx"],
            str(result.get("status", "")),
            f"{result.get('duration_ms', 0.0):.2f} ms",
            str(result.get("details") or result.get("error") or ""),
        )
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in (2, 4, 7):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.history_table.setItem(row, column, item)

    def _export_history(self, output_format):
        if not self._history:
            QMessageBox.information(self, "SPI history", "There is no history to export.")
            return
        suffix = "json" if output_format == "json" else "csv"
        path, _selected = QFileDialog.getSaveFileName(
            self, "Export SPI history",
            f"spi-history-{datetime.now():%Y%m%d-%H%M%S}.{suffix}",
            "JSON (*.json)" if suffix == "json" else "CSV (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as stream:
                if suffix == "json":
                    json.dump(self._history, stream, indent=2, ensure_ascii=False)
                else:
                    writer = csv.DictWriter(stream, fieldnames=self._history[0].keys())
                    writer.writeheader()
                    writer.writerows(self._history)
            self.status_label.setText(f"History exported: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "SPI export error", str(exc))

    def _clear_history(self):
        self._history.clear()
        self.history_table.setRowCount(0)

    def _update_chip_selects(self):
        current = self.chip_select_combo.currentData()
        self.chip_select_combo.clear()
        for chip_select in range(self.cs_count_spin.value()):
            self.chip_select_combo.addItem(f"/CS{chip_select}", chip_select)
        index = self.chip_select_combo.findData(current)
        self.chip_select_combo.setCurrentIndex(max(0, index))

    def _update_operation_ui(self):
        operation = self.operation_combo.currentData()
        needs_tx = operation in ("write", "write_read", "duplex")
        needs_rx = operation in ("read", "write_read", "duplex")
        self.tx_edit.setEnabled(needs_tx)
        self.rx_length_spin.setEnabled(needs_rx)
        self.rx_length_label.setEnabled(needs_rx)
        if operation == "write":
            self.rx_length_spin.setValue(0)
        elif operation in ("read", "write_read") and self.rx_length_spin.value() == 0:
            self.rx_length_spin.setValue(1)
        self._update_wire_preview()

    def _update_wire_preview(self):
        try:
            self.wire_preview.setText(format_spi_hex(self._custom_transaction().wire_tx))
            self.wire_preview.setToolTip("")
        except (ValueError, AttributeError) as exc:
            self.wire_preview.clear()
            self.wire_preview.setToolTip(str(exc))

    def _set_busy(self, busy):
        self.run_btn.setEnabled(not busy)
        self.loopback_btn.setEnabled(not busy)
        self.jedec_btn.setEnabled(not busy)

    def _show_result_error(self, message):
        self.status_label.setText(f"ERROR: {message}")
        self.quick_result.setText(f"ERROR: {message}")

    def _load_config(self):
        frequency = int(self.config.get("spi_frequency", 1_000_000))
        index = self.frequency_combo.findData(frequency)
        if index >= 0:
            self.frequency_combo.setCurrentIndex(index)
        else:
            self.frequency_combo.setEditText(f"{frequency} Hz")
        mode = int(self.config.get("spi_mode", 0))
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(mode)))
        self.cs_count_spin.setValue(int(self.config.get("spi_cs_count", 1)))
        self._update_chip_selects()
        chip_select = int(self.config.get("spi_chip_select", 0))
        self.chip_select_combo.setCurrentIndex(
            max(0, self.chip_select_combo.findData(chip_select))
        )
        self.dummy_edit.setText(str(self.config.get("spi_dummy_byte", "00")))
        self.turbo_check.setChecked(bool(self.config.get("spi_turbo", False)))
        self.tx_edit.setText(str(self.config.get("spi_tx", "9F")))
        self.rx_length_spin.setValue(int(self.config.get("spi_rx_length", 3)))
        operation = str(self.config.get("spi_operation", "write_read"))
        index = self.operation_combo.findData(operation)
        self.operation_combo.setCurrentIndex(max(0, index))
        self.loopback_edit.setText(str(self.config.get(
            "spi_loopback_pattern", "00 FF AA 55 12 34 56 78"
        )))

    def _collect_config(self):
        try:
            settings, dummy = self._settings()
        except ValueError:
            settings, dummy = SpiBusSettings(), 0
        self.config.set("spi_frequency", settings.frequency)
        self.config.set("spi_mode", settings.mode)
        self.config.set("spi_cs_count", settings.cs_count)
        self.config.set("spi_chip_select", settings.chip_select)
        self.config.set("spi_dummy_byte", f"{dummy:02X}")
        self.config.set("spi_turbo", settings.turbo)
        self.config.set("spi_tx", self.tx_edit.text())
        self.config.set("spi_rx_length", self.rx_length_spin.value())
        self.config.set("spi_operation", self.operation_combo.currentData())
        self.config.set("spi_loopback_pattern", self.loopback_edit.text())
