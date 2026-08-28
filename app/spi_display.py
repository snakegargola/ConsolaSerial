"""Validated profiles and pixel generation for common SPI displays."""

from __future__ import annotations

from dataclasses import dataclass
import json


DISPLAY_SCHEMA = "consola-serial-spi-display"
DISPLAY_VERSION = 1
PIXEL_FORMATS = frozenset({"rgb565", "mono_page"})


@dataclass(frozen=True)
class SpiDisplayInitStep:
    command: bytes
    data: bytes = b""
    delay_ms: int = 0

    def __post_init__(self):
        command = bytes(self.command)
        data = bytes(self.data)
        if not command:
            raise ValueError("A display initialization command cannot be empty.")
        if len(command) > 32 or len(data) > 4096:
            raise ValueError("Display initialization step is too large.")
        if not 0 <= int(self.delay_ms) <= 10_000:
            raise ValueError("Display initialization delay must be 0–10000 ms.")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "delay_ms", int(self.delay_ms))

    def to_dict(self):
        return {
            "command": self.command.hex(" ").upper(),
            "data": self.data.hex(" ").upper(),
            "delay_ms": self.delay_ms,
        }


@dataclass(frozen=True)
class SpiDisplayProfile:
    name: str
    controller: str
    width: int
    height: int
    pixel_format: str
    init_steps: tuple[SpiDisplayInitStep, ...]
    column_offset: int = 0
    row_offset: int = 0

    def __post_init__(self):
        if not str(self.name).strip() or not str(self.controller).strip():
            raise ValueError("Display name and controller cannot be empty.")
        if not 1 <= int(self.width) <= 2048 or not 1 <= int(self.height) <= 2048:
            raise ValueError("Display dimensions must be between 1 and 2048 pixels.")
        if self.pixel_format not in PIXEL_FORMATS:
            raise ValueError("Unsupported SPI display pixel format.")
        if not 0 <= int(self.column_offset) <= 65535:
            raise ValueError("Column offset must fit 16 bits.")
        if not 0 <= int(self.row_offset) <= 65535:
            raise ValueError("Row offset must fit 16 bits.")
        object.__setattr__(self, "init_steps", tuple(self.init_steps))

    def to_dict(self):
        return {
            "schema": DISPLAY_SCHEMA, "version": DISPLAY_VERSION,
            "name": self.name, "controller": self.controller,
            "width": self.width, "height": self.height,
            "pixel_format": self.pixel_format,
            "column_offset": self.column_offset, "row_offset": self.row_offset,
            "init_steps": [step.to_dict() for step in self.init_steps],
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, value):
        if value.get("schema") != DISPLAY_SCHEMA:
            raise ValueError("Not a Consola Serial SPI display profile.")
        if int(value.get("version", 0)) != DISPLAY_VERSION:
            raise ValueError("Unsupported SPI display profile version.")
        steps = tuple(SpiDisplayInitStep(
            bytes.fromhex(item.get("command", "")),
            bytes.fromhex(item.get("data", "")),
            int(item.get("delay_ms", 0)),
        ) for item in value.get("init_steps", []))
        return cls(
            str(value.get("name", "")), str(value.get("controller", "")),
            int(value.get("width", 0)), int(value.get("height", 0)),
            str(value.get("pixel_format", "")), steps,
            int(value.get("column_offset", 0)), int(value.get("row_offset", 0)),
        )

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))


def parse_init_script(text: str) -> tuple[SpiDisplayInitStep, ...]:
    """Parse ``COMMAND ; DATA ; DELAY_MS`` lines into safe initialization steps."""
    steps = []
    for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(";")]
        if len(fields) > 3:
            raise ValueError(f"Initialization line {line_number} has too many fields.")
        fields += [""] * (3 - len(fields))
        try:
            command = bytes.fromhex(fields[0])
            data = bytes.fromhex(fields[1]) if fields[1] else b""
            delay = int(fields[2] or 0)
            steps.append(SpiDisplayInitStep(command, data, delay))
        except ValueError as exc:
            raise ValueError(f"Invalid initialization line {line_number}: {exc}") from exc
    return tuple(steps)


def format_init_script(steps) -> str:
    return "\n".join(
        f"{step.command.hex(' ').upper()} ; {step.data.hex(' ').upper()} ; {step.delay_ms}"
        for step in steps
    )


def builtin_display_profiles():
    """Return conservative editable presets for widespread display controllers."""
    return (
        SpiDisplayProfile("ST7789 240×240", "ST7789", 240, 240, "rgb565", (
            SpiDisplayInitStep(b"\x01", delay_ms=150),
            SpiDisplayInitStep(b"\x11", delay_ms=120),
            SpiDisplayInitStep(b"\x3A", b"\x55", 10),
            SpiDisplayInitStep(b"\x36", b"\x00"),
            SpiDisplayInitStep(b"\x21", delay_ms=10),
            SpiDisplayInitStep(b"\x29", delay_ms=20),
        )),
        SpiDisplayProfile("ST7735 128×160", "ST7735", 128, 160, "rgb565", (
            SpiDisplayInitStep(b"\x01", delay_ms=150),
            SpiDisplayInitStep(b"\x11", delay_ms=120),
            SpiDisplayInitStep(b"\x3A", b"\x05", 10),
            SpiDisplayInitStep(b"\x36", b"\x00"),
            SpiDisplayInitStep(b"\x29", delay_ms=20),
        )),
        SpiDisplayProfile("ILI9341 320×240", "ILI9341", 320, 240, "rgb565", (
            SpiDisplayInitStep(b"\x01", delay_ms=150),
            SpiDisplayInitStep(b"\x11", delay_ms=120),
            SpiDisplayInitStep(b"\x3A", b"\x55"),
            SpiDisplayInitStep(b"\x36", b"\x48"),
            SpiDisplayInitStep(b"\x29", delay_ms=20),
        )),
        SpiDisplayProfile("Custom RGB565", "Custom", 240, 240, "rgb565", ()),
    )


def rgb888_to_rgb565(red, green, blue):
    return ((int(red) & 0xF8) << 8) | ((int(green) & 0xFC) << 3) | (int(blue) >> 3)


def solid_rgb565(width, height, color):
    word = int(color).to_bytes(2, "big")
    return word * (int(width) * int(height))


def color_bars_rgb565(width, height):
    colors = (
        0xFFFF, 0xFFE0, 0x07FF, 0x07E0,
        0xF81F, 0xF800, 0x001F, 0x0000,
    )
    output = bytearray()
    for _row in range(int(height)):
        for column in range(int(width)):
            color = colors[min(7, column * 8 // int(width))]
            output.extend(color.to_bytes(2, "big"))
    return bytes(output)


def checkerboard_rgb565(width, height, block=16):
    output = bytearray()
    for row in range(int(height)):
        for column in range(int(width)):
            color = 0xFFFF if ((row // block) ^ (column // block)) & 1 else 0x0000
            output.extend(color.to_bytes(2, "big"))
    return bytes(output)


def load_image_rgb565(path, width, height):
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required to convert display images.") from exc
    image = Image.open(path).convert("RGB")
    image = ImageOps.fit(image, (int(width), int(height)), Image.Resampling.LANCZOS)
    output = bytearray()
    for red, green, blue in image.getdata():
        output.extend(rgb888_to_rgb565(red, green, blue).to_bytes(2, "big"))
    return bytes(output)
