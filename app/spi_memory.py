"""Pure helpers for common SPI NOR, 25xx EEPROM, and FRAM devices."""

from __future__ import annotations

from dataclasses import dataclass


MEMORY_KINDS = ("SPI NOR", "25xx EEPROM", "SPI FRAM")


@dataclass(frozen=True)
class SpiMemoryGeometry:
    kind: str = "SPI NOR"
    capacity: int = 1 << 20
    address_bytes: int = 3
    page_size: int = 256
    sector_size: int = 4096
    read_command: int = 0x03
    program_command: int = 0x02
    write_enable_command: int = 0x06
    status_command: int = 0x05
    erase_command: int = 0x20
    busy_mask: int = 0x01
    protection_mask: int = 0x3C
    write_delay_ms: int = 5

    def __post_init__(self):
        if self.kind not in MEMORY_KINDS:
            raise ValueError("Unsupported SPI memory kind.")
        if not 1 <= int(self.capacity) <= (1 << 32):
            raise ValueError("Capacity must be from 1 byte to 4 GiB.")
        if not 1 <= int(self.address_bytes) <= 4:
            raise ValueError("Address width must be from 1 to 4 bytes.")
        if not 1 <= int(self.page_size) <= 65536:
            raise ValueError("Page size must be from 1 to 65536 bytes.")
        if not 1 <= int(self.sector_size) <= int(self.capacity):
            raise ValueError("Sector size must fit in the memory capacity.")
        for name in ("read_command", "program_command", "write_enable_command",
                     "status_command", "erase_command", "busy_mask", "protection_mask"):
            if not 0 <= int(getattr(self, name)) <= 0xFF:
                raise ValueError(f"{name} must be one byte.")

    def address(self, value):
        value = int(value)
        if not 0 <= value < self.capacity:
            raise ValueError("Memory address is outside the configured capacity.")
        if value >= 1 << (8 * self.address_bytes):
            raise ValueError("Address does not fit the configured address width.")
        return value.to_bytes(self.address_bytes, "big")


def validate_memory_range(geometry, address, length):
    address, length = int(address), int(length)
    if length < 0 or address < 0 or address + length > geometry.capacity:
        raise ValueError("Memory range is outside the configured capacity.")
    return address, length


def iter_page_programs(geometry, address, payload):
    """Split writes without ever crossing a physical page boundary."""
    payload = bytes(payload)
    validate_memory_range(geometry, address, len(payload))
    offset = 0
    while offset < len(payload):
        current = address + offset
        available = geometry.page_size - (current % geometry.page_size)
        chunk = payload[offset:offset + available]
        yield current, chunk
        offset += len(chunk)


def parse_jedec_id(payload):
    payload = bytes(payload)
    if len(payload) < 3:
        raise ValueError("JEDEC ID requires at least three bytes.")
    manufacturers = {0x01: "Cypress/Spansion", 0x20: "Micron/ST",
                     0x1F: "Adesto/Atmel", 0xBF: "Microchip/SST",
                     0xC2: "Macronix", 0xEF: "Winbond"}
    capacity_code = payload[2]
    capacity = (1 << capacity_code) if 8 <= capacity_code <= 32 else None
    return {"manufacturer_id": payload[0],
            "manufacturer": manufacturers.get(payload[0], "Unknown"),
            "memory_type": payload[1], "capacity_code": capacity_code,
            "capacity": capacity}


def parse_sfdp_header(payload):
    payload = bytes(payload)
    if len(payload) < 8 or payload[:4] != b"SFDP":
        raise ValueError("Invalid or missing SFDP signature.")
    return {"minor": payload[4], "major": payload[5],
            "parameter_headers": payload[6] + 1,
            "access_protocol": payload[7]}


def parse_sfdp(payload):
    """Decode the SFDP header and useful fields from the JEDEC basic table."""
    payload = bytes(payload)
    result = parse_sfdp_header(payload)
    headers = []
    for index in range(result["parameter_headers"]):
        offset = 8 + index * 8
        if offset + 8 > len(payload): break
        item = payload[offset:offset + 8]
        parameter_id = item[0] | (item[7] << 8)
        pointer = int.from_bytes(item[4:7], "little")
        header = {"id": parameter_id, "minor": item[1], "major": item[2],
                  "dwords": item[3], "pointer": pointer}
        headers.append(header)
        if parameter_id in (0xFF00, 0x0000) and pointer + 8 <= len(payload):
            table = payload[pointer:pointer + item[3] * 4]
            first_word = int.from_bytes(table[:4], "little")
            address_code = (first_word >> 17) & 0x03
            result["address_bytes"] = {0: (3,), 1: (3, 4), 2: (4,)}.get(address_code, ())
            density_word = int.from_bytes(table[4:8], "little")
            if density_word & 0x80000000:
                exponent = density_word & 0x7FFFFFFF
                capacity_bits = 1 << exponent if exponent < 63 else None
            else:
                capacity_bits = (density_word & 0x7FFFFFFF) + 1
            if capacity_bits:
                result["capacity"] = (capacity_bits + 7) // 8
            if len(table) >= 44:
                page_exponent = (int.from_bytes(table[40:44], "little") >> 4) & 0x0F
                if page_exponent:
                    result["page_size"] = 1 << page_exponent
            erase_types = []
            if len(table) >= 36:
                for dword_offset in (28, 32):
                    word = int.from_bytes(table[dword_offset:dword_offset + 4], "little")
                    for shift in (0, 16):
                        exponent = (word >> shift) & 0xFF
                        opcode = (word >> (shift + 8)) & 0xFF
                        if opcode and exponent and exponent < 32:
                            erase_types.append({"opcode": opcode, "size": 1 << exponent})
            result["erase_types"] = erase_types
    result["parameters"] = headers
    return result


def decode_status_register(value, *, busy_mask=0x01, protection_mask=0x3C):
    value = int(value)
    if not 0 <= value <= 0xFF: raise ValueError("Status register must be one byte.")
    return {"raw": value, "busy": bool(value & int(busy_mask)),
            "write_enabled": bool(value & 0x02),
            "protected": bool(value & int(protection_mask)),
            "protection_bits": value & int(protection_mask)}


def format_hex_dump(payload, base_address=0, width=16):
    lines = []
    payload = bytes(payload)
    for offset in range(0, len(payload), width):
        chunk = payload[offset:offset + width]
        hex_part = " ".join(f"{value:02X}" for value in chunk)
        ascii_part = "".join(chr(value) if 32 <= value < 127 else "." for value in chunk)
        lines.append(f"{base_address + offset:08X}  {hex_part:<{width * 3 - 1}}  |{ascii_part}|")
    return "\n".join(lines)
