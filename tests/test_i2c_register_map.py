"""Unit tests for validated I2C register-map profiles."""

import unittest

from app.i2c_register_map import I2cDeviceProfile, RegisterDefinition


class I2cRegisterMapTests(unittest.TestCase):
    def test_profile_json_round_trip_preserves_conversion(self):
        profile = I2cDeviceProfile(
            name="TMP102",
            device_address=0x48,
            registers=(RegisterDefinition(
                name="Temperature", address=0x00, length=2, access="R",
                signed=True, bit_width=12, right_shift=4,
                scale=0.0625, unit="°C", formula="x * 1.8 + 32",
                bit_field="3:2", enum_map="0=Off,1=On",
            ),),
        )
        self.assertEqual(I2cDeviceProfile.from_dict(profile.to_dict()), profile)
        self.assertEqual(profile.to_dict()["version"], 2)

    def test_version_one_profile_remains_compatible(self):
        profile = I2cDeviceProfile.from_dict({
            "schema": "serial-monitor.i2c-register-map",
            "version": 1,
            "name": "Legacy",
            "device_address": "0x50",
            "registers": [{"name": "Status", "register": "0x00"}],
        })
        self.assertEqual(profile.registers[0].formula, "x")

    def test_16_bit_register_address_is_supported(self):
        profile = I2cDeviceProfile(
            name="Wide register device", device_address=0x50,
            register_width=2,
            registers=(RegisterDefinition(name="Data", address=0x1234),),
        )
        self.assertEqual(profile.registers[0].address, 0x1234)

    def test_register_address_must_fit_profile_width(self):
        with self.assertRaises(ValueError):
            I2cDeviceProfile(
                name="Invalid", device_address=0x50, register_width=1,
                registers=(RegisterDefinition(name="Data", address=0x1234),),
            )

    def test_invalid_value_width_is_rejected(self):
        with self.assertRaises(ValueError):
            RegisterDefinition(
                name="Invalid", address=0, length=1, bit_width=12,
            )

    def test_unknown_schema_version_is_rejected(self):
        with self.assertRaises(ValueError):
            I2cDeviceProfile.from_dict({
                "schema": "serial-monitor.i2c-register-map",
                "version": 99,
                "name": "Future",
                "device_address": "0x50",
            })

    def test_false_string_does_not_become_true(self):
        register = RegisterDefinition.from_dict({
            "name": "Status", "register": "0x01", "signed": "false",
        })
        self.assertFalse(register.signed)


if __name__ == "__main__":
    unittest.main()
