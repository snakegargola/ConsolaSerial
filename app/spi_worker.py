"""Background execution of one SPI transaction through PyFtdi."""

from __future__ import annotations

from datetime import datetime
import threading
import time

from .spi_bus import (
    SpiBusSettings,
    SpiTransaction,
    classify_spi_error,
    execute_spi_transaction,
    format_spi_hex,
)


class SpiTransactionWorker(threading.Thread):
    """Configure, execute, report, and close one SPI transaction."""

    def __init__(self, url, settings, transaction, on_done):
        super().__init__(daemon=True)
        self.url = str(url)
        self.settings = settings
        self.transaction = transaction
        self.on_done = on_done

    def run(self):
        started = time.perf_counter()
        controller = None
        result = self._base_result()
        try:
            # Keep PyFtdi optional for users who only need ordinary UART.
            from pyftdi.spi import SpiController

            controller = SpiController(
                cs_count=self.settings.cs_count,
                turbo=self.settings.turbo,
            )
            controller.configure(
                self.url,
                frequency=self.settings.frequency,
                cs_count=self.settings.cs_count,
                turbo=self.settings.turbo,
            )
            port = controller.get_port(
                self.settings.chip_select,
                freq=self.settings.frequency,
                mode=self.settings.mode,
            )
            received = execute_spi_transaction(port, self.transaction)
            result.update(
                status="OK",
                rx=received,
                actual_frequency=int(round(float(port.frequency))),
            )
            self._annotate_special_result(result)
        except Exception as exc:
            result.update(classify_spi_error(exc))
        finally:
            if controller is not None:
                try:
                    controller.close()
                except Exception as exc:
                    if result.get("status") in (None, "OK", "PASS", "FAIL"):
                        result.update(classify_spi_error(exc))
            result["duration_ms"] = (time.perf_counter() - started) * 1000.0
            self.on_done(result)

    def _base_result(self):
        return {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "operation": self.transaction.operation,
            "frequency": self.settings.frequency,
            "actual_frequency": None,
            "mode": self.settings.mode,
            "chip_select": self.settings.chip_select,
            "tx": self.transaction.wire_tx,
            "rx": b"",
            "status": None,
            "error": "",
            "details": "",
            "duration_ms": 0.0,
        }

    def _annotate_special_result(self, result):
        received = result["rx"]
        if self.transaction.operation == "loopback":
            expected = self.transaction.tx
            result["status"] = "PASS" if received == expected else "FAIL"
            if received != expected:
                result["details"] = (
                    f"Expected {format_spi_hex(expected)}; "
                    f"received {format_spi_hex(received)}"
                )
        elif self.transaction.operation == "jedec" and len(received) >= 3:
            manufacturer, memory_type, capacity = received[:3]
            result["details"] = (
                f"JEDEC manufacturer 0x{manufacturer:02X}, "
                f"type 0x{memory_type:02X}, capacity 0x{capacity:02X}"
            )
