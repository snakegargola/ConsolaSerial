"""Hardware-neutral models and validation for FTDI GPIO operations."""

from __future__ import annotations

from dataclasses import dataclass


GPIO_PORT_WIDTH = 8


def gpio_width_for_interface(bridge, interface) -> int:
    """Return the physical GPIO width exposed by a bridge interface."""
    model = str(getattr(bridge, "model", "")).upper()
    has_mpsse = bool(getattr(interface, "has_mpsse", False))
    if has_mpsse and ("FT232H" in model or "FT2232H" in model):
        return 16
    return GPIO_PORT_WIDTH


def mask_for_width(width: int) -> int:
    """Return a bit mask for a validated GPIO port width."""
    width = int(width)
    if not 1 <= width <= 16:
        raise ValueError("GPIO width must be between 1 and 16 pins.")
    return (1 << width) - 1


def spi_gpio_mask(cs_count: int, width: int = GPIO_PORT_WIDTH) -> int:
    """Return pins left available after SPI signals and chip selects."""
    cs_count = int(cs_count)
    if not 1 <= cs_count <= 5:
        raise ValueError("SPI chip-select count must be between 1 and 5.")
    all_pins = mask_for_width(width)
    reserved_count = 3 + cs_count  # SCLK, MOSI, MISO, then /CS lines
    return all_pins & ~((1 << reserved_count) - 1)


@dataclass(frozen=True)
class GpioState:
    """Desired GPIO direction/output state for one atomic hardware access."""

    available_mask: int
    direction: int = 0
    output: int = 0
    width: int = GPIO_PORT_WIDTH

    def __post_init__(self):
        valid = mask_for_width(self.width)
        available = int(self.available_mask)
        direction = int(self.direction)
        output = int(self.output)
        if available & ~valid:
            raise ValueError("Available GPIO mask exceeds the port width.")
        if direction & ~available:
            raise ValueError("GPIO direction includes reserved pins.")
        if output & ~direction:
            raise ValueError("GPIO output values may only target output pins.")
        object.__setattr__(self, "available_mask", available)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "output", output)

    def result(self, sampled: int) -> dict:
        """Build the stable result consumed by the UI and tests."""
        return {
            "available_mask": self.available_mask,
            "direction": self.direction,
            "output": self.output,
            "sampled": int(sampled) & self.available_mask,
            "width": self.width,
        }
