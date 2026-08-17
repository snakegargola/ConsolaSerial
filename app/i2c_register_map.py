"""Validated, JSON-serializable models for I2C register-map profiles."""

from dataclasses import dataclass, field
from math import isfinite

from .i2c_formula import extract_bit_field, parse_enum_map


def parse_int(value, field_name):
    """Parse an integer stored as a JSON number or a ``0x``/decimal string."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer, not a boolean.")
    try:
        return int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be decimal or hexadecimal.") from exc


def parse_bool(value, field_name):
    """Parse strict JSON booleans while accepting readable yes/no strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise ValueError(f"{field_name} must be true or false.")


@dataclass(frozen=True)
class RegisterDefinition:
    """Describe one linear register value from a device datasheet."""

    name: str
    address: int
    length: int = 1
    access: str = "R"
    byteorder: str = "big"
    signed: bool = False
    bit_width: int = 8
    right_shift: int = 0
    mask: int | None = None
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    formula: str = "x"
    bit_field: str = ""
    enum_map: str = ""

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Register name cannot be empty.")
        if self.address < 0:
            raise ValueError(f"Register {self.name}: address cannot be negative.")
        if not 1 <= self.length <= 8:
            raise ValueError(f"Register {self.name}: length must be from 1 to 8 bytes.")
        if self.access not in {"R", "W", "RW"}:
            raise ValueError(f"Register {self.name}: access must be R, W, or RW.")
        if self.byteorder not in {"big", "little"}:
            raise ValueError(f"Register {self.name}: byte order must be big or little.")
        storage_bits = self.length * 8
        if not 1 <= self.bit_width <= storage_bits:
            raise ValueError(
                f"Register {self.name}: value bits must be from 1 to {storage_bits}."
            )
        if not 0 <= self.right_shift < storage_bits:
            raise ValueError(
                f"Register {self.name}: right shift must be from 0 to {storage_bits - 1}."
            )
        if self.right_shift + self.bit_width > storage_bits:
            raise ValueError(
                f"Register {self.name}: value bits plus right shift exceed "
                f"the {storage_bits}-bit payload."
            )
        if self.mask is not None and self.mask < 0:
            raise ValueError(f"Register {self.name}: mask cannot be negative.")
        if self.mask is not None and self.mask >= (1 << storage_bits):
            raise ValueError(
                f"Register {self.name}: mask does not fit in {storage_bits} bits."
            )
        if not isfinite(self.scale) or not isfinite(self.offset):
            raise ValueError(f"Register {self.name}: scale and offset must be finite.")
        if len(self.formula) > 256:
            raise ValueError(f"Register {self.name}: formula is too long.")
        try:
            extract_bit_field(0, self.bit_field)
            parse_enum_map(self.enum_map)
        except ValueError as exc:
            raise ValueError(f"Register {self.name}: {exc}") from exc

    def to_dict(self):
        """Return a stable human-readable JSON representation."""
        return {
            "name": self.name,
            "register": f"0x{self.address:X}",
            "length": self.length,
            "access": self.access,
            "byte_order": self.byteorder,
            "signed": self.signed,
            "value_bits": self.bit_width,
            "right_shift": self.right_shift,
            "mask": None if self.mask is None else f"0x{self.mask:X}",
            "scale": self.scale,
            "offset": self.offset,
            "unit": self.unit,
            "formula": self.formula,
            "bit_field": self.bit_field,
            "enum": self.enum_map,
        }

    @classmethod
    def from_dict(cls, data):
        """Build and validate one register from decoded JSON data."""
        if not isinstance(data, dict):
            raise ValueError("Each register entry must be a JSON object.")
        length = parse_int(data.get("length", 1), "Register length")
        mask_value = data.get("mask")
        return cls(
            name=str(data.get("name", "")).strip(),
            address=parse_int(data.get("register", 0), "Register address"),
            length=length,
            access=str(data.get("access", "R")).strip().upper(),
            byteorder=str(data.get("byte_order", "big")).strip().lower(),
            signed=parse_bool(data.get("signed", False), "Signed"),
            bit_width=parse_int(data.get("value_bits", length * 8), "Value bits"),
            right_shift=parse_int(data.get("right_shift", 0), "Right shift"),
            mask=None if mask_value in (None, "") else parse_int(mask_value, "Mask"),
            scale=float(data.get("scale", 1.0)),
            offset=float(data.get("offset", 0.0)),
            unit=str(data.get("unit", "")),
            formula=str(data.get("formula", "x")),
            bit_field=str(data.get("bit_field", "")),
            enum_map=str(data.get("enum", "")),
        )


@dataclass(frozen=True)
class I2cDeviceProfile:
    """A device address and the register definitions used to debug it."""

    name: str
    device_address: int
    register_width: int = 1
    register_big_endian: bool = True
    registers: tuple[RegisterDefinition, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Device profile name cannot be empty.")
        if not 0x03 <= self.device_address <= 0x77:
            raise ValueError("The 7-bit device address must be from 0x03 to 0x77.")
        if self.register_width not in (1, 2):
            raise ValueError("Register address size must be 8 or 16 bits.")
        limit = 1 << (self.register_width * 8)
        for register in self.registers:
            if register.address >= limit:
                raise ValueError(
                    f"Register {register.name}: 0x{register.address:X} does not fit "
                    f"in {self.register_width * 8} bits."
                )

    def to_dict(self):
        return {
            "schema": "serial-monitor.i2c-register-map",
            "version": 2,
            "name": self.name,
            "device_address": f"0x{self.device_address:02X}",
            "register_address_bits": self.register_width * 8,
            "register_address_byte_order": (
                "big" if self.register_big_endian else "little"
            ),
            "registers": [register.to_dict() for register in self.registers],
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("The profile root must be a JSON object.")
        schema = data.get("schema", "serial-monitor.i2c-register-map")
        if schema != "serial-monitor.i2c-register-map":
            raise ValueError(f"Unsupported profile schema: {schema}")
        version = parse_int(data.get("version", 1), "Profile version")
        if version not in (1, 2):
            raise ValueError(f"Unsupported register-map profile version: {version}")
        address_bits = parse_int(
            data.get("register_address_bits", 8), "Register address bits"
        )
        if address_bits not in (8, 16):
            raise ValueError("Register address bits must be 8 or 16.")
        address_order = str(
            data.get("register_address_byte_order", "big")
        ).lower()
        if address_order not in {"big", "little"}:
            raise ValueError("Register address byte order must be big or little.")
        raw_registers = data.get("registers", [])
        if not isinstance(raw_registers, list):
            raise ValueError("Profile registers must be a JSON list.")
        return cls(
            name=str(data.get("name", "")).strip(),
            device_address=parse_int(data.get("device_address"), "Device address"),
            register_width=address_bits // 8,
            register_big_endian=address_order == "big",
            registers=tuple(
                RegisterDefinition.from_dict(register) for register in raw_registers
            ),
        )
