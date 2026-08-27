"""Versioned, Qt-independent profiles for SPI register framing and decoding."""

from dataclasses import asdict, dataclass
import json


SCHEMA = "consola-serial.spi-register-profile"
VERSION = 1


@dataclass(frozen=True)
class SpiRegisterProfile:
    name: str
    read_flags: str = "80"
    write_flags: str = "00"
    register_bytes: int = 1
    data_bytes: int = 1
    dummy_bytes: int = 0
    byteorder: str = "big"
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""

    def __post_init__(self):
        if not self.name.strip(): raise ValueError("Profile name cannot be empty.")
        if not 1 <= int(self.register_bytes) <= 4: raise ValueError("Register width must be 1–4 bytes.")
        if not 1 <= int(self.data_bytes) <= 256: raise ValueError("Data width must be 1–256 bytes.")
        if not 0 <= int(self.dummy_bytes) <= 16: raise ValueError("Dummy count must be 0–16.")
        if self.byteorder not in ("big", "little"): raise ValueError("Byte order must be big or little.")

    def to_json(self):
        return json.dumps({"schema": SCHEMA, "version": VERSION, **asdict(self)},
                          indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text):
        value = json.loads(text)
        if value.pop("schema", None) != SCHEMA: raise ValueError("Not an SPI register profile.")
        if int(value.pop("version", 0)) != VERSION: raise ValueError("Unsupported profile version.")
        return cls(**value)
