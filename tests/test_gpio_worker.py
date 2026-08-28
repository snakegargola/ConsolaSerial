import unittest

from app.gpio_bus import GpioState
from app.gpio_worker import apply_gpio_port


class FakePort:
    def __init__(self):
        self.direction_calls = []
        self.writes = []

    def set_direction(self, pins, direction):
        self.direction_calls.append((pins, direction))

    def write(self, value):
        self.writes.append(value)

    def read(self, with_output=False):
        return 0xA0


class GpioWorkerTests(unittest.TestCase):
    def test_applies_masks_then_samples_physical_port(self):
        port = FakePort()
        result = apply_gpio_port(port, GpioState(0xF0, 0x30, 0x20))
        self.assertEqual(port.direction_calls, [(0xF0, 0x30)])
        self.assertEqual(port.writes, [0x20])
        self.assertEqual(result["sampled"], 0xA0)

    def test_read_only_does_not_rewrite_outputs(self):
        port = FakePort()
        apply_gpio_port(port, GpioState(0xFF, 0x01, 0x01), write_outputs=False)
        self.assertEqual(port.writes, [])


if __name__ == "__main__":
    unittest.main()
