"""Hardware-neutral SPI settings and transaction tests."""

import unittest

from app.spi_bus import (
    SPI_MAX_PAYLOAD, SpiBusSettings, SpiTransaction,
    classify_spi_error, execute_spi_transaction, parse_spi_hex,
)


class _FakePort:
    def __init__(self, response=b""):
        self.response = response
        self.calls = []

    def write(self, payload, **kwargs):
        self.calls.append(("write", bytes(payload), kwargs))

    def exchange(self, payload, read_length, **kwargs):
        self.calls.append(("exchange", bytes(payload), read_length, kwargs))
        return self.response[:read_length]


class SpiBusTests(unittest.TestCase):
    def test_settings_validate_frequency_mode_and_chip_select(self):
        valid = SpiBusSettings(
            frequency=10_000_000, mode=3, cs_count=2, chip_select=1
        )
        self.assertEqual(valid.mode, 3)
        for kwargs in (
            {"frequency": 999}, {"frequency": 30_000_001}, {"mode": 4},
            {"cs_count": 0}, {"cs_count": 6},
            {"cs_count": 1, "chip_select": 1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SpiBusSettings(**kwargs)

    def test_hex_parser_accepts_common_notation(self):
        expected = b"\x9F\x00\xAA\x55"
        self.assertEqual(parse_spi_hex("9F 00 AA 55"), expected)
        self.assertEqual(parse_spi_hex("9F00AA55"), expected)
        self.assertEqual(parse_spi_hex("0x9F, 0x00, 0xAA, 0x55"), expected)

    def test_read_uses_physical_half_duplex_input(self):
        transaction = SpiTransaction("read", read_length=3, dummy_byte=0xFF)
        port = _FakePort(b"\x11\x22\x33")
        result = execute_spi_transaction(port, transaction)
        self.assertEqual(result, b"\x11\x22\x33")
        self.assertEqual(port.calls[0][1], b"")
        self.assertFalse(port.calls[0][3]["duplex"])

    def test_write_read_keeps_cs_asserted_between_phases(self):
        transaction = SpiTransaction(
            "write_read", tx=b"\x9F", read_length=3, dummy_byte=0xFF
        )
        port = _FakePort(b"\xEF\x40\x18")
        self.assertEqual(
            execute_spi_transaction(port, transaction), b"\xEF\x40\x18"
        )
        self.assertEqual(
            port.calls,
            [("exchange", b"\x9F", 3,
              {"start": True, "stop": True, "duplex": False})],
        )
        self.assertEqual(transaction.wire_tx, b"\x9F\xFF\xFF\xFF")

    def test_unreliable_generic_full_duplex_is_rejected(self):
        with self.assertRaises(ValueError):
            SpiTransaction("duplex", tx=b"\xAA", read_length=1)

    def test_loopback_cannot_fall_back_to_pyftdi_full_duplex(self):
        transaction = SpiTransaction("loopback", tx=b"\xAA\x55")
        with self.assertRaisesRegex(ValueError, "Physical loopback"):
            execute_spi_transaction(_FakePort(b"\xAA\x55"), transaction)

    def test_invalid_operation_requirements_are_rejected(self):
        for args in (
            ("write", b"", 0), ("read", b"", 0),
            ("write_read", b"\x9F", 0), ("loopback", b"", 0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                SpiTransaction(args[0], tx=args[1], read_length=args[2])

        with self.assertRaises(ValueError):
            SpiTransaction("read", read_length=SPI_MAX_PAYLOAD + 1)

    def test_memory_protection_has_a_stable_error_category(self):
        result = classify_spi_error(PermissionError("Protection bits active"))
        self.assertEqual(result["status"], "PROTECTED")


if __name__ == "__main__":
    unittest.main()
