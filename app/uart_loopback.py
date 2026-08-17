"""Deterministic UART loopback frames and streaming echo verification."""

from __future__ import annotations

import zlib


LOOPBACK_MAGIC = b"\xA5\x5A\xC3\x3C"


def build_loopback_frame(sequence: int, payload_size: int) -> bytes:
    """Build a binary frame whose exact echo detects dropped or changed bits."""
    sequence = int(sequence)
    payload_size = int(payload_size)
    if not 0 <= sequence <= 0xFFFF:
        raise ValueError("Loopback sequence must fit in 16 bits.")
    if not 1 <= payload_size <= 4096:
        raise ValueError("Loopback payload size must be between 1 and 4096 bytes.")

    header = (
        LOOPBACK_MAGIC
        + sequence.to_bytes(2, "big")
        + payload_size.to_bytes(2, "big")
    )
    payload = bytes(
        (sequence * 37 + index * 17 + (index // 8) * 29) & 0xFF
        for index in range(payload_size)
    )
    checksum = zlib.crc32(header + payload).to_bytes(4, "big")
    return header + payload + checksum


class LoopbackStreamMatcher:
    """Find one expected frame in arbitrarily chunked raw UART input.

    Bytes before a valid echo are counted as unexpected. Only the suffix that
    could still be the beginning of the expected frame is retained between
    reads, keeping memory bounded even on a noisy port.
    """

    def __init__(self):
        self._expected = b""
        self._buffer = bytearray()
        self.received_bytes = 0
        self.unexpected_bytes = 0

    @property
    def waiting(self) -> bool:
        return bool(self._expected)

    def reset(self):
        self._expected = b""
        self._buffer.clear()
        self.received_bytes = 0
        self.unexpected_bytes = 0

    def expect(self, frame: bytes):
        frame = bytes(frame)
        if not frame:
            raise ValueError("Expected loopback frame cannot be empty.")
        if self._expected:
            raise RuntimeError("A loopback frame is already pending.")
        if self._buffer:
            self.unexpected_bytes += len(self._buffer)
            self._buffer.clear()
        self._expected = frame

    def abandon(self):
        """Discard a timed-out partial echo before starting the next frame."""
        self.unexpected_bytes += len(self._buffer)
        self._buffer.clear()
        self._expected = b""

    def feed(self, data: bytes) -> bool:
        """Consume raw RX bytes and return True when the expected echo arrives."""
        data = bytes(data)
        self.received_bytes += len(data)
        if not data:
            return False
        if not self._expected:
            self.unexpected_bytes += len(data)
            return False

        self._buffer.extend(data)
        match_at = self._buffer.find(self._expected)
        if match_at >= 0:
            self.unexpected_bytes += match_at
            del self._buffer[:match_at + len(self._expected)]
            self._expected = b""
            return True

        overlap = self._prefix_overlap()
        discard = len(self._buffer) - overlap
        if discard:
            self.unexpected_bytes += discard
            del self._buffer[:discard]
        return False

    def _prefix_overlap(self) -> int:
        limit = min(len(self._buffer), len(self._expected) - 1)
        for size in range(limit, 0, -1):
            if self._buffer[-size:] == self._expected[:size]:
                return size
        return 0
