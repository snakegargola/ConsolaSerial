import unittest

from app.gpio_bus import GpioState, gpio_width_for_interface, spi_gpio_mask
from app.usb_bridge import make_bridge


class GpioBusTests(unittest.TestCase):
    def test_spi_gpio_excludes_bus_and_configured_chip_selects(self):
        self.assertEqual(spi_gpio_mask(1, 8), 0xF0)
        self.assertEqual(spi_gpio_mask(2, 8), 0xE0)
        self.assertEqual(spi_gpio_mask(5, 8), 0x00)

    def test_state_rejects_reserved_or_input_output_bits(self):
        with self.assertRaises(ValueError):
            GpioState(0xF0, direction=0x08)
        with self.assertRaises(ValueError):
            GpioState(0xF0, direction=0x10, output=0x20)

    def test_gpio_width_matches_supported_ftdi_family(self):
        ft4232 = make_bridge(vid=0x0403, pid=0x6011)
        ft232h = make_bridge(vid=0x0403, pid=0x6014)
        self.assertEqual(gpio_width_for_interface(ft4232, ft4232.interfaces[0]), 8)
        self.assertEqual(gpio_width_for_interface(ft232h, ft232h.interfaces[0]), 16)


if __name__ == "__main__":
    unittest.main()
