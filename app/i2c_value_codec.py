"""Encoding and decoding helpers for generic I2C registers and sensors."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecodedI2cValue:
    """All common representations of a register byte sequence."""

    raw_hex: str
    unsigned: int
    signed: int
    selected_integer: int
    hexadecimal: str
    octal: str
    binary: str
    ascii: str
    scaled: float


def decode_i2c_value(data, *, byteorder="big", signed=False, bit_width=None,
                     right_shift=0, mask=None, scale=1.0, offset=0.0):
    """Decode raw bytes using a datasheet-style conversion pipeline.

    The pipeline is: bytes -> integer -> right shift -> mask -> sign extension
    -> scale and offset. ``bit_width`` describes the meaningful value bits,
    which can be smaller than the transferred byte count.
    """
    payload = bytes(data)
    if not payload:
        raise ValueError("At least one byte is required.")
    storage_bits = len(payload) * 8
    bit_width = storage_bits if bit_width is None else int(bit_width)
    if not 1 <= bit_width <= storage_bits:
        raise ValueError(f"Value bits must be from 1 to {storage_bits}.")
    right_shift = int(right_shift)
    if not 0 <= right_shift < storage_bits:
        raise ValueError(f"Right shift must be from 0 to {storage_bits - 1}.")
    if bit_width + right_shift > storage_bits:
        raise ValueError("Value bits plus right shift exceed the received payload.")

    raw = int.from_bytes(payload, byteorder=byteorder, signed=False)
    shifted = raw >> right_shift
    effective_mask = (1 << bit_width) - 1 if mask is None else int(mask)
    if not 0 <= effective_mask < (1 << bit_width):
        raise ValueError(f"Mask must fit in the configured {bit_width} value bits.")
    value = shifted & effective_mask
    unsigned = value
    sign_bit = 1 << (bit_width - 1)
    signed_value = value - (1 << bit_width) if value & sign_bit else value
    selected = signed_value if signed else unsigned
    binary_width = max(bit_width, 1)
    return DecodedI2cValue(
        raw_hex=payload.hex(" ").upper(),
        unsigned=unsigned,
        signed=signed_value,
        selected_integer=selected,
        hexadecimal=f"0x{unsigned:0{max(1, (bit_width + 3) // 4)}X}",
        octal=f"0o{unsigned:o}",
        binary=f"0b{unsigned:0{binary_width}b}",
        ascii="".join(chr(value) if 32 <= value <= 126 else "." for value in payload),
        scaled=selected * float(scale) + float(offset),
    )


def encode_i2c_value(text, *, input_format="HEX bytes", length=1,
                     byteorder="big", signed=False):
    """Encode a user value into a fixed-length I2C payload."""
    text = text.strip()
    if input_format == "HEX bytes":
        payload = bytes.fromhex(text)
        if len(payload) != length:
            raise ValueError(f"Expected exactly {length} byte(s).")
        return payload
    if input_format == "ASCII":
        payload = text.encode("utf-8")
        if len(payload) != length:
            raise ValueError(f"Expected exactly {length} encoded byte(s).")
        return payload
    bases = {"Decimal": 10, "Hexadecimal": 16, "Octal": 8, "Binary": 2}
    try:
        value = int(text, bases[input_format])
        return value.to_bytes(length, byteorder=byteorder, signed=signed)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Value does not fit in {length} byte(s).") from exc
