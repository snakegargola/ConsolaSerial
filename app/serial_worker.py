import threading
import serial
import serial.tools.list_ports


def list_ports():
    """Return list of available serial port names."""
    return [p.device for p in serial.tools.list_ports.comports()]


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
