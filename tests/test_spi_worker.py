"""SPI worker lifecycle and result tests without physical hardware."""

import unittest
from unittest.mock import patch

from app.spi_bus import SpiBusSettings, SpiTransaction
from app.spi_worker import SpiTransactionWorker


class _FakePort:
    frequency = 998_000.4

    def __init__(self, response):
        self.response = response
        self.calls = []

    def write(self, payload, **kwargs):
        self.calls.append((bytes(payload), 0, kwargs))

    def exchange(self, payload, read_length, **kwargs):
        self.calls.append((bytes(payload), read_length, kwargs))
        return self.response[:read_length]


class _FakeController:
    instances = []
    response = b"\xEF\x40\x18"

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.configure_args = None
        self.port_args = None
        self.port = _FakePort(self.response)
        self.closed = False
        self.instances.append(self)

    def configure(self, url, **kwargs):
        self.configure_args = (url, kwargs)

    def get_port(self, chip_select, **kwargs):
        self.port_args = (chip_select, kwargs)
        return self.port

    def close(self):
        self.closed = True


class SpiWorkerTests(unittest.TestCase):
    def setUp(self):
        _FakeController.instances.clear()

    def test_worker_configures_port_reports_jedec_and_closes(self):
        results = []
        settings = SpiBusSettings(
            frequency=1_000_000, mode=0, cs_count=2, chip_select=1
        )
        transaction = SpiTransaction(
            "jedec", tx=b"\x9F", read_length=3, dummy_byte=0xFF
        )
        with patch("pyftdi.spi.SpiController", _FakeController):
            worker = SpiTransactionWorker(
                "ftdi://0x0403:0x6011:TEST/1",
                settings,
                transaction,
                results.append,
            )
            worker.run()

        controller = _FakeController.instances[0]
        self.assertTrue(controller.closed)
        self.assertEqual(controller.port_args, (1, {"freq": 1_000_000, "mode": 0}))
        self.assertEqual(results[0]["status"], "OK")
        self.assertEqual(results[0]["rx"], b"\xEF\x40\x18")
        self.assertEqual(results[0]["actual_frequency"], 998_000)
        self.assertIn("manufacturer 0xEF", results[0]["details"])

    def test_transaction_worker_rejects_unsafe_loopback_path(self):
        _FakeController.response = b"\xAA\x00"
        results = []
        try:
            with patch("pyftdi.spi.SpiController", _FakeController):
                SpiTransactionWorker(
                    "ftdi://test/1",
                    SpiBusSettings(),
                    SpiTransaction("loopback", tx=b"\xAA\x55"),
                    results.append,
                ).run()
        finally:
            _FakeController.response = b"\xEF\x40\x18"
        self.assertEqual(results[0]["status"], "INVALID")
        self.assertIn("Physical loopback", results[0]["error"])
        self.assertTrue(_FakeController.instances[0].closed)


if __name__ == "__main__":
    unittest.main()
