"""UI-level tests for the reusable UART hardware/loopback panel."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.uart_tools_widget import UartToolsPanel


class _FakeWorker:
    def __init__(self):
        self.is_connected = True
        self.sent = []
        self.outputs = {}
        self.break_state = False

    def set_control_line(self, line, asserted):
        self.outputs[line] = bool(asserted)
        return True, ""

    def set_break(self, asserted):
        self.break_state = bool(asserted)
        return True, ""

    def modem_status(self):
        return {"CTS": True, "DSR": False, "DCD": True, "RI": False}, ""

    def send(self, payload):
        self.sent.append(bytes(payload))
        return True


class _MemoryConfig:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class UartToolsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self):
        panel = UartToolsPanel()
        self.addCleanup(panel.close)
        return panel

    def test_connection_applies_saved_outputs_and_reads_inputs(self):
        panel = self._panel()
        config = _MemoryConfig()
        config.values.update({"uart_rts": True, "uart_dtr": True})
        panel.load_config(config)
        worker = _FakeWorker()

        panel.set_connection(worker, "None")
        panel._poll_modem_inputs()

        self.assertEqual(worker.outputs, {"RTS": True, "DTR": True})
        self.assertIn("●", panel.modem_labels["CTS"].text())
        self.assertIn("○", panel.modem_labels["DSR"].text())

    def test_rts_is_not_manual_during_hardware_flow_control(self):
        panel = self._panel()
        worker = _FakeWorker()
        panel.set_connection(worker, "RTS/CTS")
        self.assertFalse(panel.rts_check.isEnabled())

    def test_loopback_verifies_complete_echoes(self):
        panel = self._panel()
        worker = _FakeWorker()
        panel.frames_spin.setValue(3)
        panel.payload_spin.setValue(16)
        panel.set_connection(worker, "None")

        panel.run_btn.click()
        for index in range(3):
            frame = worker.sent[index]
            panel.feed_raw_data(frame[:5])
            panel.feed_raw_data(frame[5:])
            self.app.processEvents()

        self.assertFalse(panel.loopback_active)
        self.assertIn("PASS: 3/3", panel.result_label.text())
        self.assertIn("unexpected 0 B", panel.result_label.text())

    def test_loopback_timeout_is_reported_as_failure(self):
        panel = self._panel()
        worker = _FakeWorker()
        panel.frames_spin.setValue(1)
        panel.set_connection(worker, "None")

        panel.run_btn.click()
        panel._frame_timed_out()

        self.assertFalse(panel.loopback_active)
        self.assertIn("FAIL: 0/1", panel.result_label.text())
        self.assertIn("1 timed out", panel.result_label.text())

    def test_settings_round_trip(self):
        panel = self._panel()
        config = _MemoryConfig()
        panel.rts_check.setChecked(True)
        panel.dtr_check.setChecked(False)
        panel.frames_spin.setValue(25)
        panel.payload_spin.setValue(128)
        panel.timeout_spin.setValue(2.5)
        panel.collect_config(config)

        restored = self._panel()
        restored.load_config(config)
        self.assertTrue(restored.rts_check.isChecked())
        self.assertFalse(restored.dtr_check.isChecked())
        self.assertEqual(restored.frames_spin.value(), 25)
        self.assertEqual(restored.payload_spin.value(), 128)
        self.assertEqual(restored.timeout_spin.value(), 2.5)


if __name__ == "__main__":
    unittest.main()
