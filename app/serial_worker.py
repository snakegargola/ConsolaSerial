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
                 on_data, on_error, on_raw_data=None,
                 initial_rts=True, initial_dtr=True):
        super().__init__(daemon=True)
        self._port = port
        self._baud = baud
        self._databits = databits
        self._parity = parity
        self._stopbits = stopbits
        self._flowcontrol = flowcontrol
        self._eol_rx = eol_rx
        self._initial_rts = bool(initial_rts)
        self._initial_dtr = bool(initial_dtr)
        self.on_data = on_data    # callback(bytes)
        self.on_error = on_error  # callback(str)
        self.on_raw_data = on_raw_data  # callback(bytes), before EOL framing
        self._stop_event = threading.Event()
        self._serial = None
        self._tx_lock = threading.Lock()
        self._control_lock = threading.Lock()
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
        connection = None
        try:
            rtscts = self._flowcontrol == "RTS/CTS"
            xonxoff = self._flowcontrol == "XON/XOFF"
            # Configure output states before opening to avoid a needless
            # RTS/DTR pulse on boards that use these lines for reset/boot.
            connection = serial.Serial()
            connection.port = self._port
            connection.baudrate = self._baud
            connection.bytesize = int(self._databits)
            connection.parity = self._PARITY_MAP.get(
                self._parity, serial.PARITY_NONE
            )
            connection.stopbits = self._STOPBITS_MAP.get(
                str(self._stopbits), serial.STOPBITS_ONE
            )
            connection.rtscts = rtscts
            connection.xonxoff = xonxoff
            connection.timeout = 0.1
            connection.rts = self._initial_rts
            connection.dtr = self._initial_dtr
            connection.open()
            self._serial = connection
        except (OSError, ValueError, serial.SerialException) as e:
            if connection is not None and connection.is_open:
                connection.close()
            self.on_error(str(e))
            return

        buffer = b""
        eol = self._get_eol_bytes()

        while not self._stop_event.is_set():
            try:
                chunk = self._serial.read(256)
            except (OSError, serial.SerialException) as e:
                self.on_error(str(e))
                break

            if not chunk:
                continue

            self.rx_bytes += len(chunk)
            if self.on_raw_data:
                self.on_raw_data(chunk)

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
                except (OSError, serial.SerialException) as e:
                    self.on_error(str(e))
        return False

    def set_control_line(self, line: str, asserted: bool):
        """Set RTS or DTR safely from the GUI thread."""
        attribute = {"RTS": "rts", "DTR": "dtr"}.get(str(line).upper())
        if attribute is None:
            return False, f"Unsupported UART control line: {line}"
        with self._control_lock:
            connection = self._serial
            if connection is None or not connection.is_open:
                return False, "Serial port is not connected."
            try:
                setattr(connection, attribute, bool(asserted))
            except (OSError, ValueError, serial.SerialException) as exc:
                return False, str(exc)
        return True, ""

    def set_break(self, asserted: bool):
        """Assert or release TX BREAK without sleeping in the GUI thread."""
        with self._control_lock:
            connection = self._serial
            if connection is None or not connection.is_open:
                return False, "Serial port is not connected."
            try:
                connection.break_condition = bool(asserted)
            except (OSError, ValueError, serial.SerialException) as exc:
                return False, str(exc)
        return True, ""

    def modem_status(self):
        """Return input control-line states, or an error if unavailable."""
        with self._control_lock:
            connection = self._serial
            if connection is None or not connection.is_open:
                return None, "Serial port is not connected."
            try:
                status = {
                    "CTS": bool(connection.cts),
                    "DSR": bool(connection.dsr),
                    "DCD": bool(connection.cd),
                    "RI": bool(connection.ri),
                }
            except (OSError, ValueError, serial.SerialException) as exc:
                return None, str(exc)
        return status, ""

    def stop(self):
        self._stop_event.set()
        # Wake a blocking platform read immediately during hot-unplug/shutdown.
        # The worker thread remains responsible for closing the port.
        connection = self._serial
        if connection is not None:
            try:
                connection.cancel_read()
            except (AttributeError, OSError, serial.SerialException):
                pass

    @property
    def is_connected(self):
        return self._serial is not None and self._serial.is_open
