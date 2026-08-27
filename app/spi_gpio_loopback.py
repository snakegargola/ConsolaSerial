"""Physical SPI wiring loopback using explicit MPSSE GPIO pin sampling."""


def exchange_gpio_loopback(gpio, payload, mode=0):
    """Clock MOSI on DBUS1 and sample the physical DBUS2 input, MSB first."""
    payload = bytes(payload)
    cpol = 1 if int(mode) in (2, 3) else 0
    idle_clock = 0x01 if cpol else 0x00
    active_clock = 0x00 if cpol else 0x01
    received = bytearray()
    gpio.write(idle_clock)
    for output in payload:
        incoming = 0
        for shift in range(7, -1, -1):
            mosi = 0x02 if output & (1 << shift) else 0x00
            gpio.write(mosi | idle_clock)
            gpio.write(mosi | active_clock)
            raw = gpio.read()
            pins = raw[0] if isinstance(raw, (bytes, bytearray)) else int(raw)
            incoming = (incoming << 1) | (1 if pins & 0x04 else 0)
            gpio.write(mosi | idle_clock)
        received.append(incoming)
    gpio.write(idle_clock)
    return bytes(received)
