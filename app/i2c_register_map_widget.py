"""PyQt register-map editor and runner for generic I2C devices."""

import csv
from datetime import datetime
import json

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget,
)

from .i2c_register_map import I2cDeviceProfile, RegisterDefinition, parse_int
from .i2c_value_codec import decode_i2c_value, encode_i2c_value


class I2cRegisterMapWidget(QWidget):
    """Edit, execute, save, and load a datasheet-derived register map.

    The widget emits hardware-neutral request dictionaries. Its owner performs
    the FTDI transaction and returns the result with the original request.
    """

    read_requested = pyqtSignal(dict)
    write_requested = pyqtSignal(dict)

    COLUMNS = (
        "Name", "Register", "Bytes", "Access", "Data endian", "Signed",
        "Bits", "Shift", "Mask", "Scale", "Offset", "Unit", "Raw", "Value",
    )
    RAW_COLUMN = 12
    VALUE_COLUMN = 13

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._read_queue = []
        self._sequence_total = 0
        self._sequence_completed = 0
        self._samples = []
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_register_map)
        self._build_ui()
        self.new_profile()

    def _build_ui(self):
        root = QVBoxLayout(self)
        profile = QGridLayout()
        profile.addWidget(QLabel("Profile name:"), 0, 0)
        self.profile_name = QLineEdit()
        profile.addWidget(self.profile_name, 0, 1)
        profile.addWidget(QLabel("Device address:"), 0, 2)
        self.device_address = QComboBox()
        self.device_address.setEditable(True)
        profile.addWidget(self.device_address, 0, 3)
        profile.addWidget(QLabel("Register address:"), 0, 4)
        self.register_width = QComboBox()
        self.register_width.addItem("8-bit", 1)
        self.register_width.addItem("16-bit", 2)
        profile.addWidget(self.register_width, 0, 5)
        self.register_endian = QComboBox()
        self.register_endian.addItems(["Big endian", "Little endian"])
        profile.addWidget(self.register_endian, 0, 6)

        new_btn = QPushButton("New")
        new_btn.clicked.connect(self.new_profile)
        profile.addWidget(new_btn, 1, 0)
        example_btn = QPushButton("TMP102 example")
        example_btn.clicked.connect(self.load_tmp102_example)
        profile.addWidget(example_btn, 1, 1)
        load_btn = QPushButton("Load profile")
        load_btn.clicked.connect(self._load_profile_file)
        profile.addWidget(load_btn, 1, 2)
        save_btn = QPushButton("Save profile")
        save_btn.clicked.connect(self._save_profile_file)
        profile.addWidget(save_btn, 1, 3)
        root.addLayout(profile)

        actions = QHBoxLayout()
        add_btn = QPushButton("+ Register")
        add_btn.clicked.connect(self.add_register)
        actions.addWidget(add_btn)
        delete_btn = QPushButton("Delete selected")
        delete_btn.clicked.connect(self.delete_selected)
        actions.addWidget(delete_btn)
        self.read_selected_btn = QPushButton("Read selected")
        self.read_selected_btn.clicked.connect(self.read_selected)
        actions.addWidget(self.read_selected_btn)
        self.read_all_btn = QPushButton("Read all")
        self.read_all_btn.clicked.connect(self.read_all)
        actions.addWidget(self.read_all_btn)
        actions.addWidget(QLabel("Raw write value:"))
        self.write_value = QLineEdit()
        self.write_value.setPlaceholderText("FF, 255, text...")
        actions.addWidget(self.write_value, stretch=1)
        self.write_format = QComboBox()
        self.write_format.addItems(
            ["HEX bytes", "Decimal", "Hexadecimal", "Octal", "Binary", "ASCII"]
        )
        actions.addWidget(self.write_format)
        self.write_selected_btn = QPushButton("Write selected")
        self.write_selected_btn.clicked.connect(self.write_selected)
        actions.addWidget(self.write_selected_btn)
        root.addLayout(actions)

        monitoring = QHBoxLayout()
        self.poll_enabled = QCheckBox("Poll Read all")
        self.poll_enabled.toggled.connect(self._toggle_polling)
        monitoring.addWidget(self.poll_enabled)
        monitoring.addWidget(QLabel("Interval (ms):"))
        self.poll_interval = QSpinBox()
        self.poll_interval.setRange(100, 60000)
        self.poll_interval.setValue(1000)
        self.poll_interval.valueChanged.connect(self._update_poll_interval)
        monitoring.addWidget(self.poll_interval)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        monitoring.addWidget(export_btn)
        self.sample_count = QLabel("Samples: 0")
        monitoring.addWidget(self.sample_count)
        monitoring.addStretch()
        root.addLayout(monitoring)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            self.VALUE_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        root.addWidget(self.table, stretch=1)
        explanation = QLabel(
            "Each row comes from the datasheet. Scale and Offset use: "
            "physical value = decoded integer × scale + offset."
        )
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    @staticmethod
    def _item(value, editable=True):
        item = QTableWidgetItem(str(value))
        if not editable:
            item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def add_register(self, register=None):
        """Append a register definition, or a safe editable default."""
        register = register or RegisterDefinition(name="New register", address=0)
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = (
            register.name, f"0x{register.address:X}", register.length,
            register.access, "BE" if register.byteorder == "big" else "LE",
            "Yes" if register.signed else "No", register.bit_width,
            register.right_shift,
            "" if register.mask is None else f"0x{register.mask:X}",
            f"{register.scale:g}", f"{register.offset:g}", register.unit, "", "",
        )
        for column, value in enumerate(values):
            self.table.setItem(
                row, column,
                self._item(value, editable=column < self.RAW_COLUMN),
            )
        self.table.selectRow(row)

    def delete_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    @property
    def is_busy(self):
        """Whether a map read/write sequence is waiting for hardware."""
        return self._busy

    def stop_polling(self):
        """Stop periodic map reads while preserving the current results."""
        self.poll_enabled.setChecked(False)

    def set_addresses(self, addresses):
        values = [f"0x{int(address):02X}" for address in addresses]
        current = self.device_address.currentText()
        self.device_address.clear()
        self.device_address.addItems(values)
        if values:
            self.device_address.setCurrentText(current if current in values else values[0])
        else:
            self.device_address.setCurrentText(current or "0x50")

    def select_address(self, address):
        self.device_address.setCurrentText(f"0x{int(address):02X}")

    def profile(self):
        """Validate the editor and return its immutable profile model."""
        registers = []
        for row in range(self.table.rowCount()):
            try:
                text = lambda column: self.table.item(row, column).text().strip()
                length = parse_int(text(2), "Length")
                mask_text = text(8)
                endian = text(4).lower()
                if endian not in {"be", "big", "big endian", "le", "little", "little endian"}:
                    raise ValueError("Data endian must be BE or LE.")
                signed_text = text(5).lower()
                if signed_text not in {"yes", "no", "true", "false", "1", "0"}:
                    raise ValueError("Signed must be Yes or No.")
                registers.append(RegisterDefinition(
                    name=text(0),
                    address=parse_int(text(1), "Register address"),
                    length=length,
                    access=text(3).upper(),
                    byteorder="big" if endian in {"be", "big", "big endian"} else "little",
                    signed=signed_text in {"yes", "true", "1"},
                    bit_width=parse_int(text(6), "Value bits"),
                    right_shift=parse_int(text(7), "Right shift"),
                    mask=None if not mask_text else parse_int(mask_text, "Mask"),
                    scale=float(text(9)), offset=float(text(10)), unit=text(11),
                ))
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"Row {row + 1}: {exc}") from exc
        return I2cDeviceProfile(
            name=self.profile_name.text().strip(),
            device_address=parse_int(
                self.device_address.currentText(), "Device address"
            ),
            register_width=int(self.register_width.currentData()),
            register_big_endian=self.register_endian.currentIndex() == 0,
            registers=tuple(registers),
        )

    def load_profile(self, profile):
        """Replace editor contents with a validated device profile."""
        if not isinstance(profile, I2cDeviceProfile):
            profile = I2cDeviceProfile.from_dict(profile)
        self.profile_name.setText(profile.name)
        self.device_address.setCurrentText(f"0x{profile.device_address:02X}")
        self.register_width.setCurrentIndex(0 if profile.register_width == 1 else 1)
        self.register_endian.setCurrentIndex(0 if profile.register_big_endian else 1)
        self.table.setRowCount(0)
        for register in profile.registers:
            self.add_register(register)
        self._samples.clear()
        self.sample_count.setText("Samples: 0")
        self.status.setText(f"Profile loaded: {profile.name}")

    def new_profile(self):
        self.load_profile(I2cDeviceProfile(
            name="New I2C Device", device_address=0x50,
            registers=(RegisterDefinition(name="Register 0", address=0),),
        ))

    def load_tmp102_example(self):
        temperature = dict(
            length=2, access="R", byteorder="big", signed=True,
            bit_width=12, right_shift=4, scale=0.0625, unit="°C",
        )
        self.load_profile(I2cDeviceProfile(
            name="TMP102 Example", device_address=0x48,
            registers=(
                RegisterDefinition(name="Temperature", address=0x00, **temperature),
                RegisterDefinition(
                    name="Configuration", address=0x01, length=2, access="RW",
                    bit_width=16,
                ),
                RegisterDefinition(name="TLOW", address=0x02, **{
                    **temperature, "access": "RW"
                }),
                RegisterDefinition(name="THIGH", address=0x03, **{
                    **temperature, "access": "RW"
                }),
            ),
        ))

    def _save_profile_file(self):
        try:
            profile = self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "Register Map", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save I2C register map", f"{profile.name}.i2cmap.json",
            "I2C register map (*.i2cmap.json);;JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as output:
                json.dump(profile.to_dict(), output, indent=2, ensure_ascii=False)
            self.status.setText(f"Profile saved: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Save profile error", str(exc))

    def _load_profile_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load I2C register map", "",
            "I2C register map (*.i2cmap.json *.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as source:
                self.load_profile(I2cDeviceProfile.from_dict(json.load(source)))
            self.status.setText(f"Profile loaded: {path}")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            QMessageBox.critical(self, "Load profile error", str(exc))

    def _selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            raise ValueError("Select one register row first.")
        return row

    def _request_for_row(self, row, profile=None):
        profile = profile or self.profile()
        register = profile.registers[row]
        return {
            "source": "register_map", "row": row,
            "address": profile.device_address,
            "register": register.address,
            "register_width": profile.register_width,
            "big_endian": profile.register_big_endian,
            "length": register.length,
            "decode": {
                "byteorder": register.byteorder, "signed": register.signed,
                "bit_width": register.bit_width,
                "right_shift": register.right_shift, "mask": register.mask,
                "scale": register.scale, "offset": register.offset,
                "unit": register.unit, "name": register.name,
            },
        }

    def read_selected(self):
        try:
            row = self._selected_row()
            profile = self.profile()
            if "R" not in profile.registers[row].access:
                raise ValueError("The selected register is not marked as readable.")
        except ValueError as exc:
            QMessageBox.warning(self, "Register Map", str(exc))
            return
        self._start_read_rows([row])

    def read_all(self):
        try:
            profile = self.profile()
            rows = [
                row for row, register in enumerate(profile.registers)
                if "R" in register.access
            ]
            if not rows:
                raise ValueError("The profile has no readable registers.")
        except ValueError as exc:
            QMessageBox.warning(self, "Register Map", str(exc))
            return
        self._start_read_rows(rows)

    def _start_read_rows(self, rows):
        if self._busy:
            self.status.setText("A register-map operation is already running.")
            return
        self._read_queue = list(rows)
        self._sequence_total = len(rows)
        self._sequence_completed = 0
        self._emit_next_read()

    def _emit_next_read(self):
        if not self._read_queue:
            self._busy = False
            self.status.setText(
                f"Read complete: {self._sequence_completed} register(s)."
            )
            return
        try:
            row = self._read_queue.pop(0)
            request = self._request_for_row(row)
        except ValueError as exc:
            self.handle_error(str(exc))
            return
        self._busy = True
        self.status.setText(
            f"Reading {request['decode']['name']} "
            f"({self._sequence_completed + 1}/{self._sequence_total})…"
        )
        self.read_requested.emit(request)

    def write_selected(self):
        if self._busy:
            self.status.setText("A register-map operation is already running.")
            return
        try:
            row = self._selected_row()
            profile = self.profile()
            register = profile.registers[row]
            if "W" not in register.access:
                raise ValueError("The selected register is not marked as writable.")
            request = self._request_for_row(row, profile)
            request["payload"] = encode_i2c_value(
                self.write_value.text(), input_format=self.write_format.currentText(),
                length=register.length, byteorder=register.byteorder,
                signed=register.signed,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Register Map", str(exc))
            return
        answer = QMessageBox.question(
            self, "Confirm register write",
            f"Write {request['payload'].hex(' ').upper()} to "
            f"{register.name} (0x{register.address:X})?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._busy = True
        self._read_queue.clear()
        self.status.setText(f"Writing {register.name}…")
        self.write_requested.emit(request)

    def handle_transaction_result(self, operation, data, request):
        """Update the originating row and continue a queued Read all."""
        row = int(request["row"])
        decode = request["decode"]
        if operation == "write":
            self._busy = False
            raw = request.get("payload", b"").hex(" ").upper()
            self.table.setItem(row, self.RAW_COLUMN, self._item(raw, editable=False))
            self.table.setItem(row, self.VALUE_COLUMN, self._item("Written (ACK)", editable=False))
            self.status.setText(f"Write completed: {decode['name']}.")
            return
        try:
            decoded = decode_i2c_value(
                data, byteorder=decode["byteorder"], signed=decode["signed"],
                bit_width=decode["bit_width"], right_shift=decode["right_shift"],
                mask=decode["mask"], scale=decode["scale"], offset=decode["offset"],
            )
        except ValueError as exc:
            self.handle_error(f"{decode['name']}: {exc}")
            return
        unit = decode["unit"]
        value = f"{decoded.scaled:g}{(' ' + unit) if unit else ''}"
        raw_item = self._item(decoded.raw_hex, editable=False)
        raw_item.setToolTip(
            f"Unsigned: {decoded.unsigned}\nSigned: {decoded.signed}\n"
            f"HEX: {decoded.hexadecimal}\nOctal: {decoded.octal}\n"
            f"Binary: {decoded.binary}\nASCII: {decoded.ascii}"
        )
        self.table.setItem(row, self.RAW_COLUMN, raw_item)
        self.table.setItem(row, self.VALUE_COLUMN, self._item(value, editable=False))
        self._sequence_completed += 1
        self._samples.append({
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "profile": self.profile_name.text().strip(),
            "device_address": self.device_address.currentText(),
            "name": decode["name"], "register": f"0x{request['register']:X}",
            "raw": decoded.raw_hex, "unsigned": decoded.unsigned,
            "signed": decoded.signed, "scaled": decoded.scaled, "unit": unit,
        })
        self.sample_count.setText(f"Samples: {len(self._samples)}")
        QTimer.singleShot(0, self._emit_next_read)

    def handle_error(self, error):
        self._busy = False
        self._read_queue.clear()
        self.status.setText(f"ERROR: {error}")

    def _toggle_polling(self, enabled):
        if enabled:
            self._poll_timer.start(self.poll_interval.value())
            self._poll_register_map()
        else:
            self._poll_timer.stop()

    def _update_poll_interval(self, value):
        if self._poll_timer.isActive():
            self._poll_timer.start(value)

    def _poll_register_map(self):
        if not self._busy:
            self.read_all()

    def _export_csv(self):
        if not self._samples:
            QMessageBox.information(
                self, "Register Map", "Read at least one register before exporting."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export register samples", "i2c-registers.csv", "CSV (*.csv)"
        )
        if not path:
            return
        fields = (
            "timestamp", "profile", "device_address", "name", "register",
            "raw", "unsigned", "signed", "scaled", "unit",
        )
        try:
            with open(path, "w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader()
                writer.writerows(self._samples)
            self.status.setText(f"Exported {len(self._samples)} sample(s): {path}")
        except OSError as exc:
            QMessageBox.critical(self, "CSV export error", str(exc))
