"""Unit tests for generic I2C value encoding and decoding."""

import unittest

from app.i2c_value_codec import decode_i2c_value, encode_i2c_value


class DecodeI2cValueTests(unittest.TestCase):
    def test_tmp102_positive_temperature(self):
        decoded = decode_i2c_value(
            bytes.fromhex("19 80"), signed=True, bit_width=12,
            right_shift=4, scale=0.0625,
        )
        self.assertEqual(decoded.signed, 408)
        self.assertEqual(decoded.scaled, 25.5)
        self.assertEqual(decoded.hexadecimal, "0x198")
        self.assertEqual(decoded.octal, "0o630")

    def test_tmp102_negative_temperature_sign_extends_value_bits(self):
        decoded = decode_i2c_value(
            bytes.fromhex("F6 00"), signed=True, bit_width=12,
            right_shift=4, scale=0.0625,
        )
        self.assertEqual(decoded.signed, -160)
        self.assertEqual(decoded.scaled, -10.0)

    def test_mask_shift_scale_and_offset_pipeline(self):
        decoded = decode_i2c_value(
            bytes.fromhex("AB CD"), bit_width=8, right_shift=4,
            mask=0xFF, scale=0.5, offset=1,
        )
        self.assertEqual(decoded.unsigned, 0xBC)
        self.assertEqual(decoded.scaled, 95.0)

    def test_shift_and_value_width_must_fit_payload(self):
        with self.assertRaises(ValueError):
            decode_i2c_value(b"\xFF", bit_width=8, right_shift=1)

    def test_mask_must_fit_value_width(self):
        with self.assertRaises(ValueError):
            decode_i2c_value(b"\xFF", bit_width=4, mask=0xFF)


class EncodeI2cValueTests(unittest.TestCase):
    def test_common_numeric_formats_are_equivalent(self):
        cases = (
            ("255", "Decimal"), ("FF", "Hexadecimal"),
            ("377", "Octal"), ("11111111", "Binary"),
        )
        for text, input_format in cases:
            with self.subTest(input_format=input_format):
                self.assertEqual(
                    encode_i2c_value(text, input_format=input_format, length=1),
                    b"\xFF",
                )

    def test_signed_little_endian_value(self):
        self.assertEqual(
            encode_i2c_value(
                "-10", input_format="Decimal", length=2,
                byteorder="little", signed=True,
            ),
            b"\xF6\xFF",
        )

    def test_hex_byte_count_is_validated(self):
        with self.assertRaises(ValueError):
            encode_i2c_value("AA", input_format="HEX bytes", length=2)


if __name__ == "__main__":
    unittest.main()
