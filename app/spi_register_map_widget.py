"""Qt editor, runner and sample exporter for SPI register maps."""

import csv
from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .i2c_value_codec import decode_i2c_value
from .spi_bus import format_spi_hex
from .spi_register_map import SpiRegisterDefinition, SpiRegisterMap, example_spi_register_map


class SpiRegisterMapWidget(QWidget):
    read_requested = pyqtSignal(object, object)

    COLUMNS = ("Name", "Address", "Bytes", "Access", "Endian", "Signed",
               "Scale", "Offset", "Unit", "Raw", "Value")

    def __init__(self, parent=None):
        super().__init__(parent); self._samples = []; self._polling = False
        self._timer = QTimer(self); self._timer.timeout.connect(self._read_all)
        self._build_ui(); self.apply_profile(example_spi_register_map())

    def _build_ui(self):
        root = QVBoxLayout(self); header = QHBoxLayout()
        self.name = QLineEdit(); self.read_flags = QLineEdit("80"); self.write_flags = QLineEdit("00")
        self.address_bytes = QSpinBox(); self.address_bytes.setRange(1, 4)
        self.dummy_bytes = QSpinBox(); self.dummy_bytes.setRange(0, 16)
        for label, widget in (("Map", self.name), ("Read flags", self.read_flags),
                              ("Write flags", self.write_flags), ("Address bytes", self.address_bytes),
                              ("Dummy", self.dummy_bytes)):
            header.addWidget(QLabel(label)); header.addWidget(widget)
        root.addLayout(header)
        self.table = QTableWidget(0, len(self.COLUMNS)); self.table.setHorizontalHeaderLabels(self.COLUMNS)
        root.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for label, handler in (("Add", self._add), ("Remove", self._remove),
                               ("Read selected", self._read_selected), ("Read all", self._read_all),
                               ("Save map", self._save), ("Load map", self._load),
                               ("Export CSV", self._export)):
            button = QPushButton(label); button.clicked.connect(handler); actions.addWidget(button)
        self.interval = QSpinBox(); self.interval.setRange(100, 60000); self.interval.setValue(1000); self.interval.setSuffix(" ms")
        self.poll = QPushButton("Start polling"); self.poll.clicked.connect(self._toggle_poll)
        actions.addWidget(self.interval); actions.addWidget(self.poll); root.addLayout(actions)
        self.status = QLabel("Ready."); root.addWidget(self.status)

    def _add(self, definition=None):
        item = definition or SpiRegisterDefinition("REGISTER", 0)
        row = self.table.rowCount(); self.table.insertRow(row)
        values = (item.name, f"0x{item.address:X}", str(item.length), item.access,
                  item.byteorder, "yes" if item.signed else "no", str(item.scale),
                  str(item.offset), item.unit, "", "")
        for column, value in enumerate(values): self.table.setItem(row, column, QTableWidgetItem(value))

    def profile(self):
        registers = []
        for row in range(self.table.rowCount()):
            value = lambda column: self.table.item(row, column).text().strip()
            registers.append(SpiRegisterDefinition(value(0), int(value(1), 0), int(value(2)),
                value(3).upper(), value(4).lower(), value(5).lower() in ("yes", "true", "1"),
                float(value(6)), float(value(7)), value(8)))
        return SpiRegisterMap(self.name.text(), int(self.read_flags.text(), 16),
                              int(self.write_flags.text(), 16), self.address_bytes.value(),
                              self.dummy_bytes.value(), tuple(registers))

    def apply_profile(self, profile):
        self.name.setText(profile.name); self.read_flags.setText(f"{profile.read_flags:02X}")
        self.write_flags.setText(f"{profile.write_flags:02X}"); self.address_bytes.setValue(profile.address_bytes)
        self.dummy_bytes.setValue(profile.dummy_bytes); self.table.setRowCount(0)
        for item in profile.registers: self._add(item)

    def _remove(self):
        if self.table.currentRow() >= 0: self.table.removeRow(self.table.currentRow())

    def _request(self, indexes):
        try: self.read_requested.emit(self.profile(), tuple(indexes))
        except (ValueError, KeyError, AttributeError) as exc: self.status.setText(f"INVALID: {exc}")

    def _read_selected(self):
        if self.table.currentRow() >= 0: self._request((self.table.currentRow(),))

    def _read_all(self): self._request(range(self.table.rowCount()))

    def show_result(self, result, profile):
        if result.get("status") != "OK": self.status.setText(f"{result.get('status')}: {result.get('error')}"); return
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        for value in result.get("values", []):
            index = value["index"]; definition = profile.registers[index]; data = value["data"]
            try:
                decoded = decode_i2c_value(data, byteorder=definition.byteorder, signed=definition.signed,
                                           scale=definition.scale, offset=definition.offset)
            except ValueError as exc:
                self.table.item(index, 10).setText(f"ERROR: {exc}"); continue
            self.table.item(index, 9).setText(format_spi_hex(data)); self.table.item(index, 10).setText(f"{decoded.scaled:g} {definition.unit}")
            self._samples.append({"timestamp": timestamp, "name": definition.name,
                                  "address": f"0x{definition.address:X}", "raw": format_spi_hex(data),
                                  "value": decoded.scaled, "unit": definition.unit})
        self.status.setText(f"OK: {len(result.get('values', []))} register(s), {result.get('duration_ms', 0):.2f} ms")

    def _toggle_poll(self):
        self._polling = not self._polling
        if self._polling: self._timer.start(self.interval.value()); self.poll.setText("Stop polling"); self._read_all()
        else: self.stop_polling()

    def stop_polling(self): self._polling = False; self._timer.stop(); self.poll.setText("Start polling")

    def _save(self):
        try: profile = self.profile()
        except ValueError as exc: self.status.setText(f"INVALID: {exc}"); return
        path, _ = QFileDialog.getSaveFileName(self, "Save SPI register map", "device.spimap.json", "SPI map (*.spimap.json)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as stream: stream.write(profile.to_json())
            except OSError as exc: self.status.setText(f"ERROR: {exc}")

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load SPI register map", "", "SPI map (*.spimap.json);;JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as stream: self.apply_profile(SpiRegisterMap.from_json(stream.read()))
            except (OSError, ValueError) as exc: QMessageBox.critical(self, "SPI map", str(exc))

    def _export(self):
        if not self._samples: return
        path, _ = QFileDialog.getSaveFileName(self, "Export SPI map samples", "spi-map.csv", "CSV (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=self._samples[0].keys()); writer.writeheader(); writer.writerows(self._samples)
            except OSError as exc: self.status.setText(f"ERROR: {exc}")

    def settings_dict(self):
        try: return {"profile": self.profile().to_json(), "interval": self.interval.value()}
        except ValueError: return {}

    def apply_settings(self, value):
        if not isinstance(value, dict): return
        try:
            if value.get("profile"): self.apply_profile(SpiRegisterMap.from_json(value["profile"]))
            if "interval" in value: self.interval.setValue(int(value["interval"]))
        except (ValueError, TypeError): pass
