"""Reusable PyQt widgets for generic I2C registers, sensors, and memories."""

from statistics import mean

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QTabWidget,
    QFileDialog, QMessageBox, QAbstractItemView,
)

from .i2c_value_codec import decode_i2c_value, encode_i2c_value
from .i2c_register_map_widget import I2cRegisterMapWidget


class I2cDeviceInspector(QWidget):
    """Generic I2C debugging panel with register and memory tools.

    Hardware access is delegated to the containing window through request
    signals, so this widget remains independent from PyFtdi and shares the
    application's single-operation I2C lock.
    """

    register_read_requested = pyqtSignal(dict)
    register_write_requested = pyqtSignal(dict)
    memory_read_requested = pyqtSignal(dict)
    memory_write_requested = pyqtSignal(dict)

    SENSOR_PRESETS = {
        "TMP102 temperature": {
            "register": "0x00", "length": 2, "bits": 12, "shift": 4,
            "signed": True, "scale": 0.0625, "offset": 0.0, "unit": "°C",
        },
        "LM75 temperature": {
            "register": "0x00", "length": 2, "bits": 9, "shift": 7,
            "signed": True, "scale": 0.5, "offset": 0.0, "unit": "°C",
        },
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._addresses = []
        self._poll_pending = False
        self._live_values = []
        self._memory_data = b""
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_register)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_register_tab(), "Register / Sensor")
        self.register_map = I2cRegisterMapWidget()
        self.register_map.read_requested.connect(self._forward_register_map_read)
        self.register_map.write_requested.connect(self._forward_register_map_write)
        tabs.addTab(self.register_map, "Register Map")
        tabs.addTab(self._build_memory_tab(), "Memory Viewer")
        root.addWidget(tabs)

    @staticmethod
    def _address_combo(default="0x50"):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setCurrentText(default)
        return combo

    @staticmethod
    def _parse_number(text, name):
        try:
            return int(text.strip(), 0)
        except ValueError as exc:
            raise ValueError(f"{name} must be decimal or hexadecimal (0x...).") from exc

    def _build_register_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        box = QGroupBox("Register transaction")
        grid = QGridLayout(box)
        grid.addWidget(QLabel("Device address:"), 0, 0)
        self.reg_address = self._address_combo()
        grid.addWidget(self.reg_address, 0, 1)
        grid.addWidget(QLabel("Register:"), 0, 2)
        self.reg_register = QLineEdit("0x00")
        grid.addWidget(self.reg_register, 0, 3)
        grid.addWidget(QLabel("Register size:"), 0, 4)
        self.reg_width = QComboBox()
        self.reg_width.addItem("8-bit", 1)
        self.reg_width.addItem("16-bit", 2)
        grid.addWidget(self.reg_width, 0, 5)
        grid.addWidget(QLabel("Byte order:"), 0, 6)
        self.reg_endian = QComboBox()
        self.reg_endian.addItems(["Big endian", "Little endian"])
        grid.addWidget(self.reg_endian, 0, 7)

        grid.addWidget(QLabel("Preset:"), 1, 0)
        self.reg_preset = QComboBox()
        self.reg_preset.addItem("Raw / custom")
        self.reg_preset.addItems(self.SENSOR_PRESETS)
        self.reg_preset.currentTextChanged.connect(self._apply_sensor_preset)
        grid.addWidget(self.reg_preset, 1, 1, 1, 2)

        grid.addWidget(QLabel("Read bytes:"), 1, 3)
        self.reg_length = QSpinBox()
        self.reg_length.setRange(1, 8)
        self.reg_length.setValue(2)
        self.reg_length.valueChanged.connect(self._sync_value_bits)
        grid.addWidget(self.reg_length, 1, 4)
        self.reg_read_btn = QPushButton("Read register")
        self.reg_read_btn.clicked.connect(self._read_register)
        grid.addWidget(self.reg_read_btn, 1, 5)
        self.reg_signed = QCheckBox("Signed")
        grid.addWidget(self.reg_signed, 1, 6)
        grid.addWidget(QLabel("Value bits:"), 2, 0)
        self.reg_value_bits = QSpinBox()
        self.reg_value_bits.setRange(1, 64)
        self.reg_value_bits.setValue(16)
        grid.addWidget(self.reg_value_bits, 2, 1)
        grid.addWidget(QLabel("Right shift:"), 2, 2)
        self.reg_shift = QSpinBox()
        self.reg_shift.setRange(0, 63)
        grid.addWidget(self.reg_shift, 2, 3)

        grid.addWidget(QLabel("Mask:"), 2, 4)
        self.reg_mask = QLineEdit()
        self.reg_mask.setPlaceholderText("automatic")
        grid.addWidget(self.reg_mask, 2, 5)
        grid.addWidget(QLabel("Scale:"), 3, 0)
        self.reg_scale = QDoubleSpinBox()
        self.reg_scale.setRange(-1e9, 1e9)
        self.reg_scale.setDecimals(8)
        self.reg_scale.setValue(1.0)
        grid.addWidget(self.reg_scale, 3, 1)
        grid.addWidget(QLabel("Offset:"), 3, 2)
        self.reg_offset = QDoubleSpinBox()
        self.reg_offset.setRange(-1e9, 1e9)
        self.reg_offset.setDecimals(8)
        grid.addWidget(self.reg_offset, 3, 3)
        grid.addWidget(QLabel("Unit:"), 3, 4)
        self.reg_unit = QLineEdit()
        self.reg_unit.setPlaceholderText("°C, V, Pa...")
        grid.addWidget(self.reg_unit, 3, 5)

        grid.addWidget(QLabel("Write value:"), 4, 0)
        self.reg_write_value = QLineEdit()
        self.reg_write_value.setPlaceholderText("Example: 01 FF")
        grid.addWidget(self.reg_write_value, 4, 1, 1, 3)
        self.reg_write_format = QComboBox()
        self.reg_write_format.addItems(
            ["HEX bytes", "Decimal", "Hexadecimal", "Octal", "Binary", "ASCII"]
        )
        grid.addWidget(self.reg_write_format, 4, 4, 1, 2)
        self.reg_write_btn = QPushButton("Write register")
        self.reg_write_btn.clicked.connect(self._write_register)
        grid.addWidget(self.reg_write_btn, 4, 6, 1, 2)
        pipeline = QLabel(
            "Decode order: bytes → byte order → right shift → mask/value bits "
            "→ signed/unsigned → scale → offset."
        )
        pipeline.setWordWrap(True)
        grid.addWidget(pipeline, 5, 0, 1, 8)
        root.addWidget(box)

        live = QHBoxLayout()
        self.live_enabled = QCheckBox("Live polling")
        self.live_enabled.toggled.connect(self._toggle_polling)
        live.addWidget(self.live_enabled)
        live.addWidget(QLabel("Interval (ms):"))
        self.live_interval = QSpinBox()
        self.live_interval.setRange(50, 60000)
        self.live_interval.setValue(1000)
        self.live_interval.valueChanged.connect(self._update_poll_interval)
        live.addWidget(self.live_interval)
        self.live_stats = QLabel("Samples: 0")
        live.addWidget(self.live_stats)
        live.addStretch()
        root.addLayout(live)

        self.value_table = QTableWidget(0, 2)
        self.value_table.setHorizontalHeaderLabels(["Representation", "Value"])
        self.value_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.value_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.value_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.value_table, stretch=1)
        self.reg_status = QLabel("Ready.")
        root.addWidget(self.reg_status)
        return tab

    def _build_memory_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        config = QGridLayout()
        config.addWidget(QLabel("Device address:"), 0, 0)
        self.mem_address = self._address_combo()
        config.addWidget(self.mem_address, 0, 1)
        config.addWidget(QLabel("Start address:"), 0, 2)
        self.mem_start = QLineEdit("0x0000")
        config.addWidget(self.mem_start, 0, 3)
        config.addWidget(QLabel("Address size:"), 0, 4)
        self.mem_reg_width = QComboBox()
        self.mem_reg_width.addItem("8-bit", 1)
        self.mem_reg_width.addItem("16-bit", 2)
        self.mem_reg_width.setCurrentIndex(1)
        config.addWidget(self.mem_reg_width, 0, 5)
        config.addWidget(QLabel("Length:"), 0, 6)
        self.mem_length = QSpinBox()
        self.mem_length.setRange(1, 65536)
        self.mem_length.setValue(256)
        config.addWidget(self.mem_length, 0, 7)
        config.addWidget(QLabel("Page size:"), 1, 0)
        self.mem_page_size = QSpinBox()
        self.mem_page_size.setRange(1, 1024)
        self.mem_page_size.setValue(16)
        config.addWidget(self.mem_page_size, 1, 1)
        config.addWidget(QLabel("Write delay (ms):"), 1, 2)
        self.mem_write_delay = QSpinBox()
        self.mem_write_delay.setRange(0, 1000)
        self.mem_write_delay.setValue(10)
        config.addWidget(self.mem_write_delay, 1, 3)
        self.mem_read_btn = QPushButton("Read memory")
        self.mem_read_btn.clicked.connect(self._read_memory)
        config.addWidget(self.mem_read_btn, 1, 4)
        load_btn = QPushButton("Load BIN")
        load_btn.clicked.connect(self._load_binary)
        config.addWidget(load_btn, 1, 5)
        save_btn = QPushButton("Save BIN")
        save_btn.clicked.connect(self._save_binary)
        config.addWidget(save_btn, 1, 6)
        self.mem_write_btn = QPushButton("Write + verify")
        self.mem_write_btn.clicked.connect(self._write_memory)
        config.addWidget(self.mem_write_btn, 1, 7)
        root.addLayout(config)

        self.memory_table = QTableWidget(0, 16)
        self.memory_table.setHorizontalHeaderLabels([f"{value:X}" for value in range(16)])
        self.memory_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.memory_table, stretch=1)
        self.memory_ascii = QTextEdit()
        self.memory_ascii.setReadOnly(True)
        self.memory_ascii.setMaximumHeight(70)
        root.addWidget(self.memory_ascii)
        self.mem_status = QLabel("Memory writes require confirmation and are verified after writing.")
        root.addWidget(self.mem_status)
        return tab

    def set_addresses(self, addresses):
        """Populate both device selectors with scanner results."""
        values = [f"0x{int(address):02X}" for address in addresses]
        self._addresses = values
        for combo in (self.reg_address, self.mem_address):
            current = combo.currentText()
            combo.clear()
            combo.addItems(values)
            if values:
                combo.setCurrentText(current if current in values else values[0])
            else:
                combo.setCurrentText(current or "0x50")
        self.register_map.set_addresses(addresses)

    def select_address(self, address):
        """Select one scanner result in both register and memory tools."""
        selected = f"0x{int(address):02X}"
        self.reg_address.setCurrentText(selected)
        self.mem_address.setCurrentText(selected)
        self.register_map.select_address(address)

    def _apply_sensor_preset(self, name):
        """Load datasheet parameters for a simple linear sensor format."""
        preset = self.SENSOR_PRESETS.get(name)
        if not preset:
            return
        self.reg_register.setText(preset["register"])
        self.reg_endian.setCurrentIndex(0)
        self.reg_length.setValue(preset["length"])
        self.reg_value_bits.setValue(preset["bits"])
        self.reg_shift.setValue(preset["shift"])
        self.reg_mask.clear()
        self.reg_signed.setChecked(preset["signed"])
        self.reg_scale.setValue(preset["scale"])
        self.reg_offset.setValue(preset["offset"])
        self.reg_unit.setText(preset["unit"])
        self.reg_status.setText(f"Preset loaded: {name}. Confirm it against your datasheet.")

    def _common_register_request(self):
        address = self._parse_number(self.reg_address.currentText(), "Device address")
        register = self._parse_number(self.reg_register.text(), "Register")
        if not 0x03 <= address <= 0x77:
            raise ValueError("Device address must be from 0x03 to 0x77.")
        width = int(self.reg_width.currentData())
        if not 0 <= register < (1 << (width * 8)):
            raise ValueError(f"Register does not fit in {width * 8} bits.")
        return {
            "source": "register",
            "address": address, "register": register, "register_width": width,
            "big_endian": self.reg_endian.currentIndex() == 0,
            "length": self.reg_length.value(),
        }

    def _read_register(self):
        if self.register_map.is_busy:
            self.reg_status.setText("Wait for the Register Map operation to finish.")
            return
        self.register_map.stop_polling()
        try:
            request = self._common_register_request()
        except ValueError as exc:
            QMessageBox.warning(self, "Register Inspector", str(exc))
            return
        self._poll_pending = True
        self.reg_status.setText("Reading register…")
        self.register_read_requested.emit(request)

    def _write_register(self):
        if self.register_map.is_busy:
            self.reg_status.setText("Wait for the Register Map operation to finish.")
            return
        self.register_map.stop_polling()
        try:
            request = self._common_register_request()
            request["payload"] = encode_i2c_value(
                self.reg_write_value.text(),
                input_format=self.reg_write_format.currentText(),
                length=request["length"],
                byteorder="big" if request["big_endian"] else "little",
                signed=self.reg_signed.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Register Inspector", str(exc))
            return
        self.reg_status.setText("Writing register…")
        self.register_write_requested.emit(request)

    def handle_register_result(self, operation, data, request=None):
        if request and request.get("source") == "register_map":
            self.register_map.handle_transaction_result(operation, data, request)
            return
        self._poll_pending = False
        if operation == "write":
            self.reg_status.setText("Write completed (ACK).")
            return
        try:
            mask = self._parse_number(self.reg_mask.text(), "Mask") if self.reg_mask.text().strip() else None
            decoded = decode_i2c_value(
                data,
                byteorder="big" if self.reg_endian.currentIndex() == 0 else "little",
                signed=self.reg_signed.isChecked(),
                bit_width=self.reg_value_bits.value(),
                right_shift=self.reg_shift.value(), mask=mask,
                scale=self.reg_scale.value(), offset=self.reg_offset.value(),
            )
        except ValueError as exc:
            self.reg_status.setText(f"Decode error: {exc}")
            return
        unit = self.reg_unit.text().strip()
        rows = (
            ("Raw bytes", decoded.raw_hex), ("Unsigned decimal", str(decoded.unsigned)),
            ("Signed decimal", str(decoded.signed)), ("Hexadecimal", decoded.hexadecimal),
            ("Octal", decoded.octal), ("Binary", decoded.binary),
            ("ASCII", decoded.ascii),
            ("Scaled value", f"{decoded.scaled:g}{(' ' + unit) if unit else ''}"),
        )
        self.value_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            self.value_table.setItem(row, 0, QTableWidgetItem(name))
            self.value_table.setItem(row, 1, QTableWidgetItem(value))
        self.reg_status.setText(f"Read {len(data)} byte(s) successfully.")
        self._live_values.append(decoded.scaled)
        if len(self._live_values) > 10000:
            self._live_values = self._live_values[-10000:]
        self.live_stats.setText(
            f"Samples: {len(self._live_values)}  Min: {min(self._live_values):g}  "
            f"Max: {max(self._live_values):g}  Avg: {mean(self._live_values):g}"
        )

    def handle_error(self, error):
        self._poll_pending = False
        self.reg_status.setText(f"ERROR: {error}")
        self.mem_status.setText(f"ERROR: {error}")
        self.register_map.handle_error(error)

    def handle_operation_error(self, error, request):
        """Route an error only to the inspector tool that started the request."""
        source = request.get("source") if request else None
        if source == "register_map":
            self.register_map.handle_error(error)
        elif source == "memory":
            self.mem_status.setText(f"ERROR: {error}")
        else:
            self._poll_pending = False
            self.reg_status.setText(f"ERROR: {error}")

    def pause_polling(self):
        """Stop both polling modes before another I2C tool takes the bus."""
        self.live_enabled.setChecked(False)
        self.register_map.stop_polling()

    def _forward_register_map_read(self, request):
        self.live_enabled.setChecked(False)
        if self._poll_pending:
            self.register_map.handle_error(
                "Wait for the current Register / Sensor read to finish."
            )
            return
        self.register_read_requested.emit(request)

    def _forward_register_map_write(self, request):
        self.live_enabled.setChecked(False)
        if self._poll_pending:
            self.register_map.handle_error(
                "Wait for the current Register / Sensor read to finish."
            )
            return
        self.register_write_requested.emit(request)

    def _sync_value_bits(self, length):
        self.reg_value_bits.setMaximum(length * 8)
        self.reg_value_bits.setValue(length * 8)
        self.reg_shift.setMaximum(length * 8 - 1)

    def _toggle_polling(self, enabled):
        self._live_values.clear()
        self.live_stats.setText("Samples: 0")
        if enabled:
            self._poll_timer.start(self.live_interval.value())
            self._poll_register()
        else:
            self._poll_timer.stop()

    def _update_poll_interval(self, value):
        if self._poll_timer.isActive():
            self._poll_timer.start(value)

    def _poll_register(self):
        if not self._poll_pending:
            self._read_register()

    def _memory_request(self):
        address = self._parse_number(self.mem_address.currentText(), "Device address")
        start = self._parse_number(self.mem_start.text(), "Start address")
        width = int(self.mem_reg_width.currentData())
        if not 0x03 <= address <= 0x77:
            raise ValueError("Device address must be from 0x03 to 0x77.")
        if not 0 <= start < (1 << (width * 8)):
            raise ValueError(f"Start address does not fit in {width * 8} bits.")
        length = self.mem_length.value()
        if start + length > (1 << (width * 8)):
            raise ValueError(
                f"Range 0x{start:X} + {length} bytes exceeds the "
                f"{width * 8}-bit address space."
            )
        return {
            "source": "memory",
            "address": address, "start": start, "register_width": width,
            "big_endian": True, "length": length,
            "page_size": self.mem_page_size.value(),
            "write_delay_ms": self.mem_write_delay.value(),
        }

    def _read_memory(self):
        if self.register_map.is_busy:
            self.mem_status.setText("Wait for the Register Map operation to finish.")
            return
        self.pause_polling()
        try:
            request = self._memory_request()
        except ValueError as exc:
            QMessageBox.warning(self, "Memory Viewer", str(exc))
            return
        self.mem_status.setText("Reading memory…")
        self.memory_read_requested.emit(request)

    def _write_memory(self):
        if self.register_map.is_busy:
            self.mem_status.setText("Wait for the Register Map operation to finish.")
            return
        self.pause_polling()
        try:
            request = self._memory_request()
            request["payload"] = self._collect_memory_table()
            if not request["payload"]:
                raise ValueError("Load or read data before writing memory.")
        except ValueError as exc:
            QMessageBox.warning(self, "Memory Viewer", str(exc))
            return
        answer = QMessageBox.question(
            self, "Confirm memory write",
            f"Write {len(request['payload'])} bytes at 0x{request['start']:X} and verify?\n"
            "Incorrect page size or address width can corrupt memory contents."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.mem_status.setText("Writing memory pages…")
        self.memory_write_requested.emit(request)

    def handle_memory_result(self, operation, data):
        self._memory_data = bytes(data)
        if data:
            self._populate_memory_table(self._memory_data)
        self.mem_status.setText(
            "Write and verification completed successfully."
            if operation == "write" else f"Read {len(data)} byte(s)."
        )

    def _populate_memory_table(self, data):
        rows = (len(data) + 15) // 16
        self.memory_table.setRowCount(rows)
        start = self._parse_number(self.mem_start.text(), "Start address")
        self.memory_table.setVerticalHeaderLabels([f"{start + row * 16:04X}:" for row in range(rows)])
        for index, value in enumerate(data):
            item = QTableWidgetItem(f"{value:02X}")
            self.memory_table.setItem(index // 16, index % 16, item)
        self.memory_ascii.setPlainText(
            "".join(chr(value) if 32 <= value <= 126 else "." for value in data)
        )

    def _collect_memory_table(self):
        """Collect exactly ``Length`` bytes without silently closing gaps."""
        output = bytearray()
        length = self.mem_length.value()
        available_cells = self.memory_table.rowCount() * 16
        if available_cells < length:
            raise ValueError(
                f"The table contains space for {available_cells} bytes, but "
                f"Length is {length}. Read or load the data first."
            )
        for index in range(length):
            item = self.memory_table.item(index // 16, index % 16)
            if item is None or not item.text().strip():
                raise ValueError(f"Missing HEX byte at table offset {index}.")
            try:
                output.append(int(item.text(), 16))
            except ValueError as exc:
                raise ValueError(f"Invalid HEX byte at table offset {index}.") from exc
        return bytes(output)

    def _load_binary(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load binary", "", "Binary (*.bin);;All files (*)")
        if not path:
            return
        try:
            with open(path, "rb") as source:
                self._memory_data = source.read()
            self.mem_length.setValue(len(self._memory_data))
            self._populate_memory_table(self._memory_data)
            self.mem_status.setText(f"Loaded {len(self._memory_data)} byte(s) from {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Load binary error", str(exc))

    def _save_binary(self):
        try:
            data = self._collect_memory_table()
        except ValueError as exc:
            QMessageBox.warning(self, "Memory Viewer", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save binary", "memory.bin", "Binary (*.bin)")
        if not path:
            return
        try:
            with open(path, "wb") as output:
                output.write(data)
            self.mem_status.setText(f"Saved {len(data)} byte(s) to {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Save binary error", str(exc))
