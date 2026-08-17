"""FTDI MPSSE I2C workers with optional, lazy PyFtdi imports."""

import threading
import time

from .i2c_bus import (
    append_write_pec, classify_i2c_error, coerce_bus_settings,
    configure_i2c_controller, verify_combined_pec, verify_read_pec,
    verify_receive_pec, validate_7bit_address,
)


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


def resolve_memory_bank(base_address, absolute_address, bank_size=0):
    """Return ``(slave_address, internal_address)`` for a banked EEPROM.

    A zero bank size keeps the complete absolute address inside the device.
    Positive bank sizes model parts such as 24C04/08/16, where the upper
    address bits select consecutive 7-bit slave addresses.
    """
    base_address = validate_7bit_address(base_address)
    if int(absolute_address) < 0:
        raise ValueError("Memory address cannot be negative.")
    if int(bank_size) < 0:
        raise ValueError("Memory bank size cannot be negative.")
    if bank_size:
        slave_address = base_address + int(absolute_address) // int(bank_size)
        internal_address = int(absolute_address) % int(bank_size)
    else:
        slave_address = base_address
        internal_address = int(absolute_address)
    if slave_address > 0x77:
        raise ValueError("Banked memory address exceeds the usable 7-bit I2C range.")
    return slave_address, internal_address


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
        self._settings = coerce_bus_settings(frequency)
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
            configure_i2c_controller(controller, self._url, self._settings)
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
        self._settings = coerce_bus_settings(frequency)
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
            configure_i2c_controller(controller, self._url, self._settings)
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
        self._settings = coerce_bus_settings(frequency)
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
            configure_i2c_controller(controller, self._url, self._settings)
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
        self._settings = coerce_bus_settings(frequency)
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
            configure_i2c_controller(controller, self._url, self._settings)
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
        self._settings = coerce_bus_settings(frequency)
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
            configure_i2c_controller(controller, self._url, self._settings)
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
                 write_delay_ms, bank_size, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._settings = coerce_bus_settings(frequency)
        self._operation = operation
        self._address = address
        self._start = start
        self._register_width = register_width
        self._big_endian = big_endian
        self._length = length
        self._payload = bytes(payload)
        self._page_size = page_size
        self._write_delay_ms = write_delay_ms
        self._bank_size = int(bank_size or 0)
        self._on_done = on_done
        self._on_error = on_error
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def _port_for(self, controller, absolute):
        address, register = resolve_memory_bank(
            self._address, absolute, self._bank_size
        )
        port = controller.get_port(address)
        port.configure_register(
            bigendian=self._big_endian, width=self._register_width
        )
        return port, register

    def _read_range(self, controller, length):
        result = bytearray()
        while len(result) < length:
            if self._stop_event.is_set():
                raise RuntimeError("Memory operation stopped.")
            absolute = self._start + len(result)
            size = min(self.READ_CHUNK, length - len(result))
            if self._bank_size:
                size = min(size, self._bank_size - (absolute % self._bank_size))
            port, register = self._port_for(controller, absolute)
            result.extend(port.read_from(register, size))
        return bytes(result)

    def run(self):
        controller = None
        try:
            from pyftdi.i2c import I2cController
            controller = I2cController()
            configure_i2c_controller(controller, self._url, self._settings)
            if self._operation == "read":
                result = self._read_range(controller, self._length)
            else:
                for absolute, chunk in iter_memory_pages(
                    self._start, self._payload, self._page_size
                ):
                    if self._stop_event.is_set():
                        raise RuntimeError("Memory operation stopped.")
                    pending = bytes(chunk)
                    cursor = absolute
                    while pending:
                        size = len(pending)
                        if self._bank_size:
                            size = min(
                                size,
                                self._bank_size - (cursor % self._bank_size),
                            )
                        port, register = self._port_for(controller, cursor)
                        port.write_to(register, pending[:size])
                        pending = pending[size:]
                        cursor += size
                        if self._write_delay_ms and self._stop_event.wait(
                            self._write_delay_ms / 1000.0
                        ):
                            raise RuntimeError("Memory operation stopped.")
                result = self._read_range(controller, len(self._payload))
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


class I2cLabWorker(threading.Thread):
    """Execute one raw-I2C or SMBus transaction and return structured data."""

    def __init__(self, url, settings, request, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._settings = coerce_bus_settings(settings)
        self._request = dict(request)
        self._on_done = on_done
        self._on_error = on_error

    def stop(self):
        # One USB transaction cannot be safely interrupted mid-byte.
        pass

    def _raw_transaction(self, controller, port):
        operation = self._request["operation"]
        payload = bytes(self._request.get("payload", b""))
        read_length = int(self._request.get("read_length", 0))
        if operation == "write":
            port.write(payload)
            return b""
        if operation == "read":
            return bytes(port.read(read_length))
        if operation == "write_read":
            # I2cPort.exchange emits write + repeated START + read + STOP.
            return bytes(port.exchange(payload, read_length))
        if operation == "probe_read":
            if not controller.poll(self._request["address"], write=False):
                raise RuntimeError("Address returned NACK in read mode.")
            return b""
        if operation == "probe_write":
            if not controller.poll(self._request["address"], write=True):
                raise RuntimeError("Address returned NACK in write mode.")
            return b""
        raise ValueError(f"Unsupported raw transaction: {operation}")

    def _smbus_transaction(self, controller, port):
        function = self._request["operation"]
        address = int(self._request["address"])
        command = int(self._request.get("command", 0))
        payload = bytes(self._request.get("payload", b""))
        use_pec = bool(self._request.get("pec", False))

        if function in {"quick_write", "quick_read"}:
            acknowledged = controller.poll(
                address, write=function == "quick_write"
            )
            if not acknowledged:
                raise RuntimeError("SMBus Quick command returned NACK.")
            return b""
        if function == "send_byte":
            port.write(append_write_pec(address, payload) if use_pec else payload)
            return b""
        if function == "receive_byte":
            response = bytes(port.read(2 if use_pec else 1))
            return verify_receive_pec(address, response) if use_pec else response

        write_payload = bytes((command,))
        if function in {"write_byte", "write_word"}:
            write_payload += payload
            port.write(
                append_write_pec(address, write_payload)
                if use_pec else write_payload
            )
            return b""
        if function in {"read_byte", "read_word"}:
            length = 1 if function == "read_byte" else 2
            response = bytes(port.exchange(write_payload, length + int(use_pec)))
            return (
                verify_read_pec(address, command, response)
                if use_pec else response
            )
        if function == "process_call":
            response = bytes(port.exchange(write_payload + payload, 2 + int(use_pec)))
            return (
                verify_combined_pec(address, write_payload + payload, response)
                if use_pec else response
            )
        if function == "block_write":
            if not 1 <= len(payload) <= 32:
                raise ValueError("SMBus block writes require 1–32 data bytes.")
            frame = write_payload + bytes((len(payload),)) + payload
            port.write(append_write_pec(address, frame) if use_pec else frame)
            return b""
        if function == "block_read":
            maximum = int(self._request.get("read_length", 32))
            if not 1 <= maximum <= 32:
                raise ValueError("SMBus block read maximum must be 1–32 bytes.")
            # Keep the bus active so the device-provided length byte can decide
            # how many additional bytes are clocked without a new START.
            port.write(write_payload, relax=False)
            length_byte = bytes(port.read(1, relax=False))
            count = length_byte[0]
            if not 1 <= count <= 32:
                # Finish the open transaction before reporting a malformed
                # length byte, so the next operation does not inherit it.
                port.read(0, start=False)
                raise ValueError(f"Invalid SMBus block length returned: {count}.")
            tail = bytes(port.read(count + int(use_pec), start=False))
            response = length_byte + tail
            if count > maximum:
                raise ValueError(
                    f"Device returned {count} bytes, above configured maximum {maximum}."
                )
            if use_pec:
                response = verify_read_pec(address, command, response)
            return response[1:1 + count]
        raise ValueError(f"Unsupported SMBus function: {function}")

    def run(self):
        controller = None
        started = time.perf_counter()
        try:
            from pyftdi.i2c import I2cController

            controller = I2cController()
            actual_frequency = configure_i2c_controller(
                controller, self._url, self._settings
            )
            address = validate_7bit_address(self._request["address"])
            self._request["address"] = address
            port = controller.get_port(address)
            if self._request.get("protocol", "raw") == "smbus":
                received = self._smbus_transaction(controller, port)
            else:
                received = self._raw_transaction(controller, port)
            result = {
                **self._request,
                "received": bytes(received),
                "status": "ACK",
                "actual_frequency": actual_frequency,
                "duration_ms": (time.perf_counter() - started) * 1000.0,
            }
            self._on_done(result)
        except Exception as exc:
            error = {
                **self._request,
                **classify_i2c_error(exc),
                "received": b"",
                "duration_ms": (time.perf_counter() - started) * 1000.0,
            }
            self._on_error(error)
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass


class I2cBusDiagnosticWorker(threading.Thread):
    """Read bus line state or recover a slave holding SDA low.

    Recovery only drives SCL/SDA low. A released line is configured as input,
    which emulates open-drain behavior and avoids electrical contention.
    """

    SCL = 0x01  # xDBUS0
    SDA_OUT = 0x02  # xDBUS1, physically joined to xDBUS2
    SDA_IN = 0x04  # xDBUS2

    def __init__(self, url, action, on_done, on_error):
        super().__init__(daemon=True)
        self._url = url
        self._action = action
        self._on_done = on_done
        self._on_error = on_error

    def stop(self):
        pass

    @classmethod
    def _line_state(cls, gpio):
        pins = int(gpio.read())
        return {
            "raw": pins,
            "scl_high": bool(pins & cls.SCL),
            "sda_high": bool(pins & cls.SDA_IN),
        }

    def run(self):
        gpio = None
        try:
            from pyftdi.gpio import GpioAsyncController

            if self._action not in {"check", "recover"}:
                raise ValueError(f"Unsupported I2C diagnostic action: {self._action}")

            gpio = GpioAsyncController()
            gpio.configure(
                self._url, direction=0x00, initial=0x00, frequency=10_000
            )
            time.sleep(0.002)
            before = self._line_state(gpio)
            pulses = 0
            if self._action == "recover":
                gpio.write(0x00)
                for _ in range(9):
                    # Pull SCL low, then release it to the external pull-up.
                    gpio.set_direction(self.SCL, self.SCL)
                    gpio.write(0x00)
                    time.sleep(0.0001)
                    gpio.set_direction(self.SCL, 0x00)
                    time.sleep(0.0001)
                    pulses += 1
                    if self._line_state(gpio)["sda_high"]:
                        break
                # STOP: SDA low while SCL low, release SCL, then release SDA.
                gpio.set_direction(
                    self.SCL | self.SDA_OUT, self.SCL | self.SDA_OUT
                )
                gpio.write(0x00)
                time.sleep(0.0001)
                gpio.set_direction(self.SCL, 0x00)
                time.sleep(0.0001)
                gpio.set_direction(self.SDA_OUT, 0x00)
                time.sleep(0.002)
            after = self._line_state(gpio)
            self._on_done({
                "action": self._action,
                "before": before,
                "after": after,
                "pulses": pulses,
                "healthy": after["scl_high"] and after["sda_high"],
            })
        except Exception as exc:
            self._on_error({"action": self._action, **classify_i2c_error(exc)})
        finally:
            if gpio is not None:
                try:
                    gpio.close()
                except Exception:
                    pass
