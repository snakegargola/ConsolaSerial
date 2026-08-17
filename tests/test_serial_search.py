"""UI test for the single, literal serial-monitor search bar."""

from copy import deepcopy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.bridge_interface_manager import UsbBridgeInterfaceManager
from app.config_manager import DEFAULT_CONFIG
from app.serial_monitor import SerialMonitorApp, UartSessionPanel
from app.usb_bridge import make_bridge


class _MemoryConfig:
    def __init__(self):
        self.config = deepcopy(DEFAULT_CONFIG)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def save(self):
        return True

    def add_to_history(self, _command, max_entries=20):
        del max_entries


class SerialSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        bridge = make_bridge(vid=0x0403, pid=0x6011, serial="TEST")
        manager = UsbBridgeInterfaceManager(capabilities={
            interface.name: interface.capabilities
            for interface in bridge.interfaces
        })
        window = UartSessionPanel(
            bridge.interfaces[0], bridge, _MemoryConfig(), manager
        )
        self.addCleanup(window.close)
        return window

    def test_general_console_is_hidden_for_a_managed_bridge(self):
        decision = SerialMonitorApp._general_console_should_be_visible
        self.assertFalse(decision(has_protocol_bridge=True))
        self.assertTrue(decision(has_protocol_bridge=False))

    def test_ft232r_opens_only_the_usb_bridge_tab(self):
        ft232r = make_bridge(vid=0x0403, pid=0x6001, serial="FT232R-TEST")
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)
        window._usb_bridge_discovery_finished([ft232r], "")

        self.assertFalse(window.main_tabs.isTabVisible(0))
        self.assertTrue(window.main_tabs.isTabVisible(1))
        self.assertEqual(window.main_tabs.currentIndex(), 1)

    def test_no_bridge_opens_only_the_general_tab(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)

        self.assertTrue(window.main_tabs.isTabVisible(0))
        self.assertFalse(window.main_tabs.isTabVisible(1))
        self.assertEqual(window.main_tabs.currentIndex(), 0)

    def test_hot_swap_replaces_ft232r_with_ft4232_workspace(self):
        ft232r = make_bridge(vid=0x0403, pid=0x6001, serial="OLD")
        ft4232 = make_bridge(
            vid=0x0403, pid=0x6011, serial="NEW", interface_count=4
        )
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)

        window._usb_bridge_discovery_finished([ft232r], "")
        self.assertEqual(window.active_bridge.model, "FT232R")
        self.assertEqual(window.usb_bridge_channel_tabs.count(), 1)

        window._usb_bridge_discovery_finished([ft4232], "")
        self.assertEqual(window.active_bridge.model, "FT4232H")
        self.assertEqual(window.usb_bridge_channel_tabs.count(), 4)
        self.assertFalse(window.main_tabs.isTabVisible(0))
        self.assertTrue(window.main_tabs.isTabVisible(1))

    def test_literal_search_replaces_filter_and_wraps_navigation(self):
        window = self._window()

        window._append("RX: Hola mundo\n", "#00FF7F")
        window._append("TX: hola otra vez\n", "#00BFFF")
        window.search_edit.setText("hola")

        self.assertFalse(hasattr(window, "filter_edit"))
        self.assertEqual(len(window._search_results), 2)
        window._search_next()
        self.assertEqual(window.search_result_lbl.text(), "1/2")
        window._search_next()
        self.assertEqual(window.search_result_lbl.text(), "2/2")
        window._search_next()
        self.assertEqual(window.search_result_lbl.text(), "1/2")

        window.search_edit.clear()
        self.assertEqual(window.monitor.extraSelections(), [])

    def test_hex_mode_shows_exact_bytes_and_blocks_incomplete_input(self):
        window = self._window()
        window.send_fmt.setCurrentText("HEX")

        window.send_edit.setText("AA 5")
        self.assertFalse(window.send_btn.isEnabled())
        self.assertIn("incomplete byte", window.send_preview.text())

        window.send_edit.setText("AA 55")
        self.assertTrue(window.send_btn.isEnabled())
        self.assertEqual(window.send_preview.text(), "AA 55 0A")

        window.send_fmt.setCurrentText("ASCII")
        window.send_edit.setText("A")
        self.assertEqual(window.send_preview.text(), "41 0A")


if __name__ == "__main__":
    unittest.main()
