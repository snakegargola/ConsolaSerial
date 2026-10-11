"""UI test for the single, literal serial-monitor search bar."""

from copy import deepcopy
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

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
        self.assertFalse(window.usb_bridge_mode_panel.isHidden())

    def test_no_bridge_opens_only_the_general_tab(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)

        self.assertTrue(window.main_tabs.isTabVisible(0))
        self.assertFalse(window.main_tabs.isTabVisible(1))
        self.assertEqual(window.main_tabs.currentIndex(), 0)
        self.assertTrue(window.usb_bridge_mode_panel.isHidden())

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

    def test_ft4232_spi_is_selectable_only_on_mpsse_interfaces(self):
        ft4232 = make_bridge(
            vid=0x0403, pid=0x6011, serial="SPI-TEST", interface_count=4
        )
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)
        window._usb_bridge_discovery_finished([ft4232], "")

        modes_a = [
            window.usb_bridge_mode_combos["A"].itemText(index)
            for index in range(window.usb_bridge_mode_combos["A"].count())
        ]
        modes_c = [
            window.usb_bridge_mode_combos["C"].itemText(index)
            for index in range(window.usb_bridge_mode_combos["C"].count())
        ]
        self.assertEqual(modes_a, ["UART", "I2C", "SPI", "GPIO"])
        self.assertEqual(modes_c, ["UART", "GPIO"])

        window.usb_bridge_mode_combos["A"].setCurrentText("SPI")
        window._apply_usb_bridge_workspace_modes(show_error=False)
        self.assertEqual(window.channel_manager.mode("A"), "SPI")
        self.assertIs(
            window.usb_bridge_channel_stacks["A"].currentWidget(),
            window.usb_bridge_spi_sessions["A"],
        )
        self.assertEqual(window.channel_manager.owner("A"), "SPI session A")

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

    def test_display_switch_reformats_rx_and_tx_without_losing_bytes_or_times(self):
        window = self._window()
        with patch.object(window, "_check_alerts") as alerts:
            window._display_rx(b"A\x00\xff\r\n")
            window._record_serial_data(b"OK\n", "TX")
            original = window.monitor.toPlainText()
            timestamps = [entry.timestamp for entry in window.log]
            window.display_fmt.setCurrentText("HEX")
            hex_view = window.monitor.toPlainText()
            self.assertNotIn("ASCII:", hex_view)
            self.assertIn("RX  HEX: 41 00 FF 0D 0A", hex_view)
            self.assertIn("TX  HEX: 4F 4B 0A", hex_view)
            window.display_fmt.setCurrentText("ASCII + HEX")
            self.assertIn("ASCII: OK  HEX: 4F 4B 0A", window.monitor.toPlainText())
            window.display_fmt.setCurrentText("ASCII")
            self.assertEqual(window.monitor.toPlainText(), original)
            self.assertEqual([entry.timestamp for entry in window.log], timestamps)
            self.assertEqual(len(window.log), 2)
            alerts.assert_called_once()

    def test_display_switch_updates_search_colors_and_export(self):
        window = self._window()
        window._display_rx(b"A\n")
        window._record_serial_data(b"B\n", "TX")
        window.search_edit.setText("41 0A")
        self.assertEqual(window._search_results, [])
        window.display_fmt.setCurrentText("HEX")
        self.assertEqual(len(window._search_results), 1)
        document = window.monitor.document()
        for block, color in ((document.firstBlock(), window._color_rx),
                             (document.lastBlock().previous(), window._color_tx)):
            self.assertEqual(block.begin().fragment().charFormat().foreground().color().name(), color.lower())
        window.chk_ts.setChecked(False)
        self.assertNotIn("[", window.monitor.toPlainText())
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "monitor.log")
            self.assertTrue(window.log.save(path, window._format_log_entry))
            with open(path, encoding="utf-8") as exported:
                self.assertEqual(exported.read(), window.monitor.toPlainText())
        window._clear_monitor()
        window.display_fmt.setCurrentText("ASCII + HEX")
        self.assertEqual(window.monitor.toPlainText(), "")
        self.assertEqual(len(window.log), 0)

    def test_send_format_is_independent_and_all_tx_paths_reformat(self):
        window = self._window()
        worker = MagicMock(is_connected=True, tx_bytes=0)
        window.worker = worker
        self.addCleanup(setattr, window, "worker", None)
        window.display_fmt.setCurrentText("HEX")
        window.send_edit.setText("A")
        window._send_data()
        self.assertEqual(window.send_fmt.currentText(), "ASCII")
        window.send_fmt.setCurrentText("HEX")
        window.send_edit.setText("42")
        window._send_data()
        window._add_sequence_command(command="C")
        window._add_sequence_command(command="44", command_format="HEX")
        window._send_sequence_command(0)
        window._send_sequence_command_manual(1)
        self.assertEqual([call.args[0] for call in worker.send.call_args_list],
                         [b"A\n", b"B\n", b"C\n", b"D\n"])
        window.display_fmt.setCurrentText("ASCII + HEX")
        for letter, hex_byte in (("A", "41"), ("B", "42"), ("C", "43"), ("D", "44")):
            self.assertIn(f"TX  ASCII: {letter}  HEX: {hex_byte} 0A", window.monitor.toPlainText())
        self.assertEqual(worker.send.call_count, 4)
        self.assertEqual(window.send_fmt.currentText(), "HEX")

    def test_display_preferences_preserve_existing_config_keys(self):
        window = self._window()
        for ascii_on, hex_on, mode in ((True, False, "ASCII"), (False, True, "HEX"),
                                      (True, True, "ASCII + HEX"), (False, False, "ASCII")):
            window.config.set("show_ascii", ascii_on)
            window.config.set("show_hex", hex_on)
            window._load_uart_config()
            self.assertEqual(window.display_fmt.currentText(), mode)
            window._collect_uart_config()
            self.assertEqual(window.config.get("show_ascii"), mode != "HEX")
            self.assertEqual(window.config.get("show_hex"), mode != "ASCII")

    def test_incoming_burst_is_searchable_without_repeated_full_scans(self):
        window = self._window()
        window._append("match\n", "#00FF7F")
        window.search_edit.setText("match")
        with patch.object(window, "_refresh_search_results", wraps=window._refresh_search_results) as refresh:
            for _ in range(40):
                window._append("match\n", "#00FF7F")
            window._search_next()
            self.assertEqual(refresh.call_count, 1)
        self.assertEqual(window.search_result_lbl.text(), "1/41")
        self.assertEqual(window.monitor.toPlainText().count("match"), 41)

    def test_search_finds_matches_split_across_receive_chunks(self):
        window = self._window()
        window.search_edit.setText("hello")
        window._append("he", "#00FF7F")
        window._append("llo\n", "#00FF7F")
        window._search_previous()
        self.assertEqual(window.search_result_lbl.text(), "1/1")
        self.assertEqual(window.monitor.textCursor().selectedText(), "hello")

    def test_sequence_config_preserves_legacy_text_and_formats(self):
        window = self._window()
        commands = ["AT", {"command": "AA 55", "format": "HEX"}]
        window.config.set("sequence_commands", commands)
        window._load_sequence_commands()
        window._add_sequence_command(True)  # QPushButton.clicked(bool)
        window.seq_table.item(2, 1).setText("STATUS")
        window._collect_config()
        self.assertEqual(window.config.get("sequence_commands"), [
            {"command": "AT", "format": "ASCII"},
            {"command": "AA 55", "format": "HEX"},
            {"command": "STATUS", "format": "ASCII"},
        ])

    def test_adapter_replacement_releases_old_panels(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)
        for serial in ("FIRST", "SECOND", "THIRD"):
            bridge = make_bridge(vid=0x0403, pid=0x6001, serial=serial)
            window._usb_bridge_discovery_finished([bridge], "")
            old_pages = [window.usb_bridge_channel_tabs.widget(0)]
            old_session = window.usb_bridge_uart_sessions["A"]
            window._usb_bridge_discovery_finished([], "")
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertTrue(sip.isdeleted(old_pages[0]))
            self.assertTrue(sip.isdeleted(old_session))

    def test_removed_panel_waits_for_inflight_operation_before_deletion(self):
        class BusySession(QWidget):
            active = True

            def is_session_active(self):
                return self.active

        page = QWidget()
        session = BusySession(page)
        SerialMonitorApp._retire_bridge_page(page)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(sip.isdeleted(page))
        session.active = False
        page.findChild(QTimer).timeout.emit()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(sip.isdeleted(page))

    def test_workspace_theme_reaches_saved_and_new_sessions(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]):
            window = SerialMonitorApp(_MemoryConfig())
        self.addCleanup(window.close)
        for theme, serial in (("light", "FIRST"), ("dark", "SECOND")):
            window._apply_theme(theme)
            bridge = make_bridge(vid=0x0403, pid=0x6001, serial=serial)
            window._usb_bridge_discovery_finished([bridge], "")
            session = window.usb_bridge_uart_sessions["A"]
            self.assertEqual(session._dark_mode, theme == "dark")
            self.assertEqual(session.palette().window().color(), window.palette().window().color())
            self.assertEqual(session.styleSheet(), "")

    def test_small_window_keeps_send_controls_accessible(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]), patch.object(
            SerialMonitorApp, "_refresh_usb_bridges"
        ):
            window = SerialMonitorApp(_MemoryConfig())
            self.addCleanup(window.close)
            window.resize(1280, 800)
            window.show()
            for _ in range(6):
                self.app.processEvents()
            area = window.main_tabs.widget(0)
            area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
            self.app.processEvents()
            viewport = area.viewport()
            for control in (window.send_edit, window.send_btn, window.auto_btn):
                rectangle = QRect(control.mapTo(viewport, QPoint()), control.size())
                self.assertTrue(viewport.rect().contains(rectangle))
            monitor_bounds = QRect(window.monitor.pos(), window.monitor.size())
            self.assertTrue(window.monitor.parentWidget().rect().contains(monitor_bounds))

    def test_uart_hotplug_refreshes_ports_when_bridge_inventory_stays_empty(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]), patch(
            "app.serial_monitor.list_port_details", return_value=[]
        ) as ports:
            window = SerialMonitorApp(_MemoryConfig())
            self.addCleanup(window.close)
            ports.return_value = [("FT232R — /dev/ttyUSB0", "/dev/ttyUSB0")]
            window._usb_bridge_discovery_finished([], "")
            self.assertEqual(window.port_combo.findData("/dev/ttyUSB0"), 0)
            self.assertTrue(window.main_tabs.isTabVisible(0))
            self.assertTrue(window.usb_bridge_mode_panel.isHidden())
            ports.return_value = []
            window._usb_bridge_discovery_finished([], "")
            self.assertEqual(window.port_combo.findData("/dev/ttyUSB0"), -1)

    def test_uart_refresh_survives_a_bridge_backend_error(self):
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]), patch(
            "app.serial_monitor.list_port_details", return_value=[]
        ) as ports:
            window = SerialMonitorApp(_MemoryConfig())
            self.addCleanup(window.close)
            ports.return_value = [("FT232R — /dev/ttyUSB0", "/dev/ttyUSB0")]
            window._usb_bridge_discovery_finished([], "No backend available")
            self.assertEqual(window.port_combo.findData("/dev/ttyUSB0"), 0)
            self.assertTrue(window.main_tabs.isTabVisible(0))
            self.assertTrue(window.usb_bridge_mode_panel.isHidden())

    def test_bridge_uart_ports_refresh_without_rebuilding_sessions(self):
        bridge = make_bridge(vid=0x0403, pid=0x6001, serial="FT232R-TEST")
        with patch("app.serial_monitor.discover_usb_bridges", return_value=[]), patch(
            "app.serial_monitor.list_bridge_interface_ports", return_value=[]
        ) as ports:
            window = SerialMonitorApp(_MemoryConfig())
            self.addCleanup(window.close)
            window._usb_bridge_discovery_finished([bridge], "")
            session = window.usb_bridge_uart_sessions["A"]
            ports.return_value = [("FT232R interface A — /dev/ttyUSB0", "/dev/ttyUSB0")]
            window._usb_bridge_discovery_finished([bridge], "")
            self.assertIs(window.usb_bridge_uart_sessions["A"], session)
            self.assertEqual(session.port_combo.findData("/dev/ttyUSB0"), 0)


if __name__ == "__main__":
    unittest.main()
