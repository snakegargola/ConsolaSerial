"""Qt editor and reporter for SPI sequences; hardware stays in the session."""

from __future__ import annotations

import csv
import json

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .spi_bus import format_spi_hex, parse_spi_hex
from .spi_sequence import SpiDeviceProfile, SpiSequenceStep, builtin_spi_profiles


OPERATIONS = ("write", "read", "write_read", "duplex", "loopback", "delay")
VALIDATIONS = ("none", "equals", "masked_equals", "not_all_00_ff")


class SpiSequenceWidget(QWidget):
    """Edit/import/export a profile and request execution from its parent."""

    run_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent); self._last_result = None; self._run_number = 0
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

        # Keep the outcome above the scrollable table so it is always visible.
        self.result_banner = QLabel("READY — press Run sequence to start")
        self.result_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_banner.setMinimumHeight(46)
        self._set_banner("READY — select a preset and press Run sequence", "#3A7CA5")
        root.addWidget(self.result_banner)

        columns = ("#", "Name", "Operation", "TX HEX", "RX", "Dummy",
                   "Delay ms", "Validation", "Expected", "Mask", "Result")
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
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
        actions.addWidget(QLabel("Timeout:"))
        self.timeout_spin = QSpinBox(); self.timeout_spin.setRange(1, 3600); self.timeout_spin.setValue(30); self.timeout_spin.setSuffix(" s")
        actions.addWidget(self.timeout_spin)
        self.stop_btn = QPushButton("Stop"); self.stop_btn.setEnabled(False)
        actions.addWidget(self.stop_btn)
        report = QPushButton("Export report")
        report.clicked.connect(self._export_report)
        actions.addWidget(report)
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
        for column, value in ((3, step.tx_template or format_spi_hex(step.tx)),
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
            tx_text = text(3)
            is_template = "{" in tx_text
            steps.append(SpiSequenceStep(
                text(1), self.table.cellWidget(row, 2).currentText(),
                b"" if is_template else parse_spi_hex(tx_text), self.table.cellWidget(row, 4).value(),
                parse_spi_hex(text(5), allow_empty=False)[0],
                self.table.cellWidget(row, 6).value(),
                self.table.cellWidget(row, 7).currentText(),
                parse_spi_hex(text(8)), parse_spi_hex(text(9)),
                tx_template=tx_text if is_template else "",
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
        self._clear_previous_result()
        try:
            steps = self._rows()
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}")
            return
        total = len(steps) * self.repeat_spin.value()
        self._set_banner(f"RUN #{self._run_number} RUNNING — 0/{total} completed", "#B7791F")
        self.status.setText("SPI opens the FTDI interface for this operation and closes it when finished.")
        self.run_requested.emit(steps * self.repeat_spin.value())

    def _run_selected(self):
        self._clear_previous_result()
        try:
            row = self.table.currentRow()
            if row < 0: raise ValueError("Select a step first.")
            step = self._rows()[row]
        except ValueError as exc:
            self.status.setText(f"INVALID: {exc}"); return
        total = self.repeat_spin.value()
        self._set_banner(f"RUN #{self._run_number} RUNNING — 0/{total} completed", "#B7791F")
        self.run_requested.emit((step,) * total)

    def _clear_previous_result(self):
        self._run_number += 1
        self._last_result = None
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 10)
            if item is not None:
                item.setText("")
        self._set_banner(f"RUN #{self._run_number} — clearing previous RX/result…", "#3A7CA5")
        self.status.setText("Previous result and report cleared.")

    def set_busy(self, busy):
        self.run_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    def show_result(self, result):
        self._last_result = result
        for item in result.get("steps", []):
            row = item["index"]
            if row < self.table.rowCount():
                details = item.get("details") or format_spi_hex(item.get("rx", b""))
                self.table.item(row, 10).setText(f"{item['status']} {details}".strip())
        completed = len(result.get("steps", []))
        passed = sum(item.get("status") == "PASS" for item in result.get("steps", []))
        failed = sum(item.get("status") == "FAIL" for item in result.get("steps", []))
        status = result.get("status", "ERROR")
        successful = status in ("OK", "PASS") and not failed
        color = "#238636" if successful else "#C62828"
        if status == "STOPPED": color = "#6B7280"
        outcome = "PASS — TEST COMPLETED CORRECTLY" if successful else status
        self._set_banner(f"RUN #{self._run_number} {outcome} — completed {completed}, PASS {passed}, FAIL {failed}", color)
        if self.table.rowCount():
            self.table.scrollToItem(self.table.item(0, 10), QAbstractItemView.ScrollHint.PositionAtCenter)
        self.status.setText(
            f"{result.get('status', 'ERROR')}: {len(result.get('steps', []))} step(s), "
            f"{result.get('duration_ms', 0):.2f} ms — {result.get('error', '')}"
        )

    def _set_banner(self, text, color):
        self.result_banner.setText(text)
        self.result_banner.setStyleSheet(
            f"font-size:16px;font-weight:bold;color:white;background:{color};"
            "border-radius:6px;padding:8px;"
        )

    def _export_report(self):
        if not self._last_result:
            self.status.setText("Run a sequence before exporting a report."); return
        path, selected = QFileDialog.getSaveFileName(
            self, "Export SPI validation report", "spi-validation-report.json",
            "JSON (*.json);;CSV (*.csv)")
        if not path: return
        try:
            steps = []
            for item in self._last_result.get("steps", []):
                row = dict(item); row["tx"] = format_spi_hex(row.get("tx", b"")); row["rx"] = format_spi_hex(row.get("rx", b""))
                steps.append(row)
            with open(path, "w", encoding="utf-8", newline="") as stream:
                if path.lower().endswith(".csv") or selected.startswith("CSV"):
                    if steps:
                        writer = csv.DictWriter(stream, fieldnames=steps[0].keys()); writer.writeheader(); writer.writerows(steps)
                else:
                    summary = {key: value for key, value in self._last_result.items() if key != "steps"}
                    summary["steps"] = steps; json.dump(summary, stream, indent=2, ensure_ascii=False)
            self.status.setText(f"Report exported: {path}")
        except OSError as exc: self.status.setText(f"ERROR: {exc}")

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
