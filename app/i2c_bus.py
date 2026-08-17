"""Hardware-neutral I2C settings, validation, SMBus PEC, and error helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class I2cBusSettings:
    """Options shared by every operation performed on one I2C interface."""

    frequency: int = 100_000
    clock_stretching: bool = False
    retry_count: int = 3

    def __post_init__(self):
        if not 1_000 <= int(self.frequency) <= 3_400_000:
            raise ValueError("I2C frequency must be from 1 kHz to 3.4 MHz.")
        # PyFtdi accepts an explicit retry count from 1 through 16.
        if not 1 <= int(self.retry_count) <= 16:
            raise ValueError("I2C retry count must be from 1 to 16.")


def coerce_bus_settings(value):
    """Accept the legacy integer frequency or a complete settings object."""
    if isinstance(value, I2cBusSettings):
        return value
    return I2cBusSettings(frequency=int(value))


def configure_i2c_controller(controller, url, settings):
    """Configure a PyFtdi controller consistently for every worker."""
    settings = coerce_bus_settings(settings)
    controller.set_retry_count(settings.retry_count)
    controller.configure(
        url,
        frequency=settings.frequency,
        clockstretching=settings.clock_stretching,
    )
    return float(controller.frequency)


def validate_7bit_address(address, *, allow_reserved=False):
    """Validate the address range supported by PyFtdi's I2C controller."""
    address = int(address)
    low = 0x00 if allow_reserved else 0x03
    high = 0x7F if allow_reserved else 0x77
    if not low <= address <= high:
        if allow_reserved:
            raise ValueError("The I2C address must be a 7-bit value (0x00–0x7F).")
        raise ValueError("The I2C address must be from 0x03 to 0x77.")
    return address


def parse_hex_bytes(text, *, allow_empty=True):
    """Parse friendly HEX input with spaces, commas, dashes, or ``0x`` prefixes."""
    normalized = str(text).strip().replace(",", " ").replace("-", " ")
    normalized = normalized.replace("0X", "").replace("0x", "")
    tokens = normalized.split()
    if not tokens:
        if allow_empty:
            return b""
        raise ValueError("Enter at least one hexadecimal byte.")
    output = bytearray()
    for index, token in enumerate(tokens, start=1):
        if not 1 <= len(token) <= 2:
            raise ValueError(f"HEX byte {index} must contain one or two digits.")
        try:
            value = int(token, 16)
        except ValueError as exc:
            raise ValueError(f"Invalid HEX byte at position {index}: {token}") from exc
        if not 0 <= value <= 0xFF:
            raise ValueError(f"HEX byte {index} is outside 00–FF.")
        output.append(value)
    return bytes(output)


def smbus_pec(data):
    """Calculate SMBus Packet Error Code (CRC-8 polynomial 0x07)."""
    crc = 0
    for byte in bytes(data):
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def append_write_pec(address, payload):
    """Append PEC for an SMBus write transaction."""
    validate_7bit_address(address, allow_reserved=True)
    data = bytes(payload)
    return data + bytes((smbus_pec(bytes((address << 1,)) + data),))


def verify_read_pec(address, command, payload_with_pec):
    """Verify and strip PEC from an SMBus command/read transaction."""
    validate_7bit_address(address, allow_reserved=True)
    return verify_combined_pec(address, bytes((command,)), payload_with_pec)


def verify_combined_pec(address, write_payload, payload_with_pec):
    """Verify PEC for an SMBus write-command followed by a read response."""
    data = bytes(payload_with_pec)
    if len(data) < 2:
        raise ValueError("SMBus PEC response is too short.")
    payload, received = data[:-1], data[-1]
    frame = (
        bytes((address << 1,)) + bytes(write_payload) +
        bytes(((address << 1) | 1,)) + payload
    )
    expected = smbus_pec(frame)
    if received != expected:
        raise ValueError(
            f"SMBus PEC mismatch: received 0x{received:02X}, "
            f"expected 0x{expected:02X}."
        )
    return payload


def verify_receive_pec(address, payload_with_pec):
    """Verify PEC for an SMBus receive-byte transaction."""
    data = bytes(payload_with_pec)
    if len(data) < 2:
        raise ValueError("SMBus PEC response is too short.")
    payload, received = data[:-1], data[-1]
    expected = smbus_pec(bytes(((address << 1) | 1,)) + payload)
    if received != expected:
        raise ValueError(
            f"SMBus PEC mismatch: received 0x{received:02X}, "
            f"expected 0x{expected:02X}."
        )
    return payload


def classify_i2c_error(exc):
    """Return a stable status without importing PyFtdi exception classes."""
    name = type(exc).__name__.lower()
    message = str(exc).strip() or type(exc).__name__
    if "nack" in name or "nack" in message.lower():
        kind = "NACK"
    elif "timeout" in name or "timeout" in message.lower():
        kind = "TIMEOUT"
    elif "usb" in name or "usb" in message.lower() or "backend" in message.lower():
        kind = "USB"
    elif isinstance(exc, ValueError):
        kind = "INVALID"
    else:
        kind = "ERROR"
    return {"status": kind, "error": message}
