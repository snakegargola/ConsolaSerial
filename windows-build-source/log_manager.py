import os


class LogManager:
    """Stores monitor lines in memory and can export them to a file."""

    def __init__(self):
        self._lines: list[str] = []

    def append(self, line: str):
        self._lines.append(line)

    def clear(self):
        self._lines.clear()

    def save(self, filepath: str) -> bool:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(self._lines)
            return True
        except OSError:
            return False

    def __len__(self):
        return len(self._lines)
