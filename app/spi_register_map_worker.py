"""Background batch reader for an SPI register map."""

import threading
import time

from .spi_bus import classify_spi_error


class SpiRegisterMapWorker(threading.Thread):
    def __init__(self, url, settings, profile, indexes, on_done):
        super().__init__(daemon=True); self.url = url; self.settings = settings
        self.profile = profile; self.indexes = tuple(indexes); self.on_done = on_done

    def run(self):
        started = time.perf_counter(); controller = None
        result = {"status": "OK", "values": [], "error": ""}
        try:
            from pyftdi.spi import SpiController
            controller = SpiController(cs_count=self.settings.cs_count, turbo=self.settings.turbo)
            controller.configure(self.url, frequency=self.settings.frequency,
                                 cs_count=self.settings.cs_count, turbo=self.settings.turbo)
            port = controller.get_port(self.settings.chip_select, freq=self.settings.frequency,
                                       mode=self.settings.mode)
            for index in self.indexes:
                register = self.profile.registers[index]
                if "R" not in register.access: continue
                command = self.profile.command(register) + b"\x00" * self.profile.dummy_bytes
                port.write(command, start=True, stop=False)
                data = bytes(port.exchange(b"\x00" * register.length, register.length,
                                           start=False, stop=True, duplex=True))
                result["values"].append({"index": index, "data": data})
            result["actual_frequency"] = int(round(float(port.frequency)))
        except Exception as exc: result.update(classify_spi_error(exc))
        finally:
            if controller:
                try: controller.close()
                except Exception: pass
            result["duration_ms"] = (time.perf_counter() - started) * 1000
            self.on_done(result)
