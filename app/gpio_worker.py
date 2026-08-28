"""Background FTDI GPIO access for dedicated and SPI-shared modes."""

from __future__ import annotations

import threading
import time

from .gpio_bus import GpioState
from .spi_bus import SpiBusSettings, classify_spi_error


def apply_gpio_port(port, state: GpioState, *, write_outputs: bool = True) -> dict:
    """Apply direction/output masks and sample a PyFtdi-compatible GPIO port."""
    port.set_direction(state.available_mask, state.direction)
    if write_outputs:
        port.write(state.output)
    try:
        sampled = port.read(with_output=True)
    except TypeError:  # Generic GPIO ports do not expose ``with_output``.
        sampled = port.read()
    if isinstance(sampled, (bytes, bytearray, tuple)):
        sampled = sampled[-1] if sampled else 0
    return state.result(int(sampled))


class GpioWorker(threading.Thread):
    """Execute one GPIO update/read without blocking Qt's event loop."""

    def __init__(self, url, state, on_done, *, mpsse=True,
                 spi_settings: SpiBusSettings | None = None,
                 write_outputs=True):
        super().__init__(daemon=True)
        self.url = str(url)
        self.state = state
        self.on_done = on_done
        self.mpsse = bool(mpsse)
        self.spi_settings = spi_settings
        self.write_outputs = bool(write_outputs)

    def run(self):
        started = time.perf_counter()
        controller = None
        result = {"status": None, **self.state.result(0)}
        try:
            if self.spi_settings is not None:
                from pyftdi.spi import SpiController
                settings = self.spi_settings
                controller = SpiController(
                    cs_count=settings.cs_count, turbo=settings.turbo
                )
                controller.configure(
                    self.url, frequency=settings.frequency,
                    cs_count=settings.cs_count, turbo=settings.turbo,
                )
                port = controller.get_gpio()
            elif self.mpsse:
                from pyftdi.gpio import GpioMpsseController
                controller = GpioMpsseController()
                controller.configure(
                    self.url, direction=self.state.direction,
                    initial=self.state.output, frequency=1_000_000,
                )
                port = controller.get_gpio()
            else:
                from pyftdi.gpio import GpioAsyncController
                controller = GpioAsyncController()
                controller.configure(
                    self.url, direction=self.state.direction,
                    initial=self.state.output,
                )
                port = controller.get_gpio()
            result.update(apply_gpio_port(
                port, self.state, write_outputs=self.write_outputs
            ))
            result["status"] = "OK"
        except Exception as exc:
            result.update(classify_spi_error(exc))
        finally:
            if controller is not None:
                try:
                    # Keep output latches stable after this short-lived worker
                    # releases USB ownership. A later operation/session will
                    # explicitly configure them again.
                    controller.close(freeze=result.get("status") == "OK")
                except Exception as exc:
                    if result.get("status") == "OK":
                        result.update(classify_spi_error(exc))
            result["duration_ms"] = (time.perf_counter() - started) * 1000.0
            self.on_done(result)
