"""Hardware-free tests for raw I2C, SMBus, and bank address behavior."""

import unittest

from app.i2c_worker import I2cLabWorker, resolve_memory_bank


class _FakeController:
    def __init__(self, acknowledged=True):
        self.acknowledged = acknowledged
        self.polls = []

    def poll(self, address, write=False):
        self.polls.append((address, write))
        return self.acknowledged


class _FakePort:
    def __init__(self, reads=(), exchange_result=b""):
        self.reads = list(reads)
        self.exchange_result = exchange_result
        self.calls = []

    def write(self, payload, **options):
        self.calls.append(("write", bytes(payload), options))

    def read(self, length, **options):
        self.calls.append(("read", length, options))
        return self.reads.pop(0) if self.reads else bytes(length)

    def exchange(self, payload, length, **options):
        self.calls.append(("exchange", bytes(payload), length, options))
        return self.exchange_result


def _worker(request):
    return I2cLabWorker("unused", 100_000, request, lambda _result: None, lambda _error: None)


class I2cTransactionTests(unittest.TestCase):
    def test_raw_write_read_uses_one_exchange_for_repeated_start(self):
        port = _FakePort(exchange_result=b"\xAA\x55")
        result = _worker({
            "protocol": "raw", "operation": "write_read", "address": 0x50,
            "payload": b"\x10", "read_length": 2,
        })._raw_transaction(_FakeController(), port)
        self.assertEqual(result, b"\xAA\x55")
        self.assertEqual(port.calls, [("exchange", b"\x10", 2, {})])

    def test_smbus_word_read_preserves_little_endian_wire_bytes(self):
        port = _FakePort(exchange_result=b"\x34\x12")
        result = _worker({
            "protocol": "smbus", "operation": "read_word", "address": 0x48,
            "command": 1,
        })._smbus_transaction(_FakeController(), port)
        self.assertEqual(result, b"\x34\x12")
        self.assertEqual(port.calls, [("exchange", b"\x01", 2, {})])

    def test_smbus_block_read_continues_without_new_start(self):
        port = _FakePort(reads=(b"\x03", b"\x10\x20\x30"))
        result = _worker({
            "protocol": "smbus", "operation": "block_read", "address": 0x50,
            "command": 2, "read_length": 32,
        })._smbus_transaction(_FakeController(), port)
        self.assertEqual(result, b"\x10\x20\x30")
        self.assertEqual(port.calls, [
            ("write", b"\x02", {"relax": False}),
            ("read", 1, {"relax": False}),
            ("read", 3, {"start": False}),
        ])

    def test_invalid_block_length_releases_bus_before_error(self):
        port = _FakePort(reads=(b"\x00", b""))
        with self.assertRaisesRegex(ValueError, "Invalid SMBus block length"):
            _worker({
                "protocol": "smbus", "operation": "block_read",
                "address": 0x50, "command": 2, "read_length": 32,
            })._smbus_transaction(_FakeController(), port)
        self.assertEqual(port.calls[-1], ("read", 0, {"start": False}))

    def test_memory_bank_maps_upper_bits_to_slave_address(self):
        self.assertEqual(resolve_memory_bank(0x50, 0x0123, 0x100), (0x51, 0x23))
        self.assertEqual(resolve_memory_bank(0x50, 0x0123, 0), (0x50, 0x123))
        with self.assertRaises(ValueError):
            resolve_memory_bank(0x77, 0x100, 0x100)


if __name__ == "__main__":
    unittest.main()
