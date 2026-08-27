"""Qt editor for SPI command profiles; hardware access stays in the session."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .spi_bus import format_spi_hex, parse_spi_hex
from .spi_sequence import SpiDeviceProfile, SpiSequenceStep, builtin_spi_profiles


OPERATIONS = ("write", "read", "write_read", "duplex", "delay")
VALIDATIONS = ("none", "equals", "masked_equals", "not_all_00_ff")


class SpiSequenceWidget(QWidget):
    """Edit/import/export a profile and request execution from its parent."""

    run_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profiles = builtin_spi_profiles()
        self._build_ui()
        self._load_profile(self._profiles[0])

    def _build_ui(self):
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        for profile in self._profiles:
            self.preset_combo.addItem(f"{profile.category} — {profile.name}", profile)
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        toolbar.addWidget(self.preset_combo, 1)
        for label, handler in (("New", self._new), ("Load profile", self._load),
                               ("Save profile", self._save)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        root.addLayout(toolbar)

        metadata = QHBoxLayout()
        metadata.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        metadata.addWidget(self.name_edit, 2)
        metadata.addWidget(QLabel("Category:"))
        self.category_edit = QLineEdit("Generic")
        metadata.addWidget(self.category_edit, 1)
        root.addLayout(metadata)
        self.notes_label = QLabel()
        self.notes_label.setWordWrap(True)
        root.addWidget(self.notes_label)

        columns = ("#", "Name", "Operation", "TX HEX", "RX", "Dummy",
                   "Delay ms", "Validation", "Expected", "Mask", "Result")
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for label, handler in (("Add step", self._add_row), ("Remove", self._remove),
                               ("Move up", lambda: self._move(-1)),
                               ("Move down", lambda: self._move(1))):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(QLabel("Repeat:"))
        self.repeat_spin = QSpinBox(); self.repeat_spin.setRange(1, 1000)
        actions.addWidget(self.repeat_spin)
        selected = QPushButton("Run selected")
        selected.clicked.connect(self._run_selected)
        actions.addWidget(selected)
        self.run_btn = QPushButton("Run sequence")
        self.run_btn.clicked.connect(self._run)
        actions.addWidget(self.run_btn)
        root.addLayout(actions)
        self.status = QLabel("Profiles are editable. Verify commands against the datasheet.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def _make_combo(self, values, selected):
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(selected)
        return combo

    def _add_row(self, step=None):
        step = step or SpiSequenceStep("New step", "write", b"\x00")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 1, QTableWidgetItem(step.name))
        self.table.setCellWidget(row, 2, self._make_combo(OPERATIONS, step.operation))
        for column, value in ((3, format_spi_hex(step.tx)),
                              (5, f"{step.dummy_byte:02X}"),
                              (8, format_spi_hex(step.expected)),
                              (9, format_spi_hex(step.mask)), (10, "")):
            self.table.setItem(row, column, QTableWidgetItem(value))
        rx = QSpinBox(); rx.setRange(0, 65280); rx.setValue(step.read_length)
        delay = QSpinBox(); delay.setRange(0, 3_600_000); delay.setValue(step.delay_ms)
        self.table.setCellWidget(row, 4, rx)
        self.table.setCellWidget(row, 6, delay)
        self.table.setCellWidget(row, 7, self._make_combo(VALIDATIONS, step.validation))

    def _rows(self):
        steps = []
        for row in range(self.table.rowCount()):
            text = lambda column: (self.table.item(row, column).text()
                                   if self.table.item(row, column) else "")
            steps.append(SpiSequenceStep(
                text(1), self.table.cellWidget(row, 2).currentText(),
                parse_spi_hex(text(3)), self.table.cellWidget(row, 4).value(),
                parse_spi_hex(text(5), allow_empty=False)[0],
                self.table.cellWidget(row, 6).value(),
                self.table.cellWidget(row, 7).currentText(),
                parse_spi_hex(text(8)), parse_spi_hex(text(9)),
            ))
        if not steps:
            raise ValueError("Add at least one sequence step.")
        return tuple(steps)

    def profile(self):
        return SpiDeviceProfile(self.name_edit.text(), self.category_edit.text(),
                                self.notes_label.text(), self._rows())

    def _load_profile(self, profile):
        self.name_edit.setText(profile.name)
        self.category_edit.setText(profile.category)
        self.notes_label.setText(profile.notes)
        self.table.setRowCount(0)
        for step in profile.steps:
            self._add_row(step)

    def _preset_changed(self, index):
        profile = self.preset_combo.itemData(index)
        if profile:
            self._load_profile(profile)

    def _new(self):
        self._load_profile(SpiDeviceProfile("Untitled SPI profile"))

    def _remove(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._renumber()

    def _move(self, direction):
        row = self.table.currentRow()
        target = row + direction
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        profile = self.profile()
        steps = list(profile.steps)
        steps[row], steps[target] = steps[target], steps[row]
        self._load_profile(SpiDeviceProfile(profile.name, profile.category,
                                            profile.notes, tuple(steps)))
        self.table.selectRow(target)

    def _renumber(self):
        for row in range(self.table.rowCount()):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

    def _run(self):
        try:
            steps = self._rows()
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}")
            return
        for row in range(self.table.rowCount()):
            self.table.item(row, 10).setText("")
        self.run_requested.emit(steps * self.repeat_spin.value())

    def _run_selected(self):
        try:
            row = self.table.currentRow()
            if row < 0: raise ValueError("Select a step first.")
            step = self._rows()[row]
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}"); return
        self.run_requested.emit((step,) * self.repeat_spin.value())

    def set_busy(self, busy):
        self.run_btn.setEnabled(not busy)

    def show_result(self, result):
        for item in result.get("steps", []):
            row = item["index"]
            if row < self.table.rowCount():
                details = item.get("details") or format_spi_hex(item.get("rx", b""))
                self.table.item(row, 10).setText(f"{item['status']} {details}".strip())
        self.status.setText(
            f"{result.get('status', 'ERROR')}: {len(result.get('steps', []))} step(s), "
            f"{result.get('duration_ms', 0):.2f} ms — {result.get('error', '')}"
        )

    def _save(self):
        try:
            profile = self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "SPI profile", str(exc)); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save SPI profile", "device.spiprofile.json", "SPI profile (*.spiprofile.json)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(profile.to_json())
            except OSError as exc:
                QMessageBox.critical(self, "SPI profile", str(exc))

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load SPI profile", "", "SPI profile (*.spiprofile.json);;JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    self._load_profile(SpiDeviceProfile.from_json(stream.read()))
            except (OSError, ValueError) as exc:
                QMessageBox.critical(self, "SPI profile", str(exc))
