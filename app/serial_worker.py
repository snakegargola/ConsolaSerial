import threading
import os
import serial
import serial.tools.list_ports
import re

from .usb_bridge import product_for


def list_ports():
    """Return list of available serial port names."""
    return [p.device for p in serial.tools.list_ports.comports()]


def bridge_interface_for_port(port):
    """Return the known bridge interface name for a PySerial port, if any."""
    product = product_for(getattr(port, "vid", None), getattr(port, "pid", None))
    if product is None:
        return None
    match = re.search(r"\.(\d+)$", getattr(port, "location", "") or "")
    if match:
        index = int(match.group(1)) + 1
    elif len(product.interfaces) == 1:
        index = 1
    else:
        # Composite FTDI devices normally expose the USB interface number in
        # ``location``. Do not guess when multiple ports cannot be separated.
        return None
    if not 1 <= index <= len(product.interfaces):
        return None
    return chr(ord("A") + index - 1)


def list_port_details(channel_modes=None, *, include_usb_bridges=True,
                      only_bridge_interface=None, bridge_pid=None,
                      bridge_serial=None, include_ft4232=None,
                      only_ft4232_channel=None):
    """Return friendly serial ports with optional USB-bridge filtering.

    The two FT4232-named keyword arguments remain accepted for compatibility.
    """
    if include_ft4232 is not None:
        include_usb_bridges = include_ft4232
    if only_ft4232_channel is not None:
        only_bridge_interface = only_ft4232_channel
    channel_modes = channel_modes or {}
    result = []
    for port in serial.tools.list_ports.comports():
        product = product_for(getattr(port, "vid", None), getattr(port, "pid", None))
        channel = bridge_interface_for_port(port)
        if product and not include_usb_bridges:
            continue
        if bridge_pid is not None and getattr(port, "pid", None) != int(bridge_pid):
            continue
        if bridge_serial and getattr(port, "serial_number", "") != bridge_serial:
            continue
        if only_bridge_interface and channel != str(only_bridge_interface).upper():
            continue
        if only_bridge_interface and product is None:
            continue
        if channel and channel_modes.get(channel, "UART") != "UART":
            continue
        access = os.name == "nt" or os.access(port.device, os.R_OK | os.W_OK)
        warning = " — no permission" if not access else ""
        if channel:
            label = f"{product.model} interface {channel} — {port.device}{warning}"
        else:
            label = f"{port.device}{warning}"
        result.append((label, port.device))
    return result


def list_ft4232_channel_ports(channel):
    """Compatibility wrapper for legacy callers."""
    return list_bridge_interface_ports(channel, bridge_pid=0x6011)


def list_bridge_interface_ports(interface, *, bridge_pid=None, bridge_serial=None):
    """Return VCP ports belonging to one detected adapter interface."""
    return list_port_details(
        only_bridge_interface=str(interface).upper(),
        bridge_pid=bridge_pid,
        bridge_serial=bridge_serial,
    )


class SerialWorker(threading.Thread):
    """Background thread that reads from a serial port and fires callbacks."""

    def __init__(self, port, baud, databits, parity, stopbits, flowcontrol, eol_rx,
                 on_data, on_error):
        super().__init__(daemon=True)
        self._port = port
        self._baud = baud
        self._databits = databits
        self._parity = parity
        self._stopbits = stopbits
        self._flowcontrol = flowcontrol
        self._eol_rx = eol_rx
        self.on_data = on_data    # callback(bytes)
        self.on_error = on_error  # callback(str)
        self._stop_event = threading.Event()
        self._serial = None
        self._tx_lock = threading.Lock()
        self.rx_bytes = 0
        self.tx_bytes = 0

    # ---------- parity / stopbits mapping ----------
    _PARITY_MAP = {
        "None": serial.PARITY_NONE,
        "Even": serial.PARITY_EVEN,
        "Odd": serial.PARITY_ODD,
        "Mark": serial.PARITY_MARK,
        "Space": serial.PARITY_SPACE,
    }
    _STOPBITS_MAP = {
        "1": serial.STOPBITS_ONE,
        "1.5": serial.STOPBITS_ONE_POINT_FIVE,
        "2": serial.STOPBITS_TWO,
    }

    def run(self):
        try:
            rtscts = self._flowcontrol == "RTS/CTS"
            xonxoff = self._flowcontrol == "XON/XOFF"
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                bytesize=int(self._databits),
                parity=self._PARITY_MAP.get(self._parity, serial.PARITY_NONE),
                stopbits=self._STOPBITS_MAP.get(str(self._stopbits), serial.STOPBITS_ONE),
                rtscts=rtscts,
                xonxoff=xonxoff,
                timeout=0.1,
            )
        except serial.SerialException as e:
            self.on_error(str(e))
            return

        buffer = b""
        eol = self._get_eol_bytes()

        while not self._stop_event.is_set():
            try:
                chunk = self._serial.read(256)
            except serial.SerialException as e:
                self.on_error(str(e))
                break

            if not chunk:
                continue

            self.rx_bytes += len(chunk)

            if eol:
                buffer += chunk
                while eol in buffer:
                    line, buffer = buffer.split(eol, 1)
                    self.on_data(line + eol)
            else:
                # Raw mode — deliver chunks as-is
                self.on_data(chunk)

        if self._serial and self._serial.is_open:
            self._serial.close()

    def _get_eol_bytes(self) -> bytes:
        return {
            "LF": b"\n",
            "CR": b"\r",
            "CR+LF": b"\r\n",
            "None": b"",
        }.get(self._eol_rx, b"\n")

    def send(self, data: bytes):
        if self._serial and self._serial.is_open:
            with self._tx_lock:
                try:
                    self._serial.write(data)
                    self.tx_bytes += len(data)
                    return True
                except serial.SerialException as e:
                    self.on_error(str(e))
        return False

    def stop(self):
        self._stop_event.set()

    @property
    def is_connected(self):
        return self._serial is not None and self._serial.is_open
