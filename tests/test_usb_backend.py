"""Portable libusb backend and frozen-runtime diagnostic tests."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app import usb_backend
from app.runtime_diagnostics import build_runtime_report
from main import run_self_test


class UsbBackendTests(unittest.TestCase):
    def test_packaged_backend_is_used_when_system_backend_is_missing(self):
        packaged_backend = object()
        with patch.object(
            usb_backend.libusb1,
            "get_backend",
            side_effect=(None, packaged_backend),
        ) as get_backend:
            self.assertIs(usb_backend.get_backend(), packaged_backend)
        self.assertEqual(usb_backend.backend_source(), "libusb-package")
        self.assertEqual(get_backend.call_count, 2)
        self.assertIn("find_library", get_backend.call_args_list[1].kwargs)

    def test_runtime_report_loads_native_libusb_without_touching_hardware(self):
        report = build_runtime_report()
        self.assertTrue(report["ok"])
        self.assertTrue(os.path.exists(report["libusb_library"]))
        self.assertNotEqual(report["packages"]["libusb-package"], "missing")

    def test_command_line_self_test_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "runtime.json")
            self.assertEqual(run_self_test(["program", "--self-test", path]), 0)
            with open(path, "r", encoding="utf-8") as stream:
                report = json.load(stream)
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
