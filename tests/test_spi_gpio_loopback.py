import unittest

from app.spi_gpio_loopback import exchange_gpio_loopback


class FakeGpio:
    def __init__(self, connected): self.connected = connected; self.last = 0
    def write(self, value): self.last = value
    def read(self):
        miso = 0x04 if (self.connected and self.last & 0x02) else 0
        return bytearray((self.last | miso,))


class SpiGpioLoopbackTests(unittest.TestCase):
    def test_connected_input_reconstructs_transmitted_bytes(self):
        payload = b"Hola\x00\xff"
        self.assertEqual(exchange_gpio_loopback(FakeGpio(True), payload), payload)

    def test_disconnected_input_does_not_echo(self):
        payload = b"Hola"
        self.assertNotEqual(exchange_gpio_loopback(FakeGpio(False), payload), payload)


if __name__ == "__main__": unittest.main()
