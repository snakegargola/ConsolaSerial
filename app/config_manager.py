import json
import os
import sys
from copy import deepcopy

DEFAULT_CONFIG = {
    "port": "",
    "baud": 115200,
    "databits": 8,
    "parity": "None",
    "stopbits": "1",
    "flowcontrol": "None",
    "eol_tx": "LF",
    "eol_rx": "LF",
    "color_rx": "#00FF7F",
    "color_tx": "#00BFFF",
    "color_bg": "#1C1C1C",
    "show_ascii": True,
    "show_hex": False,
    "show_timestamp": True,
    "theme": "dark",
    "cmd_history": [],
    "auto_send_interval": 1.0,
    "send_format": "ASCII",
    "uart_rts": True,
    "uart_dtr": True,
    "uart_loopback_frames": 16,
    "uart_loopback_payload_size": 64,
    "uart_loopback_timeout": 1.0,
    "sequence_commands": [],
    "sequence_interval": 1.0,
    "sequence_mode": "Stop",
    "sequence_panel_width": 360,
    "sequence_command_col_width": 220,
    "alerts": [],
    "i2c_device_url": "",
    "i2c_channel": 1,
    "i2c_frequency": 100000,
    "i2c_clock_stretching": False,
    "i2c_retry_count": 3,
    "spi_frequency": 1_000_000,
    "spi_mode": 0,
    "spi_cs_count": 1,
    "spi_chip_select": 0,
    "spi_dummy_byte": "00",
    "spi_turbo": False,
    "spi_operation": "write_read",
    "spi_tx": "9F",
    "spi_rx_length": 3,
    "spi_loopback_pattern": "00 FF AA 55 12 34 56 78",
    "usb_bridge_modes": {},
    "usb_bridge_sessions": {},
    # Legacy keys are retained so existing config.json files remain readable.
    "ft4232_channel_a_mode": "I2C",
    "ft4232_channel_b_mode": "I2C",
    "ft4232_sessions": {
        "A": {"uart": {}, "i2c": {}},
        "B": {"uart": {}, "i2c": {}},
        "C": {"uart": {}},
        "D": {"uart": {}},
    },
    "quick_commands": {
        "F1": "",
        "F2": "",
        "F3": "",
        "F4": "",
        "F5": ""
    }
}

if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(__file__))

CONFIG_FILE = os.path.join(_BASE_DIR, "config.json")


class ConfigManager:
    def __init__(self):
        self.config = deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge with defaults to handle missing keys in older configs
                for key, value in DEFAULT_CONFIG.items():
                    self.config[key] = data.get(key, value)
            except (json.JSONDecodeError, OSError):
                self.config = deepcopy(DEFAULT_CONFIG)

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def add_to_history(self, cmd: str, max_entries: int = 20):
        history = self.config.get("cmd_history", [])
        if cmd in history:
            history.remove(cmd)
        history.insert(0, cmd)
        self.config["cmd_history"] = history[:max_entries]


class ScopedConfig:
    """Expose one nested configuration dictionary through ConfigManager's API."""

    def __init__(self, parent, path, defaults=None):
        self.parent = parent
        self.path = tuple(path)
        self.defaults = deepcopy(defaults or {})

    def _bucket(self):
        bucket = self.parent.config
        for key in self.path:
            value = bucket.get(key)
            if not isinstance(value, dict):
                value = {}
                bucket[key] = value
            bucket = value
        return bucket

    def get(self, key, default=None):
        fallback = self.defaults.get(key, default)
        return self._bucket().get(key, deepcopy(fallback))

    def set(self, key, value):
        self._bucket()[key] = value

    def save(self):
        return self.parent.save()

    def add_to_history(self, cmd, max_entries=20):
        history = list(self.get("cmd_history", []))
        if cmd in history:
            history.remove(cmd)
        history.insert(0, cmd)
        self.set("cmd_history", history[:max_entries])
