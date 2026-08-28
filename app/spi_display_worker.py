"""Background SPI display reset, initialization, and framebuffer transfer."""

from __future__ import annotations

import threading
import time

from .spi_bus import SpiBusSettings, classify_spi_error


def _pin_mask(pin):
    return 0 if pin is None else 1 << int(pin)


class SpiDisplayPort:
    """Coordinate SPI writes with D/C, reset and backlight GPIO levels."""

    def __init__(self, spi_port, gpio_port, *, dc_pin, reset_pin=None,
                 backlight_pin=None, backlight_on=True):
        self.spi = spi_port
        self.gpio = gpio_port
        self.dc_mask = _pin_mask(dc_pin)
        self.reset_mask = _pin_mask(reset_pin)
        self.backlight_mask = _pin_mask(backlight_pin)
        self.direction = self.dc_mask | self.reset_mask | self.backlight_mask
        self.value = self.reset_mask
        if backlight_on:
            self.value |= self.backlight_mask
        self.gpio.set_direction(self.direction, self.direction)
        self.gpio.write(self.value)

    def _level(self, mask, high):
        self.value = self.value | mask if high else self.value & ~mask
        self.gpio.write(self.value)

    def hardware_reset(self, low_ms=20, high_ms=120):
        if not self.reset_mask:
            return
        self._level(self.reset_mask, False)
        time.sleep(max(0, low_ms) / 1000.0)
        self._level(self.reset_mask, True)
        time.sleep(max(0, high_ms) / 1000.0)

    def command(self, command, data=b""):
        self._level(self.dc_mask, False)
        self.spi.write(bytes(command), start=True, stop=not bool(data))
        if data:
            self._level(self.dc_mask, True)
            self.spi.write(bytes(data), start=False, stop=True)

    def framebuffer(self, profile, payload, chunk_size=4096):
        if profile.pixel_format != "rgb565":
            raise ValueError("Framebuffer transfer currently requires RGB565.")
        expected = profile.width * profile.height * 2
        if len(payload) != expected:
            raise ValueError(f"Framebuffer requires {expected} bytes, got {len(payload)}.")
        x0, y0 = profile.column_offset, profile.row_offset
        x1, y1 = x0 + profile.width - 1, y0 + profile.height - 1
        self.command(b"\x2A", x0.to_bytes(2, "big") + x1.to_bytes(2, "big"))
        self.command(b"\x2B", y0.to_bytes(2, "big") + y1.to_bytes(2, "big"))
        self._level(self.dc_mask, False)
        self.spi.write(b"\x2C", start=True, stop=False)
        self._level(self.dc_mask, True)
        offsets = range(0, len(payload), int(chunk_size))
        last_offset = ((len(payload) - 1) // int(chunk_size)) * int(chunk_size)
        for offset in offsets:
            self.spi.write(
                payload[offset:offset + int(chunk_size)], start=False,
                stop=offset == last_offset,
            )


class SpiDisplayWorker(threading.Thread):
    """Run one complete display action with a single SPI controller owner."""

    def __init__(self, url, settings: SpiBusSettings, profile, action, gpio_pins,
                 on_done, *, payload=b"", backlight_on=True):
        super().__init__(daemon=True)
        self.url = str(url)
        self.settings = settings
        self.profile = profile
        self.action = str(action)
        self.gpio_pins = dict(gpio_pins)
        self.on_done = on_done
        self.payload = bytes(payload)
        self.backlight_on = bool(backlight_on)

    def run(self):
        started = time.perf_counter()
        controller = None
        result = {"status": None, "action": self.action, "bytes_sent": 0}
        try:
            from pyftdi.spi import SpiController
            controller = SpiController(
                cs_count=self.settings.cs_count, turbo=self.settings.turbo
            )
            controller.configure(
                self.url, frequency=self.settings.frequency,
                cs_count=self.settings.cs_count, turbo=self.settings.turbo,
            )
            spi = controller.get_port(
                self.settings.chip_select, freq=self.settings.frequency,
                mode=self.settings.mode,
            )
            display = SpiDisplayPort(
                spi, controller.get_gpio(), dc_pin=self.gpio_pins["dc"],
                reset_pin=self.gpio_pins.get("reset"),
                backlight_pin=self.gpio_pins.get("backlight"),
                backlight_on=self.backlight_on,
            )
            if self.action == "reset":
                display.hardware_reset()
            elif self.action == "initialize":
                display.hardware_reset()
                for step in self.profile.init_steps:
                    display.command(step.command, step.data)
                    if step.delay_ms:
                        time.sleep(step.delay_ms / 1000.0)
            elif self.action == "framebuffer":
                display.framebuffer(self.profile, self.payload)
                result["bytes_sent"] = len(self.payload)
            elif self.action == "initialize_framebuffer":
                display.hardware_reset()
                for step in self.profile.init_steps:
                    display.command(step.command, step.data)
                    if step.delay_ms:
                        time.sleep(step.delay_ms / 1000.0)
                display.framebuffer(self.profile, self.payload)
                result["bytes_sent"] = len(self.payload)
            else:
                raise ValueError(f"Unsupported SPI display action: {self.action}")
            result["status"] = "OK"
            result["actual_frequency"] = int(round(float(spi.frequency)))
        except Exception as exc:
            result.update(classify_spi_error(exc))
        finally:
            if controller is not None:
                try:
                    controller.close(freeze=result.get("status") == "OK")
                except Exception as exc:
                    if result.get("status") == "OK":
                        result.update(classify_spi_error(exc))
            result["duration_ms"] = (time.perf_counter() - started) * 1000.0
            self.on_done(result)
