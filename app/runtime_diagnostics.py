"""Dependency self-test used to validate frozen Linux and Windows builds."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import platform
import sys


REQUIRED_PACKAGES = (
    "PyQt6",
    "pyserial",
    "Pillow",
    "pyftdi",
    "pyusb",
    "libusb-package",
)


def _package_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        # PyInstaller normally omits distribution metadata even though the
        # importable package is bundled; imports above are the actual check.
        return "bundled (metadata unavailable)"


def build_runtime_report():
    """Load every runtime dependency and verify that native libusb opens."""
    # Explicit imports make frozen-build failures visible during validation.
    from PIL import Image  # noqa: F401
    from PyQt6 import QtWidgets  # noqa: F401
    import serial  # noqa: F401
    import usb  # noqa: F401
    import pyftdi  # noqa: F401
    import libusb_package  # noqa: F401
    from pyftdi.i2c import I2cController  # noqa: F401
    from pyftdi.spi import SpiController  # noqa: F401

    # Import the full UI graph so missing application modules and Qt classes
    # also fail the frozen executable's self-test before distribution.
    from .serial_monitor import SerialMonitorApp  # noqa: F401

    from .usb_backend import validate_packaged_library

    library_path = validate_packaged_library()
    return {
        "ok": True,
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "libusb_library": library_path,
        "packages": {
            package: _package_version(package)
            for package in REQUIRED_PACKAGES
        },
    }
