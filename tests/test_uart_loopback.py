"""Tests for deterministic UART loopback frames and stream matching."""

import unittest

from app.uart_loopback import LoopbackStreamMatcher, build_loopback_frame


class UartLoopbackTests(unittest.TestCase):
    def test_frame_is_deterministic_and_sequence_specific(self):
        first = build_loopback_frame(7, 64)
        self.assertEqual(first, build_loopback_frame(7, 64))
        self.assertNotEqual(first, build_loopback_frame(8, 64))
        self.assertEqual(len(first), 64 + 12)

    def test_frame_arguments_are_bounded(self):
        for sequence, size in ((-1, 1), (65536, 1), (0, 0), (0, 4097)):
            with self.subTest(sequence=sequence, size=size), self.assertRaises(ValueError):
                build_loopback_frame(sequence, size)

    def test_matcher_accepts_an_echo_split_across_reads(self):
        frame = build_loopback_frame(1, 32)
        matcher = LoopbackStreamMatcher()
        matcher.expect(frame)

        self.assertFalse(matcher.feed(frame[:9]))
        self.assertTrue(matcher.feed(frame[9:]))
        self.assertEqual(matcher.received_bytes, len(frame))
        self.assertEqual(matcher.unexpected_bytes, 0)

    def test_matcher_counts_noise_and_recovers_alignment(self):
        frame = build_loopback_frame(2, 16)
        matcher = LoopbackStreamMatcher()
        matcher.expect(frame)

        self.assertFalse(matcher.feed(b"noise" + frame[:3]))
        self.assertTrue(matcher.feed(frame[3:]))
        self.assertEqual(matcher.unexpected_bytes, 5)

    def test_abandon_clears_a_corrupted_partial_frame(self):
        frame = build_loopback_frame(3, 16)
        matcher = LoopbackStreamMatcher()
        matcher.expect(frame)
        matcher.feed(frame[:5])
        matcher.abandon()

        self.assertFalse(matcher.waiting)
        self.assertEqual(matcher.unexpected_bytes, 5)


if __name__ == "__main__":
    unittest.main()
