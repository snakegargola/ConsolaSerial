"""Unit tests for safe datasheet formulas, bit fields, and enumerations."""

import unittest

from app.i2c_formula import evaluate_formula, extract_bit_field, parse_enum_map


class I2cFormulaTests(unittest.TestCase):
    def test_formula_uses_documented_variables_and_functions(self):
        value = evaluate_formula(
            "round(x * 1.8 + 32, 2)", x=25, raw=400, unsigned=400, signed=400
        )
        self.assertEqual(value, 77)
        self.assertEqual(
            evaluate_formula("(raw >> 4) & 0x0F", x=0, raw=0xAB, unsigned=0, signed=0),
            0x0A,
        )

    def test_unsafe_or_excessive_expressions_are_rejected(self):
        for expression in (
            "__import__('os')", "x.__class__", "2 ** 1000000", "1 << 200",
            "round()",
        ):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                evaluate_formula(expression, x=1)

    def test_bit_fields_and_enum_maps(self):
        self.assertEqual(extract_bit_field(0b10110100, "7:5"), 0b101)
        self.assertEqual(extract_bit_field(0b10110100, "2"), 1)
        self.assertEqual(parse_enum_map("0=Sleep, 1=Active, 0x2=Fault"), {
            0: "Sleep", 1: "Active", 2: "Fault",
        })

    def test_invalid_bit_field_and_enum_are_rejected(self):
        with self.assertRaises(ValueError):
            extract_bit_field(0, "2:7")
        with self.assertRaises(ValueError):
            parse_enum_map("Active")


if __name__ == "__main__":
    unittest.main()
