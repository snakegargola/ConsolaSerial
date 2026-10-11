from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SerialLogEntry:
    data: bytes
    direction: str
    timestamp: datetime

    def format(self, mode="ASCII", show_timestamp=True):
        parts = []
        if show_timestamp:
            parts.append(f"[{self.timestamp.strftime('%H:%M:%S.%f')[:-3]}]")
        parts.append(self.direction)
        if mode != "HEX":
            text = self.data.decode("utf-8", errors="replace").rstrip("\r\n")
            parts.append(f"ASCII: {text}")
        if mode != "ASCII":
            parts.append(f"HEX: {self.data.hex(' ').upper()}")
        return "  ".join(parts) + "\n"


class LogManager:
    """Keep original serial bytes so the entire log can change display format."""

    def __init__(self):
        self._entries: list[SerialLogEntry] = []

    def append(self, data: bytes, direction: str):
        entry = SerialLogEntry(bytes(data), direction, datetime.now())
        self._entries.append(entry)
        return entry

    def clear(self):
        self._entries.clear()

    def save(self, filepath: str, formatter=None) -> bool:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(
                    formatter(entry) if formatter else entry.format()
                    for entry in self._entries
                )
            return True
        except OSError:
            return False

    def __len__(self):
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)
