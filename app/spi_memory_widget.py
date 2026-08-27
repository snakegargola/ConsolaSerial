"""SPI memory UI; all device access is delegated to the session worker."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QInputDialog, QMessageBox, QPushButton, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget,
)

from .spi_bus import parse_spi_hex
from .spi_memory import SpiMemoryGeometry, format_hex_dump


class SpiMemoryWidget(QWidget):
    operation_requested = pyqtSignal(str, object, object)

    def __init__(self, parent=None):
        super().__init__(parent); self._buffer = b""; self._base_address = 0
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        config = QGroupBox("Memory geometry and commands")
        form = QFormLayout(config)
        self.kind = QComboBox(); self.kind.addItems(("SPI NOR", "25xx EEPROM", "SPI FRAM"))
        self.capacity = QSpinBox(); self.capacity.setRange(1, 2_147_483_647); self.capacity.setValue(1 << 20)
        self.address_bytes = QSpinBox(); self.address_bytes.setRange(1, 4); self.address_bytes.setValue(3)
        self.page_size = QSpinBox(); self.page_size.setRange(1, 65536); self.page_size.setValue(256)
        self.sector_size = QSpinBox(); self.sector_size.setRange(1, 16 << 20); self.sector_size.setValue(4096)
        self.commands = QLineEdit("03 02 06 05 20 01")
        self.commands.setToolTip("Read, Program, Write Enable, Status, Sector Erase, Busy mask")
        self.protection_mask = QLineEdit("3C")
        self.protection_mask.setToolTip("Status bits that mean protected. Use 00 only when the datasheet confirms no protection check is needed.")
        for label, widget in (("Type", self.kind), ("Capacity (bytes)", self.capacity),
                              ("Address bytes", self.address_bytes), ("Page size", self.page_size),
                              ("Sector size", self.sector_size), ("Commands (HEX)", self.commands),
                              ("Protection mask", self.protection_mask)):
            form.addRow(label, widget)
        root.addWidget(config)
        controls = QGridLayout()
        self.address = QLineEdit("000000"); self.length = QSpinBox()
        self.length.setRange(1, 65280); self.length.setValue(256)
        controls.addWidget(QLabel("Address (HEX):"), 0, 0); controls.addWidget(self.address, 0, 1)
        controls.addWidget(QLabel("Length:"), 0, 2); controls.addWidget(self.length, 0, 3)
        identify = QPushButton("Identify JEDEC/SFDP"); identify.clicked.connect(lambda: self._request("identify"))
        status = QPushButton("Read status"); status.clicked.connect(lambda: self._request("status"))
        read = QPushButton("Read"); read.clicked.connect(lambda: self._request("read"))
        load = QPushButton("Load BIN for program"); load.clicked.connect(self._load_bin)
        program = QPushButton("Program + verify"); program.clicked.connect(lambda: self._request("program"))
        erase = QPushButton("Erase sector"); erase.clicked.connect(lambda: self._request("erase_sector"))
        compare = QPushButton("Compare BIN"); compare.clicked.connect(self._compare_bin)
        edit = QPushButton("Edit buffer HEX"); edit.clicked.connect(self._edit_buffer)
        save = QPushButton("Save buffer BIN"); save.clicked.connect(self._save_bin)
        for column, button in enumerate((identify, status, read, load, edit, program, erase, compare, save)):
            controls.addWidget(button, 1, column)
        self._buttons = (identify, status, read, load, edit, program, erase, compare, save)
        root.addLayout(controls)
        self.viewer = QTextEdit(); self.viewer.setReadOnly(True); self.viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self.viewer, 1)
        self.status = QLabel("Read first. Programming and erase always require confirmation.")
        root.addWidget(self.status)

    def geometry(self):
        command = parse_spi_hex(self.commands.text(), allow_empty=False)
        if len(command) != 6: raise ValueError("Enter exactly six command/mask bytes.")
        protection = parse_spi_hex(self.protection_mask.text(), allow_empty=False)
        if len(protection) != 1: raise ValueError("Protection mask must be one byte.")
        return SpiMemoryGeometry(self.kind.currentText(), self.capacity.value(),
                                 self.address_bytes.value(), self.page_size.value(),
                                 self.sector_size.value(), *command,
                                 protection_mask=protection[0])

    def _address(self):
        try: return int(self.address.text().strip(), 16)
        except ValueError as exc: raise ValueError("Address must be hexadecimal.") from exc

    def _request(self, action):
        try:
            geometry = self.geometry(); address = self._address()
            request = {"address": address, "length": self.length.value()}
            if action == "program":
                if not self._buffer: raise ValueError("Load a BIN file before programming.")
                request["data"] = self._buffer
                prompt = f"Program {len(self._buffer)} bytes at 0x{address:X} and verify?"
            elif action == "erase_sector":
                prompt = f"Erase the entire sector containing address 0x{address:X}?"
            else: prompt = ""
            if prompt and QMessageBox.warning(self, "Destructive SPI operation", prompt,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                return
            self.operation_requested.emit(action, geometry, request)
        except ValueError as exc: self.status.setText(f"INVALID: {exc}")

    def _load_bin(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load memory image", "", "Binary (*.bin);;All files (*)")
        if path:
            try:
                with open(path, "rb") as stream: self._buffer = stream.read()
                self._base_address = self._address(); self.length.setValue(min(len(self._buffer), 65280))
                self.viewer.setPlainText(format_hex_dump(self._buffer, self._base_address))
                self.status.setText(f"Loaded {len(self._buffer)} bytes from {path}")
            except (OSError, ValueError) as exc: self.status.setText(f"ERROR: {exc}")

    def _save_bin(self):
        if not self._buffer: return
        path, _ = QFileDialog.getSaveFileName(self, "Save memory image", "memory.bin", "Binary (*.bin)")
        if path:
            try:
                with open(path, "wb") as stream: stream.write(self._buffer)
            except OSError as exc: self.status.setText(f"ERROR: {exc}")

    def _compare_bin(self):
        if not self._buffer:
            self.status.setText("Read or load a buffer before comparing."); return
        path, _ = QFileDialog.getOpenFileName(self, "Compare with memory image", "", "Binary (*.bin)")
        if not path: return
        try:
            with open(path, "rb") as stream: reference = stream.read()
            count = max(len(reference), len(self._buffer))
            differences = [index for index in range(count)
                           if index >= len(reference) or index >= len(self._buffer)
                           or reference[index] != self._buffer[index]]
            preview = ", ".join(f"0x{self._base_address + item:X}" for item in differences[:8])
            self.status.setText("MATCH: buffers are identical" if not differences else
                                f"DIFFERENT: {len(differences)} byte(s); first: {preview}")
        except OSError as exc: self.status.setText(f"ERROR: {exc}")

    def _edit_buffer(self):
        text, accepted = QInputDialog.getMultiLineText(
            self, "Edit SPI memory buffer", "HEX bytes:", format_spi_hex(self._buffer))
        if not accepted: return
        try:
            payload = parse_spi_hex(text, allow_empty=False)
            self.geometry(); self._base_address = self._address()
            if self._base_address + len(payload) > self.capacity.value():
                raise ValueError("Edited buffer exceeds configured memory capacity.")
            self._buffer = payload; self.length.setValue(min(len(payload), 65280))
            self.viewer.setPlainText(format_hex_dump(payload, self._base_address))
            self.status.setText(f"Edited buffer: {len(payload)} bytes. Program still requires confirmation.")
        except ValueError as exc: self.status.setText(f"INVALID: {exc}")

    def show_result(self, result):
        data = bytes(result.get("data", b"")); action = result.get("action")
        if action == "identify" and result.get("jedec"):
            item = result["jedec"]; sfdp = result.get("sfdp")
            if item.get("capacity") and item["capacity"] <= self.capacity.maximum():
                self.capacity.setValue(item["capacity"])
            if sfdp and sfdp.get("capacity") and sfdp["capacity"] <= self.capacity.maximum():
                self.capacity.setValue(sfdp["capacity"])
            if sfdp and sfdp.get("page_size"):
                self.page_size.setValue(sfdp["page_size"])
            if sfdp and sfdp.get("address_bytes") == (4,):
                self.address_bytes.setValue(4)
            if sfdp and sfdp.get("erase_types"):
                erase = min(sfdp["erase_types"], key=lambda value: value["size"])
                self.sector_size.setValue(erase["size"])
                command = list(parse_spi_hex(self.commands.text(), allow_empty=False))
                if len(command) == 6:
                    command[4] = erase["opcode"]
                    self.commands.setText(format_spi_hex(command))
            self.status.setText(f"{result['status']}: {item['manufacturer']} ID "
                                f"{item['manufacturer_id']:02X} {item['memory_type']:02X} "
                                f"{item['capacity_code']:02X}; SFDP: {'yes' if sfdp else 'no'} — "
                                f"{result.get('details', '')}")
        elif action == "status" and result.get("status_register"):
            item = result["status_register"]
            self.status.setText(f"Status 0x{item['raw']:02X}: BUSY={item['busy']}, "
                                f"WEL={item['write_enabled']}, protected={item['protected']} "
                                f"(bits 0x{item['protection_bits']:02X})")
        else:
            if data:
                self._buffer = data; self._base_address = result.get("address", self._base_address)
                self.viewer.setPlainText(format_hex_dump(data, self._base_address))
            self.status.setText(f"{result.get('status')}: {result.get('details') or result.get('error') or ''}")

    def set_busy(self, busy):
        for button in self._buttons: button.setEnabled(not busy)

    def settings_dict(self):
        return {"kind": self.kind.currentText(), "capacity": self.capacity.value(),
                "address_bytes": self.address_bytes.value(), "page_size": self.page_size.value(),
                "sector_size": self.sector_size.value(), "commands": self.commands.text(),
                "protection_mask": self.protection_mask.text(),
                "address": self.address.text(), "length": self.length.value()}

    def apply_settings(self, value):
        if not isinstance(value, dict): return
        self.kind.setCurrentText(str(value.get("kind", self.kind.currentText())))
        for key, widget in (("capacity", self.capacity), ("address_bytes", self.address_bytes),
                            ("page_size", self.page_size), ("sector_size", self.sector_size),
                            ("length", self.length)):
            if key in value: widget.setValue(int(value[key]))
        if "commands" in value: self.commands.setText(str(value["commands"]))
        if "protection_mask" in value: self.protection_mask.setText(str(value["protection_mask"]))
        if "address" in value: self.address.setText(str(value["address"]))
