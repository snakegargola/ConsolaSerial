"""Versioned hardware-neutral maps for devices with several SPI registers."""

from dataclasses import asdict, dataclass, field
import json


SCHEMA = "consola-serial.spi-register-map"
VERSION = 1


@dataclass(frozen=True)
class SpiRegisterDefinition:
    name: str
    address: int
    length: int = 1
    access: str = "R"
    byteorder: str = "big"
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""

    def __post_init__(self):
        if not self.name.strip(): raise ValueError("Register name cannot be empty.")
        if not 0 <= int(self.address) <= 0xFFFFFFFF: raise ValueError("Register address is invalid.")
        if not 1 <= int(self.length) <= 256: raise ValueError("Register length must be 1–256 bytes.")
        if self.access not in ("R", "W", "RW"): raise ValueError("Access must be R, W, or RW.")
        if self.byteorder not in ("big", "little"): raise ValueError("Byte order must be big or little.")


@dataclass(frozen=True)
class SpiRegisterMap:
    name: str
    read_flags: int = 0x80
    write_flags: int = 0x00
    address_bytes: int = 1
    dummy_bytes: int = 0
    registers: tuple[SpiRegisterDefinition, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not self.name.strip(): raise ValueError("Map name cannot be empty.")
        if not 1 <= int(self.address_bytes) <= 4: raise ValueError("Address width must be 1–4 bytes.")
        if not 0 <= int(self.dummy_bytes) <= 16: raise ValueError("Dummy count must be 0–16.")
        for value in (self.read_flags, self.write_flags):
            if not 0 <= int(value) <= 0xFF: raise ValueError("Flags must be one byte.")
        limit = 1 << (8 * self.address_bytes)
        if any(item.address >= limit for item in self.registers):
            raise ValueError("A register address does not fit the configured width.")
        object.__setattr__(self, "registers", tuple(self.registers))

    def command(self, register, *, write=False):
        output = bytearray(int(register.address).to_bytes(self.address_bytes, "big"))
        output[0] |= self.write_flags if write else self.read_flags
        return bytes(output)

    def to_json(self):
        return json.dumps({"schema": SCHEMA, "version": VERSION, "name": self.name,
            "read_flags": self.read_flags, "write_flags": self.write_flags,
            "address_bytes": self.address_bytes, "dummy_bytes": self.dummy_bytes,
            "registers": [asdict(item) for item in self.registers]}, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text):
        value = json.loads(text)
        if value.get("schema") != SCHEMA: raise ValueError("Not an SPI register map.")
        if int(value.get("version", 0)) != VERSION: raise ValueError("Unsupported map version.")
        return cls(value["name"], int(value.get("read_flags", 0x80)),
                   int(value.get("write_flags", 0)), int(value.get("address_bytes", 1)),
                   int(value.get("dummy_bytes", 0)),
                   tuple(SpiRegisterDefinition(**item) for item in value.get("registers", [])))


def example_spi_register_map():
    return SpiRegisterMap("Generic accelerometer example", registers=(
        SpiRegisterDefinition("WHO_AM_I", 0x0F),
        SpiRegisterDefinition("STATUS", 0x27),
        SpiRegisterDefinition("OUT_X", 0x28, 2, "R", "little", True, 1.0, 0.0, "LSB"),
        SpiRegisterDefinition("OUT_Y", 0x2A, 2, "R", "little", True, 1.0, 0.0, "LSB"),
        SpiRegisterDefinition("OUT_Z", 0x2C, 2, "R", "little", True, 1.0, 0.0, "LSB"),
    ))
