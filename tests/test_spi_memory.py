import unittest

from app.spi_memory import (
    SpiMemoryGeometry, format_hex_dump, iter_page_programs,
    parse_jedec_id, parse_sfdp, parse_sfdp_header, validate_memory_range,
)


class SpiMemoryTests(unittest.TestCase):
    def test_unaligned_program_never_crosses_pages(self):
        geometry = SpiMemoryGeometry(page_size=16)
        chunks = list(iter_page_programs(geometry, 14, bytes(range(35))))
        self.assertEqual([(address, len(data)) for address, data in chunks],
                         [(14, 2), (16, 16), (32, 16), (48, 1)])

    def test_range_and_address_width_are_validated(self):
        geometry = SpiMemoryGeometry(capacity=256, address_bytes=1, sector_size=16)
        self.assertEqual(geometry.address(255), b"\xff")
        with self.assertRaises(ValueError): geometry.address(256)
        with self.assertRaises(ValueError): validate_memory_range(geometry, 250, 7)

    def test_jedec_and_sfdp_headers_are_decoded(self):
        jedec = parse_jedec_id(b"\xef\x40\x18")
        self.assertEqual(jedec["manufacturer"], "Winbond")
        self.assertEqual(jedec["capacity"], 1 << 24)
        sfdp = parse_sfdp_header(b"SFDP\x06\x01\x02\xff")
        self.assertEqual(sfdp["parameter_headers"], 3)
        with self.assertRaises(ValueError): parse_sfdp_header(b"NOPE1234")

    def test_basic_sfdp_density_and_page_size(self):
        payload = bytearray(80)
        payload[:8] = b"SFDP\x06\x01\x00\xff"
        payload[8:16] = bytes((0x00, 0x06, 0x01, 11, 16, 0, 0, 0xFF))
        payload[20:24] = (8 * 1024 * 1024 - 1).to_bytes(4, "little")
        payload[56:60] = (8 << 4).to_bytes(4, "little")
        decoded = parse_sfdp(payload)
        self.assertEqual(decoded["capacity"], 1024 * 1024)
        self.assertEqual(decoded["page_size"], 256)

    def test_hex_dump_has_address_and_ascii(self):
        output = format_hex_dump(b"ABC\x00", 0x20)
        self.assertIn("00000020", output)
        self.assertIn("|ABC.|", output)


if __name__ == "__main__": unittest.main()
