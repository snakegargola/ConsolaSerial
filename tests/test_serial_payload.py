"""Tests for strict serial HEX parsing and exact byte previews."""

import unittest

from app.serial_payload import (
    encode_serial_payload, format_payload_preview, parse_hex_payload,
)


class SerialPayloadTests(unittest.TestCase):
    def test_hex_accepts_pairs_with_or_without_spaces(self):
        self.assertEqual(parse_hex_payload("AA 55 0d 0A"), b"\xAA\x55\x0D\x0A")
        self.assertEqual(parse_hex_payload("AA550D0A"), b"\xAA\x55\x0D\x0A")

    def test_hex_rejects_invalid_or_incomplete_input(self):
        for value in ("0xAA", "AA,55", "GG", "A", "AAA"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_hex_payload(value)

    def test_preview_includes_the_configured_eol(self):
        payload = encode_serial_payload("A", "ASCII", b"\r\n")
        self.assertEqual(payload, b"A\r\n")
        self.assertEqual(format_payload_preview(payload), "41 0D 0A")


if __name__ == "__main__":
    unittest.main()
