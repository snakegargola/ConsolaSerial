"""PyUSB backend selection with a packaged libusb fallback.

PyFtdi imports backend modules by name and expects each module to expose a
``get_backend`` function.  Prefer the operating-system libusb installation;
the ``libusb-package`` wheel is a portable fallback, especially for the
PyInstaller Windows executable.
"""

from __future__ import annotations

import ctypes
import os

from usb.backend import libusb1


_backend_source = "unavailable"


def get_backend():
    """Return a usable libusb1 backend, or ``None`` when none can be loaded."""
    global _backend_source

    backend = libusb1.get_backend()
    if backend is not None:
        _backend_source = "system"
        return backend

    try:
        import libusb_package
    except ImportError:
        _backend_source = "unavailable"
        return None

    backend = libusb1.get_backend(find_library=libusb_package.find_library)
    _backend_source = "libusb-package" if backend is not None else "unavailable"
    return backend


def backend_source():
    """Return the source selected by the most recent ``get_backend`` call."""
    return _backend_source


def validate_packaged_library():
    """Load the bundled native library without enumerating USB devices.

    Calling ``libusb_init`` during a package self-test can be rejected by a
    sandbox or CI host. Loading the library and resolving its required symbol
    proves that PyInstaller included the correct native binary without touching
    hardware.
    """
    import libusb_package

    library_path = libusb_package.get_library_path()
    if library_path is None:
        raise RuntimeError("libusb-package does not contain a native library.")
    loader = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
    library = loader(str(library_path))
    if not getattr(library, "libusb_init", None):
        raise RuntimeError("The packaged libusb library has no libusb_init symbol.")
    return str(library_path)
