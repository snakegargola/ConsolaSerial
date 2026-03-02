import json
import os
import sys

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
    "sequence_commands": [],
    "sequence_interval": 1.0,
    "sequence_mode": "Stop",
    "sequence_panel_width": 360,
    "sequence_command_col_width": 220,
    "alerts": [],
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
        self.config = DEFAULT_CONFIG.copy()
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
                self.config = DEFAULT_CONFIG.copy()

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
