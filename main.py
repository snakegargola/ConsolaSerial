"""
main.py — Entry point for the Serial Monitor application.

Usage:
    GuisSerial/bin/python main.py
"""

import sys
import os

# Ensure the project root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from app.config_manager import ConfigManager
from app.serial_monitor import SerialMonitorApp


def main():
    app = QApplication(sys.argv)
    config = ConfigManager()
    window = SerialMonitorApp(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
