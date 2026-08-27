"""Background SPI memory operations with page and verification safeguards."""

from __future__ import annotations

import threading
import time

from .spi_bus import classify_spi_error
from .spi_bus import SPI_MAX_PAYLOAD
from .spi_memory import decode_status_register, iter_page_programs, parse_jedec_id, parse_sfdp


class SpiMemoryWorker(threading.Thread):
    def __init__(self, url, settings, geometry, action, request, on_done):
        super().__init__(daemon=True)
        self.url, self.settings, self.geometry = str(url), settings, geometry
        self.action, self.request, self.on_done = action, dict(request), on_done

    def run(self):
        started = time.perf_counter(); controller = None
        result = {"action": self.action, "status": "OK", "data": b"",
                  "details": "", "error": ""}
        try:
            from pyftdi.spi import SpiController
            controller = SpiController(cs_count=self.settings.cs_count,
                                       turbo=self.settings.turbo)
            controller.configure(self.url, frequency=self.settings.frequency,
                                 cs_count=self.settings.cs_count,
                                 turbo=self.settings.turbo)
            port = controller.get_port(self.settings.chip_select,
                                       freq=self.settings.frequency, mode=self.settings.mode)
            entered_4byte = self.geometry.address_bytes == 4 and self.geometry.address_strategy == "enter_mode"
            if entered_4byte:
                port.write(b"\xb7", start=True, stop=True)
            if self.action == "identify":
                jedec = self._exchange(port, b"\x9f", 3)
                sfdp_raw = self._exchange(port, b"\x5a\x00\x00\x00\x00", 256)
                result.update(data=jedec, jedec=parse_jedec_id(jedec))
                if all(value == 0x00 for value in jedec) or all(value == 0xFF for value in jedec):
                    result.update(status="FAIL", details="JEDEC response is all 00/FF; check wiring, /CS and SPI mode")
                try: result["sfdp"] = parse_sfdp(sfdp_raw)
                except ValueError: result["sfdp"] = None
            elif self.action == "read":
                address, length = self.request["address"], self.request["length"]
                result["data"] = self._read(port, address, length)
                result["address"] = address
            elif self.action == "status":
                raw = self._exchange(port, bytes((self.geometry.status_command,)), 1)[0]
                result.update(data=bytes((raw,)), status_register=decode_status_register(
                    raw, busy_mask=self.geometry.busy_mask,
                    protection_mask=self.geometry.protection_mask))
            elif self.action == "program":
                address, payload = self.request["address"], bytes(self.request["data"])
                self._ensure_unprotected(port)
                for current, chunk in iter_page_programs(self.geometry, address, payload):
                    self._write_enable(port)
                    port.write(bytes((self.geometry.command_for("program"),)) +
                               self.geometry.address(current) + chunk)
                    self._wait_ready(port)
                verified = self._read(port, address, len(payload))
                result.update(data=verified, address=address,
                              status="PASS" if verified == payload else "FAIL",
                              details="Write verified" if verified == payload else "Verification mismatch")
            elif self.action == "erase_sector":
                address = self.request["address"]
                aligned = address - address % self.geometry.sector_size
                self._ensure_unprotected(port)
                self._write_enable(port)
                port.write(bytes((self.geometry.command_for("erase"),)) + self.geometry.address(aligned))
                self._wait_ready(port, timeout=120.0)
                result.update(address=aligned, details="Sector erase completed")
            else:
                raise ValueError("Unsupported SPI memory action.")
            result["actual_frequency"] = int(round(float(port.frequency)))
        except Exception as exc:
            result.update(classify_spi_error(exc))
        finally:
            if controller is not None and 'port' in locals() and locals().get('entered_4byte'):
                try: port.write(b"\xe9", start=True, stop=True)
                except Exception: pass
            if controller:
                try: controller.close()
                except Exception: pass
            result["duration_ms"] = (time.perf_counter() - started) * 1000
            self.on_done(result)

    @staticmethod
    def _exchange(port, command, length):
        port.write(command, start=True, stop=False)
        return bytes(port.exchange(b"\xff" * length, length,
                                   start=False, stop=True, duplex=True))

    def _read(self, port, address, length):
        output = bytearray()
        while len(output) < length:
            current = address + len(output)
            count = min(SPI_MAX_PAYLOAD, length - len(output))
            command = bytes((self.geometry.command_for("read"),)) + self.geometry.address(current)
            output.extend(self._exchange(port, command, count))
        return bytes(output)

    def _write_enable(self, port):
        port.write(bytes((self.geometry.write_enable_command,)), start=True, stop=True)

    def _ensure_unprotected(self, port):
        if not self.geometry.protection_mask: return
        raw = self._exchange(port, bytes((self.geometry.status_command,)), 1)[0]
        status = decode_status_register(raw, busy_mask=self.geometry.busy_mask,
                                        protection_mask=self.geometry.protection_mask)
        if status["protected"]:
            raise PermissionError(
                f"Memory protection bits are active (status 0x{raw:02X}, mask "
                f"0x{self.geometry.protection_mask:02X}). Unlock with the vendor procedure first."
            )

    def _wait_ready(self, port, timeout=10.0):
        if self.geometry.kind == "SPI FRAM":
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self._exchange(port, bytes((self.geometry.status_command,)), 1)[0]
            if not status & self.geometry.busy_mask:
                return
            time.sleep(max(0.001, self.geometry.write_delay_ms / 1000))
        raise TimeoutError("SPI memory remained busy after the operation timeout.")
