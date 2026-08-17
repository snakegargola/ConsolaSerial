"""Tests for model-independent USB bridge capability detection."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.bridge_interface_manager import (
    InterfaceBusyError, UsbBridgeInterfaceManager,
)
from app.usb_bridge import (
    GPIO, I2C, JTAG, SPI, UART, discover_usb_bridges, make_bridge, product_for,
)
from app.serial_worker import bridge_interface_for_port


class UsbBridgeCatalogTests(unittest.TestCase):
    def test_ft232h_exposes_one_complete_mpsse_interface(self):
        bridge = make_bridge(vid=0x0403, pid=0x6014, serial="ONE")
        self.assertEqual(len(bridge.interfaces), 1)
        self.assertEqual(
            bridge.interfaces[0].capabilities,
            frozenset({UART, I2C, SPI, JTAG, GPIO}),
        )

    def test_ft2232h_exposes_two_mpsse_interfaces(self):
        bridge = make_bridge(
            vid=0x0403, pid=0x6010, interface_count=2, device_version=0x0700
        )
        self.assertEqual([item.name for item in bridge.interfaces], ["A", "B"])
        self.assertTrue(all(I2C in item.capabilities for item in bridge.interfaces))

    def test_ft2232_cd_does_not_claim_supported_i2c(self):
        bridge = make_bridge(
            vid=0x0403, pid=0x6010, interface_count=2, device_version=0x0500
        )
        self.assertTrue(all(I2C not in item.capabilities for item in bridge.interfaces))
        self.assertTrue(all(SPI in item.capabilities for item in bridge.interfaces))

    def test_ft4232_only_exposes_mpsse_on_first_two_interfaces(self):
        bridge = make_bridge(vid=0x0403, pid=0x6011, interface_count=4)
        self.assertTrue(all(I2C in item.capabilities for item in bridge.interfaces[:2]))
        self.assertTrue(all(I2C not in item.capabilities for item in bridge.interfaces[2:]))
        self.assertTrue(all(UART in item.capabilities for item in bridge.interfaces))

    def test_ft232r_does_not_claim_mpsse_protocols(self):
        bridge = make_bridge(vid=0x0403, pid=0x6001)
        self.assertEqual(bridge.interfaces[0].capabilities, frozenset({UART, GPIO}))

    def test_custom_usb_description_does_not_hide_chip_model(self):
        bridge = make_bridge(
            vid=0x0403,
            pid=0x6011,
            serial="\uffff\uffff5WIGOU",
            description="USB <->MYUART",
        )
        self.assertEqual(bridge.model, "FT4232H")
        self.assertIn("FT4232H — USB <->MYUART", bridge.label)
        self.assertIn("S/N 5WIGOU", bridge.label)

    def test_discovery_flushes_pyftdi_hotplug_cache(self):
        with patch("pyftdi.usbtools.UsbTools.flush_cache") as flush_cache, patch(
            "pyftdi.ftdi.Ftdi.list_devices", return_value=[]
        ):
            self.assertEqual(discover_usb_bridges(), [])
        flush_cache.assert_called_once_with()

    def test_unknown_product_is_not_guessed(self):
        self.assertIsNone(product_for(0x0403, 0xFFFF))
        self.assertIsNone(make_bridge(vid=0x1234, pid=0x5678))

    def test_manager_uses_runtime_capabilities(self):
        manager = UsbBridgeInterfaceManager(
            {"A": UART}, capabilities={"A": {UART, I2C}, "B": {UART}}
        )
        manager.set_mode("A", I2C)
        with self.assertRaises(ValueError):
            manager.set_mode("B", I2C)
        manager.acquire("A", I2C, "scanner")
        with self.assertRaises(InterfaceBusyError):
            manager.set_mode("A", UART)

    def test_serial_port_maps_composite_usb_interface(self):
        port = SimpleNamespace(vid=0x0403, pid=0x6011, location="1-2:1.3")
        self.assertEqual(bridge_interface_for_port(port), "D")

    def test_single_interface_adapter_does_not_require_location_suffix(self):
        port = SimpleNamespace(vid=0x0403, pid=0x6014, location="")
        self.assertEqual(bridge_interface_for_port(port), "A")


if __name__ == "__main__":
    unittest.main()
