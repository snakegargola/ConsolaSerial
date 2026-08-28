"""Reusable per-pin GPIO editor used by dedicated and SPI sessions."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .gpio_bus import GPIO_PORT_WIDTH, GpioState, mask_for_width


class GpioPanel(QWidget):
    """Edit direction/level and display the sampled state of each GPIO pin."""

    operation_requested = pyqtSignal(object, bool)

    def __init__(self, *, title="GPIO", width=GPIO_PORT_WIDTH,
                 available_mask=None, pin_prefix="DBUS", parent=None):
        super().__init__(parent)
        self.width = int(width)
        self.pin_prefix = str(pin_prefix)
        self.available_mask = (
            mask_for_width(self.width)
            if available_mask is None else int(available_mask)
        )
        self._directions = []
        self._outputs = []
        self._sample_items = []
        self._build_ui(title)
        self.set_available_mask(self.available_mask)

    def _build_ui(self, title):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        info = QGroupBox(title)
        info_layout = QGridLayout(info)
        self.description = QLabel()
        self.description.setWordWrap(True)
        info_layout.addWidget(self.description, 0, 0)
        root.addWidget(info)

        self.table = QTableWidget(self.width, 4)
        self.table.setHorizontalHeaderLabels(("Pin", "Direction", "Output", "Read"))
        for pin in range(self.width):
            pin_item = QTableWidgetItem(f"{self.pin_prefix}{pin}")
            pin_item.setFlags(
                pin_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(pin, 0, pin_item)
            direction = QComboBox()
            direction.addItem("Input", False)
            direction.addItem("Output", True)
            direction.currentIndexChanged.connect(
                lambda _index, row=pin: self._direction_changed(row)
            )
            self.table.setCellWidget(pin, 1, direction)
            output = QCheckBox("High")
            output.setEnabled(False)
            self.table.setCellWidget(pin, 2, output)
            sampled = QTableWidgetItem("—")
            self.table.setItem(pin, 3, sampled)
            self._directions.append(direction)
            self._outputs.append(output)
            self._sample_items.append(sampled)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table)

        actions = QHBoxLayout()
        self.apply_btn = QPushButton("Apply outputs and read")
        self.apply_btn.clicked.connect(lambda: self._emit_operation(True))
        actions.addWidget(self.apply_btn)
        self.read_btn = QPushButton("Read inputs")
        self.read_btn.clicked.connect(lambda: self._emit_operation(False))
        actions.addWidget(self.read_btn)
        all_inputs = QPushButton("All inputs")
        all_inputs.clicked.connect(self._all_inputs)
        actions.addWidget(all_inputs)
        outputs_low = QPushButton("Outputs low")
        outputs_low.clicked.connect(self._outputs_low)
        actions.addWidget(outputs_low)
        actions.addStretch()
        root.addLayout(actions)
        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def set_available_mask(self, available_mask):
        self.available_mask = int(available_mask) & mask_for_width(self.width)
        names = []
        for pin in range(self.width):
            available = bool(self.available_mask & (1 << pin))
            self.table.setRowHidden(pin, not available)
            if available:
                names.append(f"{self.pin_prefix}{pin}")
        self.description.setText(
            "Available pins: " + (", ".join(names) if names else "none") +
            ". Inputs are high impedance; do not leave them floating when "
            "validating a level. FTDI GPIO is 3.3 V logic."
        )

    def state(self):
        direction = output = 0
        for pin in range(self.width):
            bit = 1 << pin
            if not self.available_mask & bit:
                continue
            if bool(self._directions[pin].currentData()):
                direction |= bit
                if self._outputs[pin].isChecked():
                    output |= bit
        return GpioState(self.available_mask, direction, output, self.width)

    def apply_settings(self, settings):
        direction = int(settings.get("direction", 0))
        output = int(settings.get("output", 0))
        for pin in range(self.width):
            self._directions[pin].setCurrentIndex(1 if direction & (1 << pin) else 0)
            self._outputs[pin].setChecked(bool(output & (1 << pin)))

    def settings_dict(self):
        state = self.state()
        return {"direction": state.direction, "output": state.output}

    def show_result(self, result):
        if result.get("status") != "OK":
            self.status.setText(f"ERROR: {result.get('error', 'GPIO operation failed')}")
            return
        sampled = int(result.get("sampled", 0))
        direction = int(result.get("direction", 0))
        for pin, item in enumerate(self._sample_items):
            bit = 1 << pin
            if self.available_mask & bit:
                item.setText("HIGH" if sampled & bit else "LOW")
                item.setToolTip("Output readback" if direction & bit else "Physical input")
        self.status.setText(
            f"OK — sampled 0x{sampled:0{max(2, (self.width + 3) // 4)}X} "
            f"in {result.get('duration_ms', 0.0):.2f} ms"
        )

    def set_busy(self, busy):
        self.apply_btn.setEnabled(not busy)
        self.read_btn.setEnabled(not busy)

    def _emit_operation(self, write_outputs):
        try:
            state = self.state()
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}")
            return
        self.operation_requested.emit(state, write_outputs)

    def _direction_changed(self, pin):
        self._outputs[pin].setEnabled(bool(self._directions[pin].currentData()))

    def _all_inputs(self):
        for pin in range(self.width):
            if self.available_mask & (1 << pin):
                self._directions[pin].setCurrentIndex(0)

    def _outputs_low(self):
        for output in self._outputs:
            output.setChecked(False)
