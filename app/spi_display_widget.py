"""Configurable quick-test UI for common and custom SPI displays."""

from __future__ import annotations

import json

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit, QSpinBox,
    QVBoxLayout, QWidget,
)

from .spi_display import (
    SpiDisplayProfile, builtin_display_profiles, checkerboard_rgb565,
    color_bars_rgb565, format_init_script, load_image_rgb565,
    parse_init_script, solid_rgb565,
)


class SpiDisplayWidget(QWidget):
    """Build display profiles and request atomic SPI/GPIO test actions."""

    operation_requested = pyqtSignal(object)

    def __init__(self, available_mask=0xF0, pin_prefix="DBUS", width=8, parent=None):
        super().__init__(parent)
        self.width = int(width)
        self.available_mask = int(available_mask)
        self.pin_prefix = str(pin_prefix)
        self._profiles = builtin_display_profiles()
        self._build_ui()
        self.set_available_mask(self.available_mask)
        self._load_profile(0)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        config_box = QGroupBox("SPI display quick validation")
        grid = QGridLayout(config_box)
        grid.addWidget(QLabel("Profile:"), 0, 0)
        self.profile_combo = QComboBox()
        for profile in self._profiles:
            self.profile_combo.addItem(profile.name, profile)
        self.profile_combo.currentIndexChanged.connect(self._load_profile)
        grid.addWidget(self.profile_combo, 0, 1, 1, 3)
        load_btn = QPushButton("Load profile")
        load_btn.clicked.connect(self._load_profile_file)
        grid.addWidget(load_btn, 0, 4)
        save_btn = QPushButton("Save profile")
        save_btn.clicked.connect(self._save_profile_file)
        grid.addWidget(save_btn, 0, 5)

        grid.addWidget(QLabel("Name:"), 1, 0)
        self.name_edit = QLineEdit()
        grid.addWidget(self.name_edit, 1, 1)
        grid.addWidget(QLabel("Controller:"), 1, 2)
        self.controller_edit = QLineEdit()
        grid.addWidget(self.controller_edit, 1, 3)
        grid.addWidget(QLabel("Format:"), 1, 4)
        self.format_combo = QComboBox()
        self.format_combo.addItem("RGB565", "rgb565")
        grid.addWidget(self.format_combo, 1, 5)

        grid.addWidget(QLabel("Width:"), 2, 0)
        self.width_spin = QSpinBox(); self.width_spin.setRange(1, 2048)
        grid.addWidget(self.width_spin, 2, 1)
        grid.addWidget(QLabel("Height:"), 2, 2)
        self.height_spin = QSpinBox(); self.height_spin.setRange(1, 2048)
        grid.addWidget(self.height_spin, 2, 3)
        grid.addWidget(QLabel("X offset:"), 2, 4)
        self.x_offset = QSpinBox(); self.x_offset.setRange(0, 65535)
        grid.addWidget(self.x_offset, 2, 5)
        grid.addWidget(QLabel("Y offset:"), 3, 4)
        self.y_offset = QSpinBox(); self.y_offset.setRange(0, 65535)
        grid.addWidget(self.y_offset, 3, 5)

        grid.addWidget(QLabel("D/C pin:"), 3, 0)
        self.dc_combo = QComboBox(); grid.addWidget(self.dc_combo, 3, 1)
        grid.addWidget(QLabel("RESET pin:"), 3, 2)
        self.reset_combo = QComboBox(); grid.addWidget(self.reset_combo, 3, 3)
        grid.addWidget(QLabel("Backlight pin:"), 4, 0)
        self.backlight_combo = QComboBox(); grid.addWidget(self.backlight_combo, 4, 1)
        self.backlight_on = QCheckBox("Backlight HIGH")
        self.backlight_on.setChecked(True)
        grid.addWidget(self.backlight_on, 4, 2, 1, 2)

        hint = QLabel(
            "Initialization format: COMMAND_HEX ; DATA_HEX ; DELAY_MS. "
            "One step per line; # starts a comment. Confirm the preset and offsets "
            "against the exact module datasheet."
        )
        hint.setWordWrap(True)
        grid.addWidget(hint, 5, 0, 1, 6)
        self.init_edit = QPlainTextEdit()
        self.init_edit.setMaximumHeight(150)
        self.init_edit.setPlaceholderText("01 ; ; 150\n11 ; ; 120\n3A ; 55 ; 10\n29 ; ; 20")
        grid.addWidget(self.init_edit, 6, 0, 1, 6)
        root.addWidget(config_box)

        actions = QGroupBox("Quick tests")
        row = QHBoxLayout(actions)
        self.reset_btn = QPushButton("Hardware reset")
        self.reset_btn.clicked.connect(lambda: self._request("reset"))
        row.addWidget(self.reset_btn)
        self.init_btn = QPushButton("Initialize")
        self.init_btn.clicked.connect(lambda: self._request("initialize"))
        row.addWidget(self.init_btn)
        self.bars_btn = QPushButton("Init + color bars")
        self.bars_btn.clicked.connect(lambda: self._request_pattern("bars"))
        row.addWidget(self.bars_btn)
        self.checker_btn = QPushButton("Checkerboard")
        self.checker_btn.clicked.connect(lambda: self._request_pattern("checker"))
        row.addWidget(self.checker_btn)
        self.clear_btn = QPushButton("Clear black")
        self.clear_btn.clicked.connect(lambda: self._request_pattern("black"))
        row.addWidget(self.clear_btn)
        self.image_btn = QPushButton("Send image…")
        self.image_btn.clicked.connect(self._request_image)
        row.addWidget(self.image_btn)
        root.addWidget(actions)

        self.wiring = QLabel()
        self.wiring.setWordWrap(True)
        root.addWidget(self.wiring)
        self.status = QLabel("Ready. Start with Hardware reset, then Initialize.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch()
        for combo in (self.dc_combo, self.reset_combo, self.backlight_combo):
            combo.currentIndexChanged.connect(self._update_wiring)

    def set_available_mask(self, available_mask):
        previous = [combo.currentData() for combo in (
            self.dc_combo, self.reset_combo, self.backlight_combo
        )]
        self.available_mask = int(available_mask)
        pins = [pin for pin in range(self.width) if self.available_mask & (1 << pin)]
        for index, combo in enumerate((self.dc_combo, self.reset_combo, self.backlight_combo)):
            combo.blockSignals(True)
            combo.clear()
            if index:
                combo.addItem("Not connected", None)
            for pin in pins:
                combo.addItem(f"{self.pin_prefix}{pin}", pin)
            match = combo.findData(previous[index])
            if match >= 0:
                combo.setCurrentIndex(match)
            elif index < len(pins):
                combo.setCurrentIndex(combo.findData(pins[index]))
            else:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)
        enabled = bool(pins)
        for button in self._action_buttons():
            button.setEnabled(enabled)
        self._update_wiring()

    def profile(self):
        return SpiDisplayProfile(
            self.name_edit.text().strip(), self.controller_edit.text().strip(),
            self.width_spin.value(), self.height_spin.value(),
            self.format_combo.currentData(), parse_init_script(self.init_edit.toPlainText()),
            self.x_offset.value(), self.y_offset.value(),
        )

    def gpio_pins(self):
        pins = {
            "dc": self.dc_combo.currentData(),
            "reset": self.reset_combo.currentData(),
            "backlight": self.backlight_combo.currentData(),
        }
        if pins["dc"] is None:
            raise ValueError("D/C requires an available GPIO pin.")
        selected = [pin for pin in pins.values() if pin is not None]
        if len(selected) != len(set(selected)):
            raise ValueError("D/C, RESET and backlight must use different pins.")
        if any(not self.available_mask & (1 << pin) for pin in selected):
            raise ValueError("A selected display GPIO is reserved by SPI.")
        return pins

    def settings_dict(self):
        try:
            profile = self.profile().to_dict()
        except ValueError:
            profile = self._profiles[0].to_dict()
        return {
            "profile": profile, "gpio_pins": self.gpio_pins_safe(),
            "backlight_on": self.backlight_on.isChecked(),
        }

    def apply_settings(self, settings):
        value = settings.get("profile")
        if isinstance(value, dict):
            try:
                self._apply_profile(SpiDisplayProfile.from_dict(value))
            except (ValueError, TypeError):
                pass
        pins = settings.get("gpio_pins", {})
        for name, combo in (("dc", self.dc_combo), ("reset", self.reset_combo),
                            ("backlight", self.backlight_combo)):
            index = combo.findData(pins.get(name))
            if index >= 0:
                combo.setCurrentIndex(index)
        self.backlight_on.setChecked(bool(settings.get("backlight_on", True)))

    def gpio_pins_safe(self):
        return {"dc": self.dc_combo.currentData(), "reset": self.reset_combo.currentData(),
                "backlight": self.backlight_combo.currentData()}

    def show_result(self, result):
        if result.get("status") != "OK":
            self.status.setText(f"ERROR: {result.get('error', 'Display operation failed')}")
            return
        count = int(result.get("bytes_sent", 0))
        detail = f", {count} framebuffer bytes" if count else ""
        self.status.setText(
            f"OK — {result.get('action', 'operation')}{detail}, "
            f"{result.get('actual_frequency', 0):g} Hz, "
            f"{result.get('duration_ms', 0.0):.2f} ms"
        )

    def set_busy(self, busy):
        for button in self._action_buttons():
            button.setEnabled(not busy and bool(self.available_mask))

    def _action_buttons(self):
        return (self.reset_btn, self.init_btn, self.bars_btn, self.checker_btn,
                self.clear_btn, self.image_btn)

    def _load_profile(self, index):
        profile = self.profile_combo.itemData(index)
        if profile:
            self._apply_profile(profile)

    def _apply_profile(self, profile):
        self.name_edit.setText(profile.name)
        self.controller_edit.setText(profile.controller)
        self.width_spin.setValue(profile.width); self.height_spin.setValue(profile.height)
        self.x_offset.setValue(profile.column_offset); self.y_offset.setValue(profile.row_offset)
        index = self.format_combo.findData(profile.pixel_format)
        self.format_combo.setCurrentIndex(max(0, index))
        self.init_edit.setPlainText(format_init_script(profile.init_steps))

    def _request(self, action, payload=b""):
        try:
            request = {
                "action": action, "profile": self.profile(), "gpio_pins": self.gpio_pins(),
                "payload": bytes(payload), "backlight_on": self.backlight_on.isChecked(),
            }
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}")
            return
        self.operation_requested.emit(request)

    def _request_pattern(self, pattern):
        try:
            profile = self.profile()
            if profile.pixel_format != "rgb565":
                raise ValueError("Quick patterns currently require RGB565.")
            if pattern == "bars":
                payload = color_bars_rgb565(profile.width, profile.height)
                action = "initialize_framebuffer"
            elif pattern == "checker":
                payload = checkerboard_rgb565(profile.width, profile.height)
                action = "framebuffer"
            else:
                payload = solid_rgb565(profile.width, profile.height, 0x0000)
                action = "framebuffer"
            self._request(action, payload)
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}")

    def _request_image(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "Open image for SPI display", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
        )
        if not path:
            return
        try:
            profile = self.profile()
            payload = load_image_rgb565(path, profile.width, profile.height)
            self._request("framebuffer", payload)
        except (ValueError, OSError, RuntimeError) as exc:
            self.status.setText(f"IMAGE ERROR: {exc}")

    def _save_profile_file(self):
        try:
            profile = self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "SPI display profile", str(exc)); return
        path, _selected = QFileDialog.getSaveFileName(
            self, "Save SPI display profile", f"{profile.controller}.spidisplay.json",
            "SPI display profile (*.spidisplay.json);;JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(profile.to_json())
            self.status.setText(f"Profile saved: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "SPI display profile", str(exc))

    def _load_profile_file(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "Open SPI display profile", "",
            "SPI display profile (*.spidisplay.json *.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                profile = SpiDisplayProfile.from_json(stream.read())
            self._apply_profile(profile)
            self.status.setText(f"Profile loaded: {path}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "SPI display profile", str(exc))

    def _update_wiring(self):
        self.wiring.setText(
            f"Wiring: SCLK={self.pin_prefix}0, MOSI={self.pin_prefix}1, "
            f"MISO={self.pin_prefix}2 (optional), /CS uses the selected SPI line, "
            f"D/C={self.dc_combo.currentText() or 'unavailable'}, "
            f"RESET={self.reset_combo.currentText() or 'not connected'}, "
            f"BL={self.backlight_combo.currentText() or 'not connected'}, plus common GND."
        )
