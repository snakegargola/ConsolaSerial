"""Generic SPI register command builder, polling, profiles and sampling."""

import csv
from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QGridLayout, QGroupBox, QLabel, QLineEdit,
    QFileDialog, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .i2c_value_codec import decode_i2c_value, encode_i2c_value
from .spi_bus import SpiTransaction, format_spi_hex, parse_spi_hex
from .spi_register_profile import SpiRegisterProfile


class SpiRegisterWidget(QWidget):
    transaction_requested = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent); self._samples = []; self._polling = False
        self._poll_timer = QTimer(self); self._poll_timer.timeout.connect(self._read)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        profiles = QGridLayout()
        self.profile_name = QLineEdit("Generic SPI register")
        save_profile = QPushButton("Save profile"); save_profile.clicked.connect(self._save_profile)
        load_profile = QPushButton("Load profile"); load_profile.clicked.connect(self._load_profile)
        profiles.addWidget(QLabel("Profile:"), 0, 0); profiles.addWidget(self.profile_name, 0, 1)
        profiles.addWidget(save_profile, 0, 2); profiles.addWidget(load_profile, 0, 3)
        root.addLayout(profiles)
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
        polling = QGridLayout()
        self.poll_interval = QSpinBox(); self.poll_interval.setRange(50, 60000)
        self.poll_interval.setValue(1000); self.poll_interval.setSuffix(" ms")
        self.poll_button = QPushButton("Start polling"); self.poll_button.clicked.connect(self._toggle_polling)
        export = QPushButton("Export samples CSV"); export.clicked.connect(self._export_samples)
        clear = QPushButton("Clear samples"); clear.clicked.connect(self._clear_samples)
        polling.addWidget(QLabel("Interval:"), 0, 0); polling.addWidget(self.poll_interval, 0, 1)
        polling.addWidget(self.poll_button, 0, 2); polling.addWidget(export, 0, 3); polling.addWidget(clear, 0, 4)
        self.sample_stats = QLabel("Samples: 0")
        polling.addWidget(self.sample_stats, 1, 0, 1, 5); root.addLayout(polling)
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
            self._samples.append({"timestamp": datetime.now().isoformat(timespec="milliseconds"),
                                  "register": self.register.text(), "raw_hex": format_spi_hex(data),
                                  "unsigned": decoded.unsigned, "signed": decoded.signed,
                                  "value": decoded.scaled, "unit": self.unit.text()})
            values = [item["value"] for item in self._samples]
            self.sample_stats.setText(f"Samples: {len(values)} — min {min(values):g}, "
                                      f"max {max(values):g}, avg {sum(values)/len(values):g}")
        except ValueError as exc: self.result.setText(f"RX {format_spi_hex(data)} — conversion error: {exc}")

    def _toggle_polling(self):
        self._polling = not self._polling
        if self._polling:
            self._poll_timer.start(self.poll_interval.value()); self.poll_button.setText("Stop polling")
            self._read()
        else:
            self._poll_timer.stop(); self.poll_button.setText("Start polling")

    def stop_polling(self):
        if self._polling:
            self._polling = False; self._poll_timer.stop(); self.poll_button.setText("Start polling")

    def _clear_samples(self):
        self._samples.clear(); self.sample_stats.setText("Samples: 0")

    def _export_samples(self):
        if not self._samples: return
        path, _ = QFileDialog.getSaveFileName(self, "Export SPI register samples",
                                               "spi-register-samples.csv", "CSV (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=self._samples[0].keys())
                    writer.writeheader(); writer.writerows(self._samples)
            except OSError as exc: self.result.setText(f"ERROR: {exc}")

    def _profile(self):
        return SpiRegisterProfile(self.profile_name.text(), self.read_opcode.text(),
            self.write_opcode.text(), self.address_bytes.value(), self.read_length.value(),
            self.dummy_count.value(), self.byteorder.currentText(),
            self.signed.currentText() == "signed", float(self.scale.text()),
            float(self.offset.text()), self.unit.text())

    def _apply_profile(self, profile):
        self.profile_name.setText(profile.name); self.read_opcode.setText(profile.read_flags)
        self.write_opcode.setText(profile.write_flags); self.address_bytes.setValue(profile.register_bytes)
        self.read_length.setValue(profile.data_bytes); self.dummy_count.setValue(profile.dummy_bytes)
        self.byteorder.setCurrentText(profile.byteorder); self.signed.setCurrentText("signed" if profile.signed else "unsigned")
        self.scale.setText(str(profile.scale)); self.offset.setText(str(profile.offset)); self.unit.setText(profile.unit)

    def _save_profile(self):
        try: profile = self._profile()
        except ValueError as exc: self.result.setText(f"INVALID: {exc}"); return
        path, _ = QFileDialog.getSaveFileName(self, "Save register profile", "device.spireg.json",
                                               "SPI register profile (*.spireg.json)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as stream: stream.write(profile.to_json())
            except OSError as exc: self.result.setText(f"ERROR: {exc}")

    def _load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load register profile", "",
                                               "SPI register profile (*.spireg.json);;JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    self._apply_profile(SpiRegisterProfile.from_json(stream.read()))
            except (OSError, ValueError) as exc: self.result.setText(f"ERROR: {exc}")

    def settings_dict(self):
        try:
            profile = self._profile()
            return {"profile": profile.to_json(), "register": self.register.text(),
                    "poll_interval": self.poll_interval.value()}
        except ValueError:
            return {}

    def apply_settings(self, value):
        if not isinstance(value, dict): return
        try:
            if value.get("profile"):
                self._apply_profile(SpiRegisterProfile.from_json(value["profile"]))
            if "register" in value: self.register.setText(str(value["register"]))
            if "poll_interval" in value: self.poll_interval.setValue(int(value["poll_interval"]))
        except (ValueError, TypeError):
            pass
