"""Unit tests for shared I2C configuration, parsing, PEC, and errors."""

import unittest

from app.i2c_bus import (
    I2cBusSettings, append_write_pec, classify_i2c_error,
    configure_i2c_controller, parse_hex_bytes, smbus_pec,
    verify_read_pec,
)


class _FakeController:
    def __init__(self):
        self.frequency = 97_500
        self.retry_count = None
        self.configuration = None

    def set_retry_count(self, count):
        self.retry_count = count

    def configure(self, url, **options):
        self.configuration = (url, options)


class I2cBusTests(unittest.TestCase):
    def test_settings_are_applied_consistently(self):
        controller = _FakeController()
        actual = configure_i2c_controller(
            controller, "ftdi://ftdi:232h/1",
            I2cBusSettings(100_000, clock_stretching=True, retry_count=5),
        )
        self.assertEqual(actual, 97_500)
        self.assertEqual(controller.retry_count, 5)
        self.assertEqual(controller.configuration, (
            "ftdi://ftdi:232h/1",
            {"frequency": 100_000, "clockstretching": True},
        ))

    def test_invalid_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            I2cBusSettings(999)
        with self.assertRaises(ValueError):
            I2cBusSettings(retry_count=0)
        with self.assertRaises(ValueError):
            I2cBusSettings(retry_count=17)

    def test_friendly_hex_parser(self):
        self.assertEqual(parse_hex_bytes("0x01, 7f-FF"), b"\x01\x7f\xff")
        with self.assertRaises(ValueError):
            parse_hex_bytes("123")

    def test_pec_matches_standard_crc8_check_vector(self):
        self.assertEqual(smbus_pec(b"123456789"), 0xF4)

    def test_write_and_read_pec_frames(self):
        write = append_write_pec(0x5A, b"\x10\x22")
        self.assertEqual(write[-1], smbus_pec(b"\xB4\x10\x22"))

        payload = b"\x34\x12"
        pec = smbus_pec(b"\xB4\x10\xB5" + payload)
        self.assertEqual(
            verify_read_pec(0x5A, 0x10, payload + bytes((pec,))), payload
        )
        with self.assertRaisesRegex(ValueError, "PEC mismatch"):
            verify_read_pec(0x5A, 0x10, payload + b"\x00")

    def test_errors_receive_stable_categories(self):
        self.assertEqual(classify_i2c_error(ValueError("bad"))["status"], "INVALID")
        self.assertEqual(
            classify_i2c_error(RuntimeError("device returned NACK"))["status"],
            "NACK",
        )


if __name__ == "__main__":
    unittest.main()
