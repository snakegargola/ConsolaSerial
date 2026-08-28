"""
main.py — Entry point for the Serial Monitor application.

Usage:
    GuisSerial/bin/python main.py
"""

import sys
import os
import json

# Ensure the project root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))


def run_self_test(arguments):
    """Validate a source or frozen distribution without opening the GUI."""
    option_index = arguments.index("--self-test")
    try:
        report_path = arguments[option_index + 1]
    except IndexError:
        report_path = os.path.abspath("runtime-self-test.json")
    try:
        from app.runtime_diagnostics import build_runtime_report
        report = build_runtime_report()
        exit_code = 0
    except Exception as exc:
        report = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 1
    try:
        with open(report_path, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
    except OSError:
        return 2
    return exit_code


def main():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from app.config_manager import ConfigManager
    from app.serial_monitor import SerialMonitorApp

    app = QApplication(sys.argv)
    app.setApplicationName("Consola Serial")
    app.setOrganizationName("Embedded Systems")
    app.setStyle("Fusion")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    config = ConfigManager()
    window = SerialMonitorApp(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test(sys.argv))
    main()
