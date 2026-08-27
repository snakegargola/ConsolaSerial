"""Background execution for a complete SPI command sequence."""

from __future__ import annotations

from datetime import datetime
import threading
import time

from .spi_bus import classify_spi_error, execute_spi_transaction


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
