"""Raw I2C, SMBus, diagnostics, and transaction-history user interface."""

import csv
from datetime import datetime
import json

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QHBoxLayout, QWidget,
)

from .i2c_bus import parse_hex_bytes, validate_7bit_address
from .i2c_value_codec import encode_i2c_value


class I2cTransactionLab(QWidget):
    """Build hardware-neutral transactions and retain an auditable history."""

    transaction_requested = pyqtSignal(dict)
    diagnostic_requested = pyqtSignal(str)

    HISTORY_FIELDS = (
        "timestamp", "protocol", "operation", "address", "tx", "rx",
        "status", "duration_ms", "details",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._busy = False
        root = QVBoxLayout(self)
        protocol_tabs = QTabWidget()
        protocol_tabs.addTab(self._build_raw_tab(), "Raw I²C")
        protocol_tabs.addTab(self._build_smbus_tab(), "SMBus")
        protocol_tabs.addTab(self._build_diagnostics_tab(), "Bus Diagnostics")
        root.addWidget(protocol_tabs)
        root.addWidget(self._build_history(), stretch=1)

    @staticmethod
    def _address_combo(default="0x50"):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setCurrentText(default)
        return combo

    @staticmethod
    def _parse_number(text, name):
        try:
            return int(str(text).strip(), 0)
        except ValueError as exc:
            raise ValueError(f"{name} must be decimal or 0x-prefixed hexadecimal.") from exc

    def _build_raw_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel("7-bit address:"), 0, 0)
        self.raw_address = self._address_combo()
        grid.addWidget(self.raw_address, 0, 1)
        grid.addWidget(QLabel("Transaction:"), 0, 2)
        self.raw_operation = QComboBox()
        self.raw_operation.addItem("Write", "write")
        self.raw_operation.addItem("Read", "read")
        self.raw_operation.addItem("Write → repeated START → Read", "write_read")
        self.raw_operation.addItem("Probe ACK (read)", "probe_read")
        self.raw_operation.addItem("Probe ACK (write)", "probe_write")
        self.raw_operation.currentIndexChanged.connect(self._update_raw_controls)
        grid.addWidget(self.raw_operation, 0, 3, 1, 3)
        grid.addWidget(QLabel("TX bytes (HEX):"), 1, 0)
        self.raw_tx = QLineEdit()
        self.raw_tx.setPlaceholderText("Example: 00 10 FF")
        grid.addWidget(self.raw_tx, 1, 1, 1, 3)
        grid.addWidget(QLabel("RX bytes:"), 1, 4)
        self.raw_read_length = QSpinBox()
        self.raw_read_length.setRange(0, 65535)
        self.raw_read_length.setValue(1)
        grid.addWidget(self.raw_read_length, 1, 5)
        self.raw_run = QPushButton("Execute transaction")
        self.raw_run.clicked.connect(self._request_raw)
        grid.addWidget(self.raw_run, 2, 0, 1, 2)
        note = QLabel(
            "Write+Read uses a repeated START and finishes with STOP. This is the "
            "usual transaction for devices that do not expose classic registers."
        )
        note.setWordWrap(True)
        grid.addWidget(note, 2, 2, 1, 4)
        self._update_raw_controls()
        return tab

    def _build_smbus_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel("7-bit address:"), 0, 0)
        self.smbus_address = self._address_combo()
        grid.addWidget(self.smbus_address, 0, 1)
        grid.addWidget(QLabel("Function:"), 0, 2)
        self.smbus_function = QComboBox()
        functions = (
            ("Quick Write", "quick_write"), ("Quick Read", "quick_read"),
            ("Send Byte", "send_byte"), ("Receive Byte", "receive_byte"),
            ("Write Byte Data", "write_byte"), ("Read Byte Data", "read_byte"),
            ("Write Word Data", "write_word"), ("Read Word Data", "read_word"),
            ("Process Call", "process_call"),
            ("Block Write", "block_write"), ("Block Read", "block_read"),
        )
        for label, value in functions:
            self.smbus_function.addItem(label, value)
        self.smbus_function.currentIndexChanged.connect(self._update_smbus_controls)
        grid.addWidget(self.smbus_function, 0, 3, 1, 3)
        grid.addWidget(QLabel("Command:"), 1, 0)
        self.smbus_command = QLineEdit("0x00")
        grid.addWidget(self.smbus_command, 1, 1)
        grid.addWidget(QLabel("Value/data:"), 1, 2)
        self.smbus_value = QLineEdit()
        self.smbus_value.setPlaceholderText("Value or HEX bytes")
        grid.addWidget(self.smbus_value, 1, 3)
        self.smbus_format = QComboBox()
        self.smbus_format.addItems(
            ["HEX bytes", "Decimal", "Hexadecimal", "Octal", "Binary"]
        )
        grid.addWidget(self.smbus_format, 1, 4)
        grid.addWidget(QLabel("Block max:"), 1, 5)
        self.smbus_block_max = QSpinBox()
        self.smbus_block_max.setRange(1, 32)
        self.smbus_block_max.setValue(32)
        grid.addWidget(self.smbus_block_max, 1, 6)
        self.smbus_pec = QCheckBox("PEC CRC-8")
        grid.addWidget(self.smbus_pec, 2, 0)
        self.smbus_run = QPushButton("Execute SMBus")
        self.smbus_run.clicked.connect(self._request_smbus)
        grid.addWidget(self.smbus_run, 2, 1)
        note = QLabel(
            "SMBus words use least-significant byte first. Block operations are "
            "limited by the SMBus specification to 32 data bytes."
        )
        note.setWordWrap(True)
        grid.addWidget(note, 2, 2, 1, 5)
        self._update_smbus_controls()
        return tab

    def _build_diagnostics_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        buttons = QHBoxLayout()
        self.check_bus_btn = QPushButton("Check SCL/SDA")
        self.check_bus_btn.clicked.connect(lambda: self.diagnostic_requested.emit("check"))
        buttons.addWidget(self.check_bus_btn)
        self.recover_bus_btn = QPushButton("Recover bus (up to 9 clocks + STOP)")
        self.recover_bus_btn.clicked.connect(self._confirm_recovery)
        buttons.addWidget(self.recover_bus_btn)
        buttons.addStretch()
        root.addLayout(buttons)
        self.diagnostic_status = QLabel(
            "Idle bus expected: SCL=HIGH and SDA=HIGH. Recovery only pulls lines "
            "low or releases them to the external pull-ups."
        )
        self.diagnostic_status.setWordWrap(True)
        root.addWidget(self.diagnostic_status)
        warning = QLabel(
            "Disconnect other masters before recovery. Clock stretching requires "
            "xDBUS7 connected to SCL; the normal wiring still joins xDBUS1+xDBUS2 for SDA."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#CC8800;")
        root.addWidget(warning)
        limit = QLabel(
            "Addressing: PyFtdi supports 7-bit I²C addresses only. 10-bit mode is "
            "shown as an explicit backend limitation rather than silently emulated."
        )
        limit.setWordWrap(True)
        root.addWidget(limit)
        return tab

    def _build_history(self):
        box = QGroupBox("Transaction history")
        root = QVBoxLayout(box)
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
        self.lab_status = QLabel("Ready.")
        actions.addWidget(self.lab_status, stretch=1)
        root.addLayout(actions)
        self.history_table = QTableWidget(0, 8)
        self.history_table.setHorizontalHeaderLabels(
            ["Time", "Protocol / operation", "Address", "TX", "RX", "Status", "ms", "Details"]
        )
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.history_table)
        return box

    def set_addresses(self, addresses):
        values = [f"0x{int(address):02X}" for address in addresses]
        for combo in (self.raw_address, self.smbus_address):
            current = combo.currentText()
            combo.clear()
            combo.addItems(values)
            selected = (
                current if current in values
                else values[0] if values
                else current or "0x50"
            )
            combo.setCurrentText(selected)

    def select_address(self, address):
        text = f"0x{int(address):02X}"
        self.raw_address.setCurrentText(text)
        self.smbus_address.setCurrentText(text)

    def _update_raw_controls(self):
        operation = self.raw_operation.currentData()
        self.raw_tx.setEnabled(operation in {"write", "write_read"})
        self.raw_read_length.setEnabled(operation in {"read", "write_read"})

    def _update_smbus_controls(self):
        function = self.smbus_function.currentData()
        uses_command = function not in {"quick_write", "quick_read", "send_byte", "receive_byte"}
        uses_value = function in {
            "send_byte", "write_byte", "write_word", "process_call",
            "block_write",
        }
        self.smbus_command.setEnabled(uses_command)
        self.smbus_value.setEnabled(uses_value)
        self.smbus_format.setEnabled(uses_value)
        self.smbus_block_max.setEnabled(function == "block_read")
        self.smbus_pec.setEnabled(function not in {"quick_write", "quick_read"})

    def _request_raw(self):
        try:
            address = validate_7bit_address(
                self._parse_number(self.raw_address.currentText(), "Address")
            )
            operation = self.raw_operation.currentData()
            payload = parse_hex_bytes(
                self.raw_tx.text(), allow_empty=operation not in {"write", "write_read"}
            )
            read_length = self.raw_read_length.value()
            if operation in {"read", "write_read"} and read_length < 1:
                raise ValueError("Read transactions require at least one RX byte.")
        except ValueError as exc:
            QMessageBox.warning(self, "Raw I2C transaction", str(exc))
            return
        self.set_busy(True)
        self.transaction_requested.emit({
            "protocol": "raw", "operation": operation, "address": address,
            "payload": payload, "read_length": read_length,
        })

    def _smbus_payload(self, function):
        if function not in {"send_byte", "write_byte", "write_word", "process_call", "block_write"}:
            return b""
        if function == "block_write":
            return parse_hex_bytes(self.smbus_value.text(), allow_empty=False)
        length = 2 if function in {"write_word", "process_call"} else 1
        return encode_i2c_value(
            self.smbus_value.text(), input_format=self.smbus_format.currentText(),
            length=length, byteorder="little", signed=False,
        )

    def _request_smbus(self):
        try:
            address = validate_7bit_address(
                self._parse_number(self.smbus_address.currentText(), "Address")
            )
            function = self.smbus_function.currentData()
            command = (
                self._parse_number(self.smbus_command.text(), "Command")
                if self.smbus_command.isEnabled() else 0
            )
            if not 0 <= command <= 0xFF:
                raise ValueError("SMBus command must fit in one byte.")
            payload = self._smbus_payload(function)
            if function == "block_write" and len(payload) > 32:
                raise ValueError("SMBus block writes allow at most 32 data bytes.")
        except ValueError as exc:
            QMessageBox.warning(self, "SMBus transaction", str(exc))
            return
        self.set_busy(True)
        self.transaction_requested.emit({
            "protocol": "smbus", "operation": function, "address": address,
            "command": command, "payload": payload,
            "read_length": self.smbus_block_max.value(),
            "pec": self.smbus_pec.isChecked(),
        })

    def _confirm_recovery(self):
        answer = QMessageBox.question(
            self, "Recover I2C bus",
            "Temporarily take control of SCL/SDA, issue up to 9 clock pulses, "
            "then generate STOP? Disconnect any other bus master first.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.set_busy(True)
            self.diagnostic_requested.emit("recover")

    def set_busy(self, busy):
        self._busy = bool(busy)
        for button in (
            self.raw_run, self.smbus_run, self.check_bus_btn, self.recover_bus_btn
        ):
            button.setEnabled(not busy)
        if busy:
            self.lab_status.setText("Transaction running…")

    def handle_result(self, result):
        self.set_busy(False)
        self._append_history(result)
        received = bytes(result.get("received", b""))
        detail = f"RX {len(received)} byte(s)" if received else "Completed"
        self.lab_status.setText(
            f"{result.get('status', 'ACK')}: {detail}; "
            f"actual clock {result.get('actual_frequency', 0) / 1000:g} kHz."
        )

    def handle_error(self, result):
        self.set_busy(False)
        self._append_history(result)
        self.lab_status.setText(
            f"{result.get('status', 'ERROR')}: {result.get('error', 'Unknown error')}"
        )

    def handle_diagnostic(self, result):
        self.set_busy(False)
        if "error" in result:
            self.diagnostic_status.setText(
                f"{result.get('status', 'ERROR')}: {result['error']}"
            )
            return
        after = result["after"]
        state = "BUS IDLE / HEALTHY" if result["healthy"] else "BUS STILL HELD"
        self.diagnostic_status.setText(
            f"{state} — SCL={'HIGH' if after['scl_high'] else 'LOW'}, "
            f"SDA={'HIGH' if after['sda_high'] else 'LOW'}, "
            f"recovery clocks={result['pulses']}."
        )

    def _append_history(self, result):
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        payload = bytes(result.get("payload", b""))
        received = bytes(result.get("received", b""))
        protocol = str(result.get("protocol", "diagnostic")).upper()
        operation = str(result.get("operation", ""))
        command_operations = {
            "write_byte", "read_byte", "write_word", "read_word",
            "process_call", "block_write", "block_read",
        }
        transmitted = payload
        details = []
        if protocol == "SMBUS" and operation in command_operations:
            command = int(result.get("command", 0))
            transmitted = bytes((command,)) + transmitted
            details.append(f"command=0x{command:02X}")
        if result.get("pec"):
            details.append("PEC enabled")
        if result.get("error"):
            details.append(str(result["error"]))
        record = {
            "timestamp": timestamp,
            "protocol": protocol,
            "operation": operation,
            "address": f"0x{int(result.get('address', 0)):02X}",
            "tx": transmitted.hex(" ").upper(),
            "rx": received.hex(" ").upper(),
            "status": str(result.get("status", "ERROR")),
            "duration_ms": round(float(result.get("duration_ms", 0.0)), 3),
            "details": "; ".join(details),
        }
        self._history.append(record)
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        values = (
            timestamp.split("T")[-1], f"{record['protocol']} / {record['operation']}",
            record["address"], record["tx"], record["rx"], record["status"],
            f"{record['duration_ms']:.3f}", record["details"],
        )
        for column, value in enumerate(values):
            self.history_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.history_table.scrollToBottom()

    def _clear_history(self):
        self._history.clear()
        self.history_table.setRowCount(0)
        self.lab_status.setText("History cleared.")

    def _export_history(self, output_format):
        if not self._history:
            QMessageBox.information(self, "Transaction history", "Run a transaction first.")
            return
        extension = output_format.lower()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export I2C history", f"i2c-transactions.{extension}",
            "CSV (*.csv)" if extension == "csv" else "JSON (*.json)",
        )
        if not path:
            return
        try:
            if extension == "csv":
                with open(path, "w", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=self.HISTORY_FIELDS)
                    writer.writeheader()
                    writer.writerows(self._history)
            else:
                with open(path, "w", encoding="utf-8") as output:
                    json.dump(self._history, output, indent=2, ensure_ascii=False)
            self.lab_status.setText(f"Exported {len(self._history)} transaction(s): {path}")
        except OSError as exc:
            QMessageBox.critical(self, "History export error", str(exc))
