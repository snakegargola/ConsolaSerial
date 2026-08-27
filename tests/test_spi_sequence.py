import unittest

from app.spi_sequence import SpiDeviceProfile, SpiSequenceStep, builtin_spi_profiles


class SpiSequenceTests(unittest.TestCase):
    def test_profile_json_round_trip(self):
        original = SpiDeviceProfile("Sensor", "Sensor", "notes", (
            SpiSequenceStep("Who am I", "write_read", b"\x0f", 1, 0xff,
                            validation="masked_equals", expected=b"\x42", mask=b"\x7f"),
            SpiSequenceStep("Wait", "delay", delay_ms=10),
        ))
        self.assertEqual(SpiDeviceProfile.from_json(original.to_json()), original)

    def test_response_validations(self):
        equals = SpiSequenceStep("ID", "read", read_length=2,
                                 validation="equals", expected=b"\x12\x34")
        self.assertTrue(equals.validate_rx(b"\x12\x34")[0])
        self.assertFalse(equals.validate_rx(b"\x12\x35")[0])
        masked = SpiSequenceStep("Status", "read", read_length=1,
                                 validation="masked_equals", expected=b"\x80", mask=b"\x80")
        self.assertTrue(masked.validate_rx(b"\x81")[0])
        connected = SpiSequenceStep("ID", "read", read_length=3,
                                    validation="not_all_00_ff")
        self.assertFalse(connected.validate_rx(b"\xff\xff\xff")[0])
        self.assertTrue(connected.validate_rx(b"\xef\x40\x18")[0])

    def test_delay_and_validation_errors_are_rejected(self):
        with self.assertRaises(ValueError):
            SpiSequenceStep("Bad delay", "delay")
        with self.assertRaises(ValueError):
            SpiSequenceStep("Bad mask", "read", read_length=1,
                            validation="masked_equals", expected=b"\x01", mask=b"\xff\xff")

    def test_presets_are_read_only_starting_points(self):
        profiles = builtin_spi_profiles()
        self.assertEqual({item.category for item in profiles}, {"Memory", "Display"})
        dangerous = {b"\x02", b"\x20", b"\x52", b"\xd8", b"\xc7"}
        self.assertFalse(any(step.tx[:1] in dangerous for profile in profiles
                             for step in profile.steps))


if __name__ == "__main__":
    unittest.main()
