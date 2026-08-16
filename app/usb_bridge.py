"""Capability catalog and discovery for supported USB protocol bridges.

The UI consumes capabilities instead of checking for one product name.  The
catalog is deliberately independent from Qt, PySerial, and PyFtdi so another
vendor/backend can be added without rewriting the channel workspace.
"""

from dataclasses import dataclass
from typing import FrozenSet, Iterable


UART = "UART"
I2C = "I2C"
SPI = "SPI"
JTAG = "JTAG"
GPIO = "GPIO"
MPSSE_PROTOCOLS = frozenset({UART, I2C, SPI, JTAG, GPIO})
LEGACY_MPSSE_PROTOCOLS = frozenset({UART, SPI, JTAG, GPIO})
UART_GPIO = frozenset({UART, GPIO})


@dataclass(frozen=True)
class BridgeInterface:
    """One independently configurable interface exposed by an adapter."""

    index: int
    name: str
    capabilities: FrozenSet[str]

    @property
    def has_mpsse(self):
        return bool({I2C, SPI, JTAG} & self.capabilities)


@dataclass(frozen=True)
class UsbBridge:
    """A detected physical adapter and its independently usable interfaces."""

    backend: str
    vendor: str
    model: str
    vid: int
    pid: int
    serial: str
    bus: int | None
    address: int | None
    base_url: str
    interfaces: tuple[BridgeInterface, ...]

    @property
    def key(self):
        identity = self.serial or f"usb-{self.bus}-{self.address}"
        return f"{self.backend}-{self.vid:04x}-{self.pid:04x}-{identity}"

    @property
    def label(self):
        location = f"USB {self.bus}:{self.address}" if self.bus is not None else "USB"
        serial = f", S/N {self.serial}" if self.serial else ""
        return f"{self.vendor} {self.model} ({location}{serial})"


@dataclass(frozen=True)
class BridgeProduct:
    model: str
    interfaces: tuple[FrozenSet[str], ...]


def _interfaces(*capability_sets: Iterable[str]):
    return tuple(frozenset(values) for values in capability_sets)


# FTDI product IDs and interface topology documented by FTDI/PyFtdi.  PID
# PID 0x6010 is shared by FT2232C/D/H. The older C/D variants expose MPSSE,
# but PyFtdi deliberately rejects standards-compliant I2C on them.
FTDI_PRODUCTS = {
    0x6001: BridgeProduct("FT232R", _interfaces(UART_GPIO)),
    0x6010: BridgeProduct(
        "FT2232C/D family",
        _interfaces(LEGACY_MPSSE_PROTOCOLS, LEGACY_MPSSE_PROTOCOLS),
    ),
    0x6011: BridgeProduct(
        "FT4232H",
        _interfaces(MPSSE_PROTOCOLS, MPSSE_PROTOCOLS, UART_GPIO, UART_GPIO),
    ),
    0x6014: BridgeProduct("FT232H", _interfaces(MPSSE_PROTOCOLS)),
    0x6015: BridgeProduct("FT-X series", _interfaces(UART_GPIO)),
    0x6043: BridgeProduct(
        "FT4232HP",
        _interfaces(MPSSE_PROTOCOLS, MPSSE_PROTOCOLS, UART_GPIO, UART_GPIO),
    ),
    0x6048: BridgeProduct(
        "FT4232HA",
        _interfaces(MPSSE_PROTOCOLS, MPSSE_PROTOCOLS, UART_GPIO, UART_GPIO),
    ),
}


def product_for(vid, pid):
    """Return a known product definition, or ``None`` without guessing."""
    if int(vid or 0) != 0x0403:
        return None
    return FTDI_PRODUCTS.get(int(pid or 0))


def interface_name(index):
    """Return A..Z for normal channel counts, then a numeric fallback."""
    return chr(ord("A") + index - 1) if 1 <= index <= 26 else str(index)


def make_bridge(*, vid, pid, serial="", bus=None, address=None,
                description="", interface_count=None, device_version=None):
    """Build a normalized descriptor from a USB enumeration record."""
    product = product_for(vid, pid)
    if product is None:
        return None
    product_interfaces = product.interfaces
    detected_model = product.model
    if int(pid) == 0x6010 and device_version == 0x0700:
        detected_model = "FT2232H"
        product_interfaces = _interfaces(MPSSE_PROTOCOLS, MPSSE_PROTOCOLS)
    count = int(interface_count or len(product_interfaces))
    count = min(count, len(product_interfaces))
    interfaces = tuple(
        BridgeInterface(index, interface_name(index), product_interfaces[index - 1])
        for index in range(1, count + 1)
    )
    model = detected_model
    if description and description.strip() and int(pid) != 0x6010:
        model = description.strip()
    if bus is not None and address is not None:
        selector = f"{int(bus)}:{int(address)}"
    elif serial:
        selector = str(serial)
    else:
        # This URL is only a last-resort selector; normal discovery supplies a
        # serial number or bus/address pair.
        selector = "1"
    base_url = f"ftdi://0x{int(vid):04x}:0x{int(pid):04x}:{selector}"
    return UsbBridge(
        backend="pyftdi", vendor="FTDI", model=model,
        vid=int(vid), pid=int(pid), serial=str(serial or ""),
        bus=None if bus is None else int(bus),
        address=None if address is None else int(address),
        base_url=base_url, interfaces=interfaces,
    )


def discover_usb_bridges():
    """Discover known bridges through PyFtdi without importing it at startup."""
    try:
        from pyftdi.ftdi import Ftdi
    except ImportError:
        return []

    from pyftdi.usbtools import UsbTools

    bridges = []
    seen = set()
    for device, interface_count in Ftdi.list_devices("ftdi://ftdi/?"):
        device_version = None
        if getattr(device, "pid", 0) == 0x6010:
            usb_device = None
            try:
                usb_device = UsbTools.get_device(device)
                device_version = int(usb_device.bcdDevice)
            except Exception:
                # Unknown 0x6010 devices use conservative C/D capabilities.
                pass
            finally:
                if usb_device is not None:
                    UsbTools.release_device(usb_device)
        bridge = make_bridge(
            vid=getattr(device, "vid", 0),
            pid=getattr(device, "pid", 0),
            serial=(getattr(device, "sn", "") or
                    getattr(device, "serial_number", "")),
            bus=getattr(device, "bus", None),
            address=getattr(device, "address", None),
            description=getattr(device, "description", ""),
            interface_count=interface_count,
            device_version=device_version,
        )
        if bridge and bridge.key not in seen:
            seen.add(bridge.key)
            bridges.append(bridge)
    return bridges


def capability_summary(bridge):
    """Human-readable per-interface capabilities for the adapter selector."""
    return " | ".join(
        f"{interface.name}: {', '.join(sorted(interface.capabilities))}"
        for interface in bridge.interfaces
    )
