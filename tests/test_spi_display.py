import tempfile
import unittest

from app.spi_display import (
    SpiDisplayProfile, builtin_display_profiles, color_bars_rgb565,
    format_init_script, parse_init_script, solid_rgb565,
)
from app.spi_display_worker import SpiDisplayPort


class FakeSpi:
    def __init__(self): self.writes = []
    def write(self, payload, **kwargs): self.writes.append(bytes(payload))


class FakeGpio:
    def __init__(self): self.directions = []; self.writes = []
    def set_direction(self, pins, direction): self.directions.append((pins, direction))
    def write(self, value): self.writes.append(value)


class SpiDisplayTests(unittest.TestCase):
    def test_builtin_profiles_round_trip(self):
        for profile in builtin_display_profiles():
            self.assertEqual(SpiDisplayProfile.from_json(profile.to_json()), profile)

    def test_init_script_round_trip_and_line_error(self):
        steps = parse_init_script("01 ; ; 150\n3A ; 55 ; 10 # pixel format")
        self.assertEqual(parse_init_script(format_init_script(steps)), steps)
        with self.assertRaisesRegex(ValueError, "line 1"):
            parse_init_script("GG ; ; 0")

    def test_rgb565_generators_have_exact_frame_size(self):
        self.assertEqual(len(solid_rgb565(4, 3, 0x1234)), 24)
        self.assertEqual(len(color_bars_rgb565(8, 2)), 32)

    def test_display_port_toggles_dc_and_writes_address_window(self):
        profile = builtin_display_profiles()[1]
        profile = SpiDisplayProfile(
            profile.name, profile.controller, 2, 1, "rgb565", (), 1, 2
        )
        spi, gpio = FakeSpi(), FakeGpio()
        display = SpiDisplayPort(spi, gpio, dc_pin=4, reset_pin=5)
        display.framebuffer(profile, b"\xF8\x00\x00\x1F", chunk_size=2)
        self.assertEqual(spi.writes[0], b"\x2A")
        self.assertEqual(spi.writes[1], b"\x00\x01\x00\x02")
        self.assertEqual(spi.writes[2], b"\x2B")
        self.assertEqual(spi.writes[3], b"\x00\x02\x00\x02")
        self.assertEqual(spi.writes[4], b"\x2C")
        self.assertEqual(spi.writes[5:], [b"\xF8\x00", b"\x00\x1F"])


if __name__ == "__main__":
    unittest.main()
