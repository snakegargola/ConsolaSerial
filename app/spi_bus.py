"""Hardware-neutral SPI settings, transactions, formatting, and execution."""

from __future__ import annotations

from dataclasses import dataclass


SPI_OPERATIONS = frozenset({
    "write", "read", "write_read", "loopback", "jedec",
})
SPI_MAX_PAYLOAD = 0xFF00  # PyFtdi's per-exchange payload limit.


@dataclass(frozen=True)
class SpiBusSettings:
    """Configuration shared by one PyFtdi SPI transaction."""

    frequency: int = 1_000_000
    mode: int = 0
    cs_count: int = 1
    chip_select: int = 0
    turbo: bool = False

    def __post_init__(self):
        frequency = int(self.frequency)
        mode = int(self.mode)
        cs_count = int(self.cs_count)
        chip_select = int(self.chip_select)
        if not 1_000 <= frequency <= 30_000_000:
            raise ValueError("SPI frequency must be from 1 kHz to 30 MHz.")
        if not 0 <= mode <= 3:
            raise ValueError("SPI mode must be 0, 1, 2, or 3.")
        if not 1 <= cs_count <= 5:
            raise ValueError("SPI CS count must be from 1 to 5.")
        if not 0 <= chip_select < cs_count:
            raise ValueError("Selected SPI CS must be lower than the CS count.")
        object.__setattr__(self, "frequency", frequency)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "cs_count", cs_count)
        object.__setattr__(self, "chip_select", chip_select)
        object.__setattr__(self, "turbo", bool(self.turbo))


@dataclass(frozen=True)
class SpiTransaction:
    """One validated SPI operation and its exact MOSI clock bytes."""

    operation: str
    tx: bytes = b""
    read_length: int = 0
    dummy_byte: int = 0x00

    def __post_init__(self):
        operation = str(self.operation).lower()
        tx = bytes(self.tx)
        read_length = int(self.read_length)
        dummy_byte = int(self.dummy_byte)
        if operation not in SPI_OPERATIONS:
            raise ValueError(f"Unsupported SPI operation: {self.operation}")
        if not 0 <= read_length <= SPI_MAX_PAYLOAD:
            raise ValueError("SPI read length must be from 0 to 65280 bytes.")
        if not 0 <= dummy_byte <= 0xFF:
            raise ValueError("SPI dummy byte must be from 0x00 to 0xFF.")
        if len(tx) > SPI_MAX_PAYLOAD:
            raise ValueError("SPI TX payload cannot exceed 65280 bytes.")
        if operation == "write" and not tx:
            raise ValueError("SPI Write requires at least one TX byte.")
        if operation == "read" and not read_length:
            raise ValueError("SPI Read requires at least one RX byte.")
        if operation == "write_read" and (not tx or not read_length):
            raise ValueError("SPI Write then Read requires TX and RX bytes.")
        if operation == "loopback" and not tx:
            raise ValueError("SPI Loopback requires a test pattern.")
        if operation == "jedec" and (not tx or not read_length):
            raise ValueError("SPI JEDEC identification requires TX and RX bytes.")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "tx", tx)
        object.__setattr__(self, "read_length", read_length)
        object.__setattr__(self, "dummy_byte", dummy_byte)

    @property
    def wire_tx(self) -> bytes:
        """Return every MOSI byte clocked by this operation."""
        tx = bytes(self.tx)
        dummy = bytes((int(self.dummy_byte),))
        if self.operation == "write":
            return tx
        if self.operation == "read":
            return dummy * int(self.read_length)
        if self.operation in ("write_read", "jedec"):
            return tx + dummy * int(self.read_length)
        if self.operation == "loopback":
            count = max(len(tx), int(self.read_length) or len(tx))
            return tx + dummy * (count - len(tx))
        raise ValueError(f"Unsupported SPI operation: {self.operation}")

    @property
    def expected_rx_length(self) -> int:
        if self.operation == "loopback":
            return len(self.tx)
        return int(self.read_length)


def parse_spi_hex(text, *, allow_empty=True) -> bytes:
    """Parse friendly HEX bytes, including compact and 0x-prefixed input."""
    normalized = str(text).strip().replace(",", " ").replace("-", " ")
    if not normalized:
        if allow_empty:
            return b""
        raise ValueError("Enter at least one hexadecimal byte.")
    tokens = normalized.split()
    if len(tokens) == 1 and not tokens[0].lower().startswith("0x"):
        compact = tokens[0]
        if len(compact) > 2:
            if len(compact) % 2:
                raise ValueError("Compact HEX input must contain complete bytes.")
            tokens = [compact[index:index + 2] for index in range(0, len(compact), 2)]

    output = bytearray()
    for index, token in enumerate(tokens, start=1):
        if token.lower().startswith("0x"):
            token = token[2:]
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


def format_spi_hex(payload) -> str:
    return bytes(payload).hex(" ").upper()


def execute_spi_transaction(port, transaction: SpiTransaction) -> bytes:
    """Execute a validated transaction against a PyFtdi-compatible port."""
    operation = transaction.operation
    tx = bytes(transaction.tx)
    read_length = transaction.expected_rx_length
    dummy = bytes((transaction.dummy_byte,))

    if operation == "write":
        port.write(tx, start=True, stop=True)
        return b""
    if operation == "read":
        return bytes(port.exchange(
            b"", read_length, start=True, stop=True, duplex=False
        ))
    if operation in ("write_read", "jedec"):
        return bytes(port.exchange(
            tx, read_length, start=True, stop=True, duplex=False
        ))
    if operation == "loopback":
        raise ValueError(
            "Physical loopback must use the GPIO sampling worker; the generic "
            "full-duplex command can echo TX instead of sampling MISO."
        )
    raise ValueError(f"Unsupported SPI operation: {operation}")


def classify_spi_error(exc):
    """Return a stable error category without importing PyFtdi exceptions."""
    message = str(exc).strip() or type(exc).__name__
    lowered = message.lower()
    if "mode" in lowered or "cpha" in lowered:
        status = "MODE"
    elif isinstance(exc, PermissionError) or "protect" in lowered:
        status = "PROTECTED"
    elif "timeout" in lowered:
        status = "TIMEOUT"
    elif "usb" in lowered or "backend" in lowered or "ftdi" in lowered:
        status = "USB"
    elif isinstance(exc, ValueError):
        status = "INVALID"
    else:
        status = "ERROR"
    return {"status": status, "error": message}
