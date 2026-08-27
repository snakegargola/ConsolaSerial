"""Generic SPI register command builder and value inspector."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QGridLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .i2c_value_codec import decode_i2c_value, encode_i2c_value
from .spi_bus import SpiTransaction, format_spi_hex, parse_spi_hex


class SpiRegisterWidget(QWidget):
    transaction_requested = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent); self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        command = QGroupBox("Command framing")
        grid = QGridLayout(command)
        self.read_opcode = QLineEdit("80"); self.write_opcode = QLineEdit("00")
        self.register = QLineEdit("00"); self.address_bytes = QSpinBox(); self.address_bytes.setRange(1, 4)
        self.read_length = QSpinBox(); self.read_length.setRange(1, 256); self.read_length.setValue(1)
        self.dummy_count = QSpinBox(); self.dummy_count.setRange(0, 16)
        fields = (("Read opcode/flags", self.read_opcode), ("Write opcode/flags", self.write_opcode),
                  ("Register (HEX)", self.register), ("Register bytes", self.address_bytes),
                  ("Data bytes", self.read_length), ("Dummy bytes before RX", self.dummy_count))
        for index, (label, widget) in enumerate(fields):
            grid.addWidget(QLabel(label), index // 3, (index % 3) * 2)
            grid.addWidget(widget, index // 3, (index % 3) * 2 + 1)
        hint = QLabel("Opcode/flags are ORed into the first register-address byte. Set 00 when the device uses raw addresses.")
        hint.setWordWrap(True); grid.addWidget(hint, 2, 0, 1, 6); root.addWidget(command)

        conversion = QGroupBox("Value conversion")
        form = QFormLayout(conversion)
        self.byteorder = QComboBox(); self.byteorder.addItems(("big", "little"))
        self.signed = QComboBox(); self.signed.addItems(("unsigned", "signed"))
        self.scale = QLineEdit("1"); self.offset = QLineEdit("0"); self.unit = QLineEdit()
        for label, widget in (("Byte order", self.byteorder), ("Sign", self.signed),
                              ("Scale", self.scale), ("Offset", self.offset), ("Unit", self.unit)):
            form.addRow(label, widget)
        root.addWidget(conversion)

        actions = QGridLayout()
        self.write_value = QLineEdit("00")
        self.input_format = QComboBox(); self.input_format.addItems(("HEX bytes", "Decimal", "Hexadecimal", "Binary"))
        read = QPushButton("Read register"); read.clicked.connect(self._read)
        write = QPushButton("Write register"); write.clicked.connect(self._write)
        actions.addWidget(read, 0, 0); actions.addWidget(write, 0, 1)
        actions.addWidget(QLabel("Write value:"), 1, 0); actions.addWidget(self.write_value, 1, 1)
        actions.addWidget(self.input_format, 1, 2); root.addLayout(actions)
        self.result = QLabel("Ready."); self.result.setWordWrap(True); root.addWidget(self.result)
        root.addStretch()

    def _address(self, flags_text):
        register = int(self.register.text().strip(), 16)
        width = self.address_bytes.value()
        if not 0 <= register < 1 << (width * 8): raise ValueError("Register does not fit its width.")
        output = bytearray(register.to_bytes(width, "big"))
        flags = parse_spi_hex(flags_text, allow_empty=False)
        if len(flags) != 1: raise ValueError("Opcode/flags must be one HEX byte.")
        output[0] |= flags[0]
        return bytes(output)

    def _read(self):
        try:
            dummy = self.dummy_count.value()
            transaction = SpiTransaction("write_read", self._address(self.read_opcode.text()) + b"\x00" * dummy,
                                         self.read_length.value(), 0x00)
            self.transaction_requested.emit(transaction, {"kind": "register_read", "dummy": dummy})
        except ValueError as exc: self.result.setText(f"INVALID: {exc}")

    def _write(self):
        try:
            data = encode_i2c_value(self.write_value.text(), input_format=self.input_format.currentText(),
                                    length=self.read_length.value(), byteorder=self.byteorder.currentText(),
                                    signed=self.signed.currentText() == "signed")
            transaction = SpiTransaction("write", self._address(self.write_opcode.text()) + data)
            self.transaction_requested.emit(transaction, {"kind": "register_write", "data": data})
        except ValueError as exc: self.result.setText(f"INVALID: {exc}")

    def show_result(self, result, context):
        if result.get("status") != "OK":
            self.result.setText(f"{result.get('status')}: {result.get('error')}"); return
        if context.get("kind") == "register_write":
            self.result.setText(f"OK: wrote {format_spi_hex(context['data'])}"); return
        data = bytes(result.get("rx", b""))
        try:
            decoded = decode_i2c_value(data, byteorder=self.byteorder.currentText(),
                                       signed=self.signed.currentText() == "signed",
                                       scale=float(self.scale.text()), offset=float(self.offset.text()))
            self.result.setText(f"RX {format_spi_hex(data)} — unsigned {decoded.unsigned}, "
                                f"signed {decoded.signed}, value {decoded.scaled:g} {self.unit.text()}")
        except ValueError as exc: self.result.setText(f"RX {format_spi_hex(data)} — conversion error: {exc}")
