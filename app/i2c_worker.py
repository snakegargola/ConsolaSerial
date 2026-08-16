"""FTDI MPSSE I2C support with an optional, lazy PyFtdi import."""

import threading


def iter_memory_pages(start, payload, page_size):
    """Yield address/data chunks without crossing EEPROM page boundaries.

    Most serial EEPROMs wrap writes that cross a physical page. Keeping this
    calculation independent from the USB worker makes it easy to test and
    reuse while preserving the original payload exactly.
    """
    if start < 0:
        raise ValueError("Memory start address cannot be negative.")
    if page_size <= 0:
        raise ValueError("Memory page size must be greater than zero.")
    data = bytes(payload)
    offset = 0
    while offset < len(data):
        absolute = start + offset
        page_remaining = page_size - (absolute % page_size)
        size = min(page_remaining, len(data) - offset)
        yield absolute, data[offset:offset + size]
        offset += size


def ssd1306_init_steps(height):
    """Return the documented initialization sequence used by Display Test."""
    compins = 0x12 if height == 64 else 0x02
    contrast = 0xCF if height == 64 else 0x8F
    return [
        ("Display OFF", [0xAE], "Turn display off while configuration changes."),
        ("Clock divide", [0xD5, 0x80], "Set display clock divide and oscillator."),
        ("Multiplex ratio", [0xA8, height - 1], f"Configure {height} display rows."),
        ("Display offset", [0xD3, 0x00], "Use zero vertical display offset."),
        ("Start line", [0x40], "Select display RAM line 0 as the first line."),
        ("Charge pump", [0x8D, 0x14], "Enable the internal charge pump."),
        ("Memory mode", [0x20, 0x00], "Use horizontal addressing mode."),
        ("Segment remap", [0xA1], "Map column 127 to segment 0."),
        ("COM scan", [0xC8], "Scan COM outputs in descending order."),
        ("COM pins", [0xDA, compins], "Configure COM pin hardware layout."),
        ("Contrast", [0x81, contrast], "Set panel contrast."),
        ("Pre-charge", [0xD9, 0xF1], "Set pre-charge period."),
        ("VCOM detect", [0xDB, 0x40], "Set VCOMH deselect level."),
        ("RAM display", [0xA4], "Show display RAM instead of forcing pixels on."),
        ("Normal mode", [0xA6], "Use normal, non-inverted pixels."),
        ("Display ON", [0xAF], "Turn the configured display on."),
    ]


def list_i2c_bridge_devices():
    """Return detected adapters that expose at least one I2C interface."""
    from .usb_bridge import I2C, discover_usb_bridges

    return [
        (bridge.label, bridge.base_url)
        for bridge in discover_usb_bridges()
        if any(I2C in interface.capabilities for interface in bridge.interfaces)
    ]


def list_ft4232_devices():
    """Compatibility alias; discovery is no longer limited to FT4232."""
    return list_i2c_bridge_devices()


class I2cScanWorker(threading.Thread):
    """Scan the standard 7-bit I2C address range without blocking the GUI."""

    def __init__(self, url, frequency, on_found, on_progress, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._frequency = frequency
        self._on_found = on_found
        self._on_progress = on_progress
        self._on_done = on_done
        self._on_error = on_error
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        controller = None
        try:
            try:
                from pyftdi.i2c import I2cController
            except ImportError as exc:
                raise RuntimeError(
                    "PyFtdi is not installed. Run: pip install -r requirements.txt"
                ) from exc

            controller = I2cController()
            controller.configure(self._url, frequency=self._frequency)
            found = []
            total = 0x78 - 0x03
            for index, address in enumerate(range(0x03, 0x78), start=1):
                if self._stop_event.is_set():
                    self._on_done(found, True, controller.frequency)
                    return
                # Address-only read probe: no register or payload is written.
                if controller.poll(address, write=False):
                    found.append(address)
                    self._on_found(address)
                self._on_progress(index, total)
            self._on_done(found, False, controller.frequency)
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass


class I2cTransactionWorker(threading.Thread):
    """Perform one register read or write on a 7-bit I2C target."""

    def __init__(self, url, frequency, operation, device_address, register,
                 register_width, big_endian, payload, read_length,
                 on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._frequency = frequency
        self._operation = operation
        self._device_address = device_address
        self._register = register
        self._register_width = register_width
        self._big_endian = big_endian
        self._payload = payload
        self._read_length = read_length
        self._on_done = on_done
        self._on_error = on_error

    def stop(self):
        # A single USB transaction cannot be interrupted safely mid-transfer.
        pass

    def run(self):
        controller = None
        try:
            from pyftdi.i2c import I2cController
            controller = I2cController()
            controller.configure(self._url, frequency=self._frequency)
            port = controller.get_port(self._device_address)
            port.configure_register(
                bigendian=self._big_endian, width=self._register_width
            )
            if self._operation == "read":
                result = bytes(port.read_from(self._register, self._read_length))
            else:
                port.write_to(self._register, self._payload)
                result = b""
            self._on_done(self._operation, result)
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass


class Ssd1306Worker(threading.Thread):
    """Run a quick SSD1306 command or framebuffer test."""

    def __init__(self, url, frequency, address, width, height, action,
                 on_done, on_error, framebuffer=None):
        super().__init__(daemon=True)
        self._url = url
        self._frequency = frequency
        self._address = address
        self._width = width
        self._height = height
        self._action = action
        self._on_done = on_done
        self._on_error = on_error
        self._custom_framebuffer = framebuffer

    def stop(self):
        pass

    @staticmethod
    def _write_commands(port, *commands):
        port.write(bytes((0x00, *commands)))

    def _initialize(self, port):
        for _name, commands, _description in ssd1306_init_steps(self._height):
            self._write_commands(port, *commands)

    def _framebuffer(self):
        if self._custom_framebuffer is not None:
            expected = self._width * (self._height // 8)
            if len(self._custom_framebuffer) != expected:
                raise ValueError(f"Framebuffer must contain {expected} bytes.")
            return bytes(self._custom_framebuffer)
        pages = self._height // 8
        data = bytearray(self._width * pages)
        if self._action == "all_on":
            data[:] = b"\xFF" * len(data)
        elif self._action == "border":
            for page in range(pages):
                for x in range(self._width):
                    if x in (0, self._width - 1):
                        value = 0xFF
                    elif page == 0:
                        value = 0x01
                    elif page == pages - 1:
                        value = 0x80
                    else:
                        value = 0x00
                    data[page * self._width + x] = value
        elif self._action == "grid":
            for page in range(pages):
                for x in range(self._width):
                    data[page * self._width + x] = 0xFF if x % 16 == 0 else 0x01
        elif self._action == "bars":
            for page in range(pages):
                value = (0xFF << (page % 8)) & 0xFF
                start = page * self._width
                data[start:start + self._width] = bytes((value,)) * self._width
        return bytes(data)

    def _write_framebuffer(self, port):
        pages = self._height // 8
        self._write_commands(
            port, 0x21, 0x00, self._width - 1, 0x22, 0x00, pages - 1
        )
        data = self._framebuffer()
        for offset in range(0, len(data), 32):
            port.write(b"\x40" + data[offset:offset + 32])

    def run(self):
        controller = None
        try:
            from pyftdi.i2c import I2cController
            controller = I2cController()
            controller.configure(self._url, frequency=self._frequency)
            port = controller.get_port(self._address)
            if self._action == "initialize":
                self._initialize(port)
            elif self._action in ("clear", "all_on", "border", "grid", "bars", "custom"):
                self._write_framebuffer(port)
            else:
                commands = {
                    "invert": (0xA7,), "normal": (0xA6,),
                    "display_on": (0xAF,), "display_off": (0xAE,),
                }
                self._write_commands(port, *commands[self._action])
            self._on_done(self._action)
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass


class I2cRawWriteWorker(threading.Thread):
    """Send one raw I2C payload, used by the command trace step runner."""

    def __init__(self, url, frequency, address, payload, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._frequency = frequency
        self._address = address
        self._payload = payload
        self._on_done = on_done
        self._on_error = on_error

    def stop(self):
        pass

    def run(self):
        controller = None
        try:
            from pyftdi.i2c import I2cController
            controller = I2cController()
            controller.configure(self._url, frequency=self._frequency)
            controller.get_port(self._address).write(self._payload)
            self._on_done("trace_step")
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass


class I2cSequenceWorker(threading.Thread):
    """Execute a user-defined sequence of raw writes and delays."""

    def __init__(self, url, frequency, address, steps,
                 on_step, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._frequency = frequency
        self._address = address
        self._steps = steps
        self._on_step = on_step
        self._on_done = on_done
        self._on_error = on_error
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        controller = None
        try:
            from pyftdi.i2c import I2cController
            controller = I2cController()
            controller.configure(self._url, frequency=self._frequency)
            port = controller.get_port(self._address)
            for index, step in enumerate(self._steps):
                if self._stop_event.is_set():
                    self._on_done(True)
                    return
                if step["type"] == "Delay":
                    if self._stop_event.wait(step["milliseconds"] / 1000.0):
                        self._on_done(True)
                        return
                else:
                    port.write(step["payload"])
                self._on_step(index)
            self._on_done(False)
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass


class I2cMemoryWorker(threading.Thread):
    """Read or safely page-write an I2C memory, then verify written bytes."""

    READ_CHUNK = 32

    def __init__(self, url, frequency, operation, address, start,
                 register_width, big_endian, length, payload, page_size,
                 write_delay_ms, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._frequency = frequency
        self._operation = operation
        self._address = address
        self._start = start
        self._register_width = register_width
        self._big_endian = big_endian
        self._length = length
        self._payload = bytes(payload)
        self._page_size = page_size
        self._write_delay_ms = write_delay_ms
        self._on_done = on_done
        self._on_error = on_error
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def _read_range(self, port, length):
        result = bytearray()
        while len(result) < length:
            if self._stop_event.is_set():
                raise RuntimeError("Memory operation stopped.")
            size = min(self.READ_CHUNK, length - len(result))
            result.extend(port.read_from(self._start + len(result), size))
        return bytes(result)

    def run(self):
        controller = None
        try:
            from pyftdi.i2c import I2cController
            controller = I2cController()
            controller.configure(self._url, frequency=self._frequency)
            port = controller.get_port(self._address)
            port.configure_register(
                bigendian=self._big_endian, width=self._register_width
            )
            if self._operation == "read":
                result = self._read_range(port, self._length)
            else:
                for absolute, chunk in iter_memory_pages(
                    self._start, self._payload, self._page_size
                ):
                    if self._stop_event.is_set():
                        raise RuntimeError("Memory operation stopped.")
                    port.write_to(absolute, chunk)
                    if self._write_delay_ms and self._stop_event.wait(
                        self._write_delay_ms / 1000.0
                    ):
                        raise RuntimeError("Memory operation stopped.")
                result = self._read_range(port, len(self._payload))
                if result != self._payload:
                    for index, (expected, actual) in enumerate(zip(self._payload, result)):
                        if expected != actual:
                            raise RuntimeError(
                                f"Verification failed at 0x{self._start + index:X}: "
                                f"wrote 0x{expected:02X}, read 0x{actual:02X}."
                            )
                    raise RuntimeError("Memory verification failed.")
            self._on_done(self._operation, result)
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass
