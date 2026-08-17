"""Hardware-independent tests for SerialWorker UART control operations."""

import unittest
from unittest.mock import patch

from app.serial_worker import SerialWorker


class _FakeSerial:
    def __init__(self):
        self.is_open = True
        self.rts = False
        self.dtr = False
        self.break_condition = False
        self.cts = True
        self.dsr = False
        self.cd = True
        self.ri = False
        self.cancelled = False

    def cancel_read(self):
        self.cancelled = True


class _OpenTrackingSerial:
    def __init__(self):
        self.is_open = False
        self.rts = True
        self.dtr = True
        self.states_at_open = None

    def open(self):
        self.states_at_open = (self.rts, self.dtr)
        self.is_open = True

    def close(self):
        self.is_open = False


class _ReadOnceSerial(_OpenTrackingSerial):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def read(self, _size):
        payload, self.payload = self.payload, b""
        return payload


class SerialWorkerControlTests(unittest.TestCase):
    def _worker(self):
        return SerialWorker(
            port="TEST",
            baud=115200,
            databits=8,
            parity="None",
            stopbits="1",
            flowcontrol="None",
            eol_rx="None",
            on_data=lambda _data: None,
            on_error=lambda _error: None,
        )

    def test_output_lines_and_break_are_controllable(self):
        worker = self._worker()
        fake = _FakeSerial()
        worker._serial = fake

        self.assertEqual(worker.set_control_line("RTS", True), (True, ""))
        self.assertEqual(worker.set_control_line("DTR", True), (True, ""))
        self.assertEqual(worker.set_break(True), (True, ""))
        self.assertTrue(fake.rts)
        self.assertTrue(fake.dtr)
        self.assertTrue(fake.break_condition)

    def test_modem_input_status_is_normalized(self):
        worker = self._worker()
        worker._serial = _FakeSerial()

        status, error = worker.modem_status()
        self.assertEqual(error, "")
        self.assertEqual(
            status,
            {"CTS": True, "DSR": False, "DCD": True, "RI": False},
        )

    def test_disconnected_controls_return_a_friendly_error(self):
        worker = self._worker()
        self.assertFalse(worker.set_control_line("RTS", True)[0])
        self.assertFalse(worker.set_break(True)[0])
        self.assertIsNone(worker.modem_status()[0])

    def test_stop_wakes_a_pending_read(self):
        worker = self._worker()
        fake = _FakeSerial()
        worker._serial = fake
        worker.stop()
        self.assertTrue(fake.cancelled)

    def test_initial_outputs_are_configured_before_port_open(self):
        worker = SerialWorker(
            port="TEST",
            baud=115200,
            databits=8,
            parity="None",
            stopbits="1",
            flowcontrol="None",
            eol_rx="None",
            on_data=lambda _data: None,
            on_error=lambda _error: None,
            initial_rts=False,
            initial_dtr=False,
        )
        fake = _OpenTrackingSerial()
        worker._stop_event.set()
        with patch("app.serial_worker.serial.Serial", return_value=fake):
            worker.run()
        self.assertEqual(fake.states_at_open, (False, False))

    def test_raw_callback_receives_bytes_before_eol_framing(self):
        raw_chunks = []
        framed_chunks = []
        worker = None

        def receive_raw(data):
            raw_chunks.append(data)
            worker._stop_event.set()

        worker = SerialWorker(
            port="TEST",
            baud=115200,
            databits=8,
            parity="None",
            stopbits="1",
            flowcontrol="None",
            eol_rx="LF",
            on_data=framed_chunks.append,
            on_error=lambda _error: None,
            on_raw_data=receive_raw,
        )
        fake = _ReadOnceSerial(b"\x00\xA5binary-without-eol")
        with patch("app.serial_worker.serial.Serial", return_value=fake):
            worker.run()

        self.assertEqual(raw_chunks, [b"\x00\xA5binary-without-eol"])
        self.assertEqual(framed_chunks, [])


if __name__ == "__main__":
    unittest.main()
