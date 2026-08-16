"""Tests for independent FT4232 channel allocation."""

import unittest

from app.config_manager import ScopedConfig
from app.ft4232_channels import ChannelBusyError, FtdiChannelManager


class FakeConfigManager:
    def __init__(self):
        self.config = {}
        self.saved = False

    def save(self):
        self.saved = True
        return True


class FtdiChannelManagerTests(unittest.TestCase):
    def test_different_channels_can_be_owned_simultaneously(self):
        manager = FtdiChannelManager({"A": "I2C", "B": "I2C"})
        manager.acquire("A", "I2C", "sensor bus")
        manager.acquire("B", "I2C", "display bus")
        self.assertEqual(manager.owner("A"), "sensor bus")
        self.assertEqual(manager.owner("B"), "display bus")

    def test_same_channel_rejects_a_second_owner(self):
        manager = FtdiChannelManager({"A": "UART"})
        manager.acquire("A", "UART", "console one")
        with self.assertRaises(ChannelBusyError):
            manager.acquire("A", "UART", "console two")

    def test_mode_cannot_change_while_channel_is_owned(self):
        manager = FtdiChannelManager({"A": "UART"})
        manager.acquire("A", "UART", "console")
        with self.assertRaises(ChannelBusyError):
            manager.set_mode("A", "I2C")
        manager.release("A", "console")
        manager.set_mode("A", "I2C")
        self.assertEqual(manager.mode("A"), "I2C")

    def test_channels_c_and_d_reject_mpsse_modes(self):
        manager = FtdiChannelManager()
        for channel in "CD":
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                manager.set_mode(channel, "I2C")


class ScopedConfigTests(unittest.TestCase):
    def test_each_channel_keeps_independent_uart_settings(self):
        parent = FakeConfigManager()
        channel_a = ScopedConfig(parent, ("sessions", "A", "uart"), {"baud": 9600})
        channel_b = ScopedConfig(parent, ("sessions", "B", "uart"), {"baud": 9600})
        channel_a.set("baud", 115200)
        channel_b.set("baud", 57600)
        self.assertEqual(channel_a.get("baud"), 115200)
        self.assertEqual(channel_b.get("baud"), 57600)

    def test_history_is_scoped(self):
        parent = FakeConfigManager()
        channel_a = ScopedConfig(parent, ("sessions", "A"))
        channel_b = ScopedConfig(parent, ("sessions", "B"))
        channel_a.add_to_history("A command")
        channel_b.add_to_history("B command")
        self.assertEqual(channel_a.get("cmd_history"), ["A command"])
        self.assertEqual(channel_b.get("cmd_history"), ["B command"])


if __name__ == "__main__":
    unittest.main()
