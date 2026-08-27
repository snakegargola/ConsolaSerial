import unittest

from app.spi_register_map import SpiRegisterDefinition, SpiRegisterMap


class SpiRegisterMapTests(unittest.TestCase):
    def test_profile_round_trip_and_command_flags(self):
        profile = SpiRegisterMap("Sensor", 0x80, 0, 1, 1, (
            SpiRegisterDefinition("ID", 0x0F),
            SpiRegisterDefinition("VALUE", 0x20, 2, "R", "little", True, 0.5, 1, "C"),
        ))
        loaded = SpiRegisterMap.from_json(profile.to_json())
        self.assertEqual(loaded, profile)
        self.assertEqual(loaded.command(loaded.registers[0]), b"\x8f")

    def test_invalid_access_and_address_width_are_rejected(self):
        with self.assertRaises(ValueError): SpiRegisterDefinition("Bad", 0, access="X")
        with self.assertRaises(ValueError):
            SpiRegisterMap("Bad", address_bytes=1,
                           registers=(SpiRegisterDefinition("Wide", 0x100),))


if __name__ == "__main__": unittest.main()
