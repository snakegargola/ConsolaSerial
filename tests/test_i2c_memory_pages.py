"""Unit tests for safe I2C EEPROM page splitting."""

import unittest

from app.i2c_worker import iter_memory_pages


class MemoryPageTests(unittest.TestCase):
    def test_unaligned_write_never_crosses_page_boundary(self):
        payload = bytes(range(20))
        pages = list(iter_memory_pages(0x0E, payload, 16))
        self.assertEqual([address for address, _data in pages], [0x0E, 0x10, 0x20])
        self.assertEqual([len(data) for _address, data in pages], [2, 16, 2])
        self.assertEqual(b"".join(data for _address, data in pages), payload)

    def test_empty_payload_produces_no_transactions(self):
        self.assertEqual(list(iter_memory_pages(0, b"", 16)), [])

    def test_invalid_page_size_is_rejected(self):
        with self.assertRaises(ValueError):
            list(iter_memory_pages(0, b"\x01", 0))


if __name__ == "__main__":
    unittest.main()
