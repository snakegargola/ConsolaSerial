"""Background execution for a complete SPI command sequence."""

from __future__ import annotations

from datetime import datetime
import threading
import time

from .spi_bus import classify_spi_error, execute_spi_transaction
from .spi_gpio_loopback import exchange_gpio_loopback


class SpiSequenceWorker(threading.Thread):
    def __init__(self, url, settings, steps, on_done, timeout_seconds=30.0):
        super().__init__(daemon=True)
        self.url = str(url)
        self.settings = settings
        self.steps = tuple(steps)
        self.on_done = on_done
        self.timeout_seconds = float(timeout_seconds)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        if any(step.operation == "loopback" for step in self.steps):
            self._run_physical_loopback()
            return
        started = time.perf_counter()
        controller = None
        result = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "status": "OK", "steps": [], "error": "", "duration_ms": 0.0,
        }
        try:
            from pyftdi.spi import SpiController
            controller = SpiController(cs_count=self.settings.cs_count,
                                       turbo=self.settings.turbo)
            controller.configure(self.url, frequency=self.settings.frequency,
                                 cs_count=self.settings.cs_count,
                                 turbo=self.settings.turbo)
            # Never let unread USB/MPSSE bytes from an earlier run satisfy a
            # validation in this run.
            ftdi = getattr(controller, "ftdi", None)
            if ftdi is not None:
                ftdi.purge_buffers()
            port = controller.get_port(self.settings.chip_select,
                                       freq=self.settings.frequency,
                                       mode=self.settings.mode)
            last_rx = b""
            for index, step in enumerate(self.steps):
                if self._stop_event.is_set():
                    result["status"] = "STOPPED"; break
                if time.perf_counter() - started > self.timeout_seconds:
                    result["status"] = "TIMEOUT"; result["error"] = "Sequence timeout expired."; break
                step_started = time.perf_counter()
                if step.operation == "delay":
                    if self._stop_event.wait(step.delay_ms / 1000.0):
                        result["status"] = "STOPPED"; break
                    received = b""
                else:
                    transaction = step.transaction({"counter": index, "last_rx": last_rx})
                    received = execute_spi_transaction(port, transaction)
                    if step.delay_ms:
                        if self._stop_event.wait(step.delay_ms / 1000.0):
                            result["status"] = "STOPPED"; break
                passed, details = step.validate_rx(received)
                last_rx = received
                result["steps"].append({
                    "index": index, "name": step.name, "operation": step.operation,
                    "tx": b"" if step.operation == "delay" else transaction.tx, "rx": received,
                    "status": "PASS" if passed else "FAIL", "details": details,
                    "duration_ms": (time.perf_counter() - step_started) * 1000.0,
                })
                if not passed:
                    result["status"] = "FAIL"
                    break
            result["actual_frequency"] = int(round(float(port.frequency)))
        except Exception as exc:
            result.update(classify_spi_error(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception:
                    pass
            result["duration_ms"] = (time.perf_counter() - started) * 1000.0
            self.on_done(result)

    def _run_physical_loopback(self):
        started = time.perf_counter(); gpio = None
        result = {"timestamp": datetime.now().isoformat(timespec="milliseconds"),
                  "status": "OK", "steps": [], "error": "", "duration_ms": 0.0}
        try:
            if any(step.operation not in ("loopback", "delay") for step in self.steps):
                raise ValueError("Physical loopback cannot be mixed with SPI transactions.")
            from pyftdi.gpio import GpioMpsseController
            gpio = GpioMpsseController()
            gpio.configure(self.url, direction=0x03,
                           frequency=min(self.settings.frequency, 1_000_000))
            gpio.ftdi.enable_loopback_mode(False)
            for index, step in enumerate(self.steps):
                if self._stop_event.is_set(): result["status"] = "STOPPED"; break
                if time.perf_counter() - started > self.timeout_seconds:
                    result.update(status="TIMEOUT", error="Sequence timeout expired."); break
                if step.operation == "delay":
                    if self._stop_event.wait(step.delay_ms / 1000): result["status"] = "STOPPED"; break
                    received = b""; transmitted = b""
                else:
                    transaction = step.transaction({"counter": index, "last_rx": b""})
                    transmitted = transaction.tx
                    received = exchange_gpio_loopback(gpio, transmitted, self.settings.mode)
                passed, details = step.validate_rx(received)
                result["steps"].append({"index": index, "name": step.name,
                    "operation": step.operation, "tx": transmitted, "rx": received,
                    "status": "PASS" if passed else "FAIL", "details": details,
                    "duration_ms": 0.0, "physical_gpio": True})
                if not passed: result["status"] = "FAIL"; break
        except Exception as exc: result.update(classify_spi_error(exc))
        finally:
            if gpio:
                try: gpio.close()
                except Exception: pass
            result["duration_ms"] = (time.perf_counter() - started) * 1000
            self.on_done(result)
