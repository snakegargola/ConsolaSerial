"""Reusable UART control-line and binary loopback panel."""

from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
)

from .uart_loopback import LoopbackStreamMatcher, build_loopback_frame


class UartToolsPanel(QGroupBox):
    """Control UART modem lines and run framed TX-to-RX loopback tests."""

    def __init__(self, can_start_loopback=None, status_callback=None, parent=None):
        super().__init__("UART hardware control and loopback", parent)
        self._worker = None
        self._flow_control = "None"
        self._can_start_loopback = can_start_loopback or (lambda: (True, ""))
        self._status_callback = status_callback or (lambda _message: None)
        self._matcher = LoopbackStreamMatcher()
        self._active = False
        self._frame_index = 0
        self._passed = 0
        self._failed = 0
        self._bytes_sent = 0
        self._started_at = 0.0

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._frame_timed_out)
        self._modem_timer = QTimer(self)
        self._modem_timer.setInterval(500)
        self._modem_timer.timeout.connect(self._poll_modem_inputs)
        self._modem_timer.start()

        self._build_ui()
        self._update_availability()

    @property
    def loopback_active(self):
        return self._active

    @property
    def output_states(self):
        return self.rts_check.isChecked(), self.dtr_check.isChecked()

    def _build_ui(self):
        grid = QGridLayout(self)
        grid.setSpacing(4)

        grid.addWidget(QLabel("Outputs:"), 0, 0)
        self.rts_check = QCheckBox("RTS")
        self.rts_check.setToolTip(
            "Manually assert RTS. Disabled while RTS/CTS flow control is active."
        )
        self.dtr_check = QCheckBox("DTR")
        self.dtr_check.setToolTip(
            "Manually assert DTR. Some development boards use DTR to reset."
        )
        self.break_btn = QPushButton("Send BREAK (250 ms)")
        self.break_btn.setToolTip(
            "Hold TX in BREAK state for 250 ms without blocking the interface."
        )
        self.rts_check.toggled.connect(
            lambda asserted: self._set_output("RTS", asserted)
        )
        self.dtr_check.toggled.connect(
            lambda asserted: self._set_output("DTR", asserted)
        )
        self.break_btn.clicked.connect(self._send_break)
        grid.addWidget(self.rts_check, 0, 1)
        grid.addWidget(self.dtr_check, 0, 2)
        grid.addWidget(self.break_btn, 0, 3)

        grid.addWidget(QLabel("Inputs:"), 0, 4)
        self.modem_labels = {}
        for column, line in enumerate(("CTS", "DSR", "DCD", "RI"), start=5):
            indicator = QLabel()
            indicator.setMinimumWidth(58)
            indicator.setToolTip(f"Live {line} modem-input state")
            self.modem_labels[line] = indicator
            self._set_indicator(line, None)
            grid.addWidget(indicator, 0, column)

        grid.addWidget(QLabel("Loopback:"), 1, 0)
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(1, 1000)
        self.frames_spin.setValue(16)
        self.frames_spin.setSuffix(" frames")
        self.frames_spin.setToolTip("Number of verified test frames")
        grid.addWidget(self.frames_spin, 1, 1, 1, 2)

        self.payload_spin = QSpinBox()
        self.payload_spin.setRange(1, 4096)
        self.payload_spin.setValue(64)
        self.payload_spin.setSuffix(" payload B")
        self.payload_spin.setToolTip(
            "Binary payload bytes per frame; each frame adds 12 framing bytes."
        )
        grid.addWidget(self.payload_spin, 1, 3, 1, 2)

        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 10.0)
        self.timeout_spin.setSingleStep(0.1)
        self.timeout_spin.setValue(1.0)
        self.timeout_spin.setSuffix(" s timeout")
        self.timeout_spin.setToolTip("Maximum echo time for each frame")
        grid.addWidget(self.timeout_spin, 1, 5, 1, 2)

        self.run_btn = QPushButton("Run TX→RX loopback")
        self.run_btn.setToolTip(
            "Connect TX to RX on this UART, then verify binary test frames."
        )
        self.run_btn.clicked.connect(self._toggle_loopback)
        grid.addWidget(self.run_btn, 1, 7, 1, 2)

        self.result_label = QLabel(
            "Connect TX to RX, connect the port, then run the test."
        )
        self.result_label.setWordWrap(True)
        grid.addWidget(self.result_label, 2, 0, 1, 9)
        grid.setColumnStretch(8, 1)

    def set_connection(self, worker, flow_control):
        """Attach a connected SerialWorker, or detach on disconnect."""
        if worker is not self._worker and self._active:
            self._finish(cancelled=True, reason="UART disconnected")
        self._worker = worker if worker and worker.is_connected else None
        self._flow_control = str(flow_control)
        if self._worker:
            self._apply_outputs()
        self._poll_modem_inputs()
        self._update_availability()

    def set_flow_control(self, flow_control):
        self._flow_control = str(flow_control)
        if self._worker:
            self._apply_outputs()
        self._update_availability()

    def feed_raw_data(self, data):
        """Feed unframed RX bytes; EOL settings never affect loopback."""
        if self._active and self._matcher.feed(data):
            self._timeout_timer.stop()
            self._passed += 1
            self._frame_index += 1
            QTimer.singleShot(0, self._send_next_frame)

    def load_config(self, config):
        self.rts_check.setChecked(bool(config.get("uart_rts", True)))
        self.dtr_check.setChecked(bool(config.get("uart_dtr", True)))
        self.frames_spin.setValue(int(config.get("uart_loopback_frames", 16)))
        self.payload_spin.setValue(
            int(config.get("uart_loopback_payload_size", 64))
        )
        self.timeout_spin.setValue(
            float(config.get("uart_loopback_timeout", 1.0))
        )

    def collect_config(self, config):
        config.set("uart_rts", self.rts_check.isChecked())
        config.set("uart_dtr", self.dtr_check.isChecked())
        config.set("uart_loopback_frames", self.frames_spin.value())
        config.set("uart_loopback_payload_size", self.payload_spin.value())
        config.set("uart_loopback_timeout", self.timeout_spin.value())

    def shutdown(self):
        if self._active:
            self._finish(cancelled=True, reason="UART session closed")
        self._timeout_timer.stop()
        self._worker = None
        self._poll_modem_inputs()
        self._update_availability()

    def _set_output(self, line, asserted):
        if not self._worker:
            return
        if line == "RTS" and self._flow_control == "RTS/CTS":
            return
        success, error = self._worker.set_control_line(line, asserted)
        if not success:
            self._show_status(f"Could not set {line}: {error}")

    def _apply_outputs(self):
        if self._flow_control != "RTS/CTS":
            self._set_output("RTS", self.rts_check.isChecked())
        self._set_output("DTR", self.dtr_check.isChecked())

    def _send_break(self):
        worker = self._worker
        if not worker:
            return
        success, error = worker.set_break(True)
        if not success:
            self._show_status(f"Could not assert BREAK: {error}")
            return
        self.break_btn.setEnabled(False)
        self._show_status("UART BREAK asserted for 250 ms.")
        QTimer.singleShot(250, lambda: self._release_break(worker))

    def _release_break(self, worker):
        if worker is self._worker and worker.is_connected:
            success, error = worker.set_break(False)
            if not success:
                self._show_status(f"Could not release BREAK: {error}")
        self._update_availability()

    def _set_indicator(self, line, state):
        indicator = self.modem_labels[line]
        if state is True:
            indicator.setText(f"{line}: ●")
            indicator.setStyleSheet("color:#00C853; font-weight:bold;")
        elif state is False:
            indicator.setText(f"{line}: ○")
            indicator.setStyleSheet("color:#777777;")
        else:
            indicator.setText(f"{line}: ?")
            indicator.setStyleSheet("color:#A0A0A0;")

    def _poll_modem_inputs(self):
        status = None
        if self._worker and self._worker.is_connected:
            status, _error = self._worker.modem_status()
        for line in self.modem_labels:
            self._set_indicator(line, None if status is None else status.get(line))

    def _update_availability(self):
        connected = bool(self._worker and self._worker.is_connected)
        self.rts_check.setEnabled(connected and self._flow_control != "RTS/CTS")
        self.dtr_check.setEnabled(connected)
        self.break_btn.setEnabled(connected)
        self.frames_spin.setEnabled(not self._active)
        self.payload_spin.setEnabled(not self._active)
        self.timeout_spin.setEnabled(not self._active)
        self.run_btn.setEnabled(connected or self._active)

    def _toggle_loopback(self):
        if self._active:
            self._finish(cancelled=True)
            return
        if not self._worker or not self._worker.is_connected:
            self.result_label.setText("Connect the UART before running loopback.")
            return
        allowed, reason = self._can_start_loopback()
        if not allowed:
            self.result_label.setText(reason)
            return

        self._matcher.reset()
        self._active = True
        self._frame_index = 0
        self._passed = 0
        self._failed = 0
        self._bytes_sent = 0
        self._started_at = time.monotonic()
        self.run_btn.setText("Stop loopback")
        self.result_label.setText("Starting binary TX→RX loopback…")
        self._update_availability()
        self._send_next_frame()

    def _send_next_frame(self):
        if not self._active:
            return
        total = self.frames_spin.value()
        if self._frame_index >= total:
            self._finish()
            return
        if not self._worker or not self._worker.is_connected:
            self._finish(cancelled=True, reason="UART disconnected")
            return

        frame = build_loopback_frame(self._frame_index, self.payload_spin.value())
        self._matcher.expect(frame)
        if not self._worker.send(frame):
            self._matcher.abandon()
            self._finish(cancelled=True, reason="TX write failed")
            return
        self._bytes_sent += len(frame)
        self.result_label.setText(
            f"Testing frame {self._frame_index + 1}/{total}…"
        )
        self._timeout_timer.start(int(self.timeout_spin.value() * 1000))

    def _frame_timed_out(self):
        if not self._active:
            return
        self._matcher.abandon()
        self._failed += 1
        self._frame_index += 1
        self._send_next_frame()

    def _finish(self, cancelled=False, reason=""):
        if not self._active:
            return
        self._timeout_timer.stop()
        if self._matcher.waiting:
            self._matcher.abandon()
        self._active = False
        elapsed = max(0.0, time.monotonic() - self._started_at)
        total = self.frames_spin.value()
        if cancelled:
            prefix = "CANCELLED"
        elif self._failed or self._matcher.unexpected_bytes:
            prefix = "FAIL"
        else:
            prefix = "PASS"
        result = (
            f"{prefix}: {self._passed}/{total} frames passed, "
            f"{self._failed} timed out, TX {self._bytes_sent} B, "
            f"RX {self._matcher.received_bytes} B, "
            f"unexpected {self._matcher.unexpected_bytes} B, {elapsed:.3f} s"
        )
        if reason:
            result += f" — {reason}"
        self.result_label.setText(result)
        self.run_btn.setText("Run TX→RX loopback")
        self._show_status(result)
        self._update_availability()

    def _show_status(self, message):
        self._status_callback(str(message))
