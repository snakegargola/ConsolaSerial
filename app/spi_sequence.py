"""Hardware-neutral SPI command sequences and reusable device profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

from .spi_bus import SpiTransaction, format_spi_hex, parse_spi_hex


SPI_PROFILE_SCHEMA = "consola-serial.spi-profile"
SPI_PROFILE_VERSION = 1
STEP_OPERATIONS = frozenset({"write", "read", "write_read", "duplex", "delay"})
VALIDATIONS = frozenset({"none", "equals", "masked_equals", "not_all_00_ff"})


@dataclass(frozen=True)
class SpiSequenceStep:
    """One portable command, delay, and optional response assertion."""

    name: str
    operation: str
    tx: bytes = b""
    read_length: int = 0
    dummy_byte: int = 0x00
    delay_ms: int = 0
    validation: str = "none"
    expected: bytes = b""
    mask: bytes = b""

    def __post_init__(self):
        operation = str(self.operation).lower()
        validation = str(self.validation).lower()
        delay_ms = int(self.delay_ms)
        if operation not in STEP_OPERATIONS:
            raise ValueError(f"Unsupported SPI sequence operation: {operation}")
        if validation not in VALIDATIONS:
            raise ValueError(f"Unsupported SPI validation: {validation}")
        if not 0 <= delay_ms <= 3_600_000:
            raise ValueError("SPI step delay must be from 0 to 3600000 ms.")
        if operation == "delay":
            if delay_ms <= 0:
                raise ValueError("A Delay step requires a positive delay.")
            if self.tx or self.read_length:
                raise ValueError("A Delay step cannot transfer bytes.")
        else:
            SpiTransaction(operation, self.tx, self.read_length, self.dummy_byte)
        expected = bytes(self.expected)
        mask = bytes(self.mask)
        if validation in ("equals", "masked_equals") and not expected:
            raise ValueError("This validation requires expected RX bytes.")
        if validation == "masked_equals":
            if len(mask) != len(expected):
                raise ValueError("Validation mask and expected RX must have equal length.")
        elif mask:
            raise ValueError("A mask is only valid with Masked equals.")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "validation", validation)
        object.__setattr__(self, "delay_ms", delay_ms)
        object.__setattr__(self, "tx", bytes(self.tx))
        object.__setattr__(self, "expected", expected)
        object.__setattr__(self, "mask", mask)

    def transaction(self):
        if self.operation == "delay":
            return None
        return SpiTransaction(
            self.operation, self.tx, self.read_length, self.dummy_byte
        )

    def validate_rx(self, received):
        received = bytes(received)
        if self.validation == "none":
            return True, ""
        if self.validation == "equals":
            passed = received == self.expected
        elif self.validation == "masked_equals":
            passed = len(received) == len(self.expected) and all(
                (actual & mask) == (expected & mask)
                for actual, expected, mask in zip(received, self.expected, self.mask)
            )
        else:
            passed = bool(received) and not (
                all(value == 0x00 for value in received)
                or all(value == 0xFF for value in received)
            )
        if passed:
            return True, ""
        return False, (
            f"RX validation failed: received {format_spi_hex(received) or '(empty)'}, "
            f"expected {format_spi_hex(self.expected) or self.validation}"
        )

    def to_dict(self):
        return {
            "name": self.name, "operation": self.operation,
            "tx": format_spi_hex(self.tx), "read_length": self.read_length,
            "dummy_byte": f"{self.dummy_byte:02X}", "delay_ms": self.delay_ms,
            "validation": self.validation,
            "expected": format_spi_hex(self.expected), "mask": format_spi_hex(self.mask),
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            name=str(value.get("name", "Step")),
            operation=value.get("operation", "write"),
            tx=parse_spi_hex(value.get("tx", "")),
            read_length=int(value.get("read_length", 0)),
            dummy_byte=parse_spi_hex(
                value.get("dummy_byte", "00"), allow_empty=False
            )[0],
            delay_ms=int(value.get("delay_ms", 0)),
            validation=value.get("validation", "none"),
            expected=parse_spi_hex(value.get("expected", "")),
            mask=parse_spi_hex(value.get("mask", "")),
        )


@dataclass(frozen=True)
class SpiDeviceProfile:
    name: str
    category: str = "Generic"
    notes: str = ""
    steps: tuple[SpiSequenceStep, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not str(self.name).strip():
            raise ValueError("SPI profile name cannot be empty.")
        object.__setattr__(self, "steps", tuple(self.steps))

    def to_dict(self):
        return {
            "schema": SPI_PROFILE_SCHEMA, "version": SPI_PROFILE_VERSION,
            "name": self.name, "category": self.category, "notes": self.notes,
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, value):
        if value.get("schema") != SPI_PROFILE_SCHEMA:
            raise ValueError("Not a Consola Serial SPI profile.")
        if int(value.get("version", 0)) != SPI_PROFILE_VERSION:
            raise ValueError("Unsupported SPI profile version.")
        return cls(
            name=value.get("name", ""), category=value.get("category", "Generic"),
            notes=value.get("notes", ""),
            steps=tuple(SpiSequenceStep.from_dict(item) for item in value.get("steps", [])),
        )

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))


def builtin_spi_profiles():
    """Safe, editable starting points; writes/erase are intentionally omitted."""
    return (
        SpiDeviceProfile("SPI NOR quick identification", "Memory", (
            "Read-only JEDEC/status/SFDP checks. Confirm every command with the "
            "exact flash datasheet before adding program or erase steps."
        ), (
            SpiSequenceStep("JEDEC ID", "write_read", b"\x9f", 3, 0xFF,
                            validation="not_all_00_ff"),
            SpiSequenceStep("Status register 1", "write_read", b"\x05", 1, 0xFF),
            SpiSequenceStep("SFDP signature", "write_read", b"\x5a\x00\x00\x00\x00",
                            4, 0xFF, validation="equals", expected=b"SFDP"),
        )),
        SpiDeviceProfile("25xx EEPROM read sample", "Memory", (
            "Read-only 16-bit-address example. Adjust opcode/address width to the datasheet."
        ), (
            SpiSequenceStep("Read address 0", "write_read", b"\x03\x00\x00", 16, 0xFF),
        )),
        SpiDeviceProfile("Display command validation template", "Display", (
            "Template for validating command bytes. Display transfers also need D/C and "
            "RESET GPIO control; those steps are deliberately not executed yet."
        ), (
            SpiSequenceStep("Software reset command", "write", b"\x01"),
            SpiSequenceStep("Reset wait", "delay", delay_ms=150),
            SpiSequenceStep("Sleep out command", "write", b"\x11"),
            SpiSequenceStep("Sleep-out wait", "delay", delay_ms=120),
        )),
    )
