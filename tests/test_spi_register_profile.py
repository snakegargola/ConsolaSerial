import unittest

from app.spi_register_profile import SpiRegisterProfile


class SpiRegisterProfileTests(unittest.TestCase):
    def test_json_round_trip(self):
        profile = SpiRegisterProfile("Accelerometer", "80", "00", 1, 2, 1,
                                     "little", True, 0.25, -1.0, "g")
        self.assertEqual(SpiRegisterProfile.from_json(profile.to_json()), profile)

    def test_schema_and_width_are_validated(self):
        with self.assertRaises(ValueError): SpiRegisterProfile("", register_bytes=1)
        with self.assertRaises(ValueError): SpiRegisterProfile("Bad", register_bytes=5)
        with self.assertRaises(ValueError): SpiRegisterProfile.from_json("{}")


if __name__ == "__main__": unittest.main()
