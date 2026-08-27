"""Background execution for a complete SPI command sequence."""

from __future__ import annotations

from datetime import datetime
import threading
import time

from .spi_bus import classify_spi_error, execute_spi_transaction


class SpiSequenceWorker(threading.Thread):
    def __init__(self, url, settings, steps, on_done):
        super().__init__(daemon=True)
        self.url = str(url)
        self.settings = settings
        self.steps = tuple(steps)
        self.on_done = on_done

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
            for index, step in enumerate(self.steps):
                step_started = time.perf_counter()
                if step.operation == "delay":
                    time.sleep(step.delay_ms / 1000.0)
                    received = b""
                else:
                    received = execute_spi_transaction(port, step.transaction())
                    if step.delay_ms:
                        time.sleep(step.delay_ms / 1000.0)
                passed, details = step.validate_rx(received)
                result["steps"].append({
                    "index": index, "name": step.name, "operation": step.operation,
                    "tx": step.tx, "rx": received,
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
