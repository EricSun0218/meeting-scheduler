#!/usr/bin/env python3
"""Tests for generate_ics.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import generate_ics as ics


class TestParseDt(unittest.TestCase):
    def test_utc_z(self):
        dt = ics.parse_dt("2026-03-15T10:00:00Z")
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.minute, 0)

    def test_positive_offset(self):
        dt = ics.parse_dt("2026-03-15T10:00:00+08:00")
        # +08:00 → UTC = 02:00
        self.assertEqual(dt.hour, 2)

    def test_negative_offset(self):
        dt = ics.parse_dt("2026-03-15T10:00:00-05:00")
        # -05:00 → UTC = 15:00
        self.assertEqual(dt.hour, 15)

    def test_no_seconds(self):
        dt = ics.parse_dt("2026-03-15T10:00+08:00")
        self.assertEqual(dt.hour, 2)

    def test_no_offset_assumes_utc(self):
        dt = ics.parse_dt("2026-03-15T10:00:00")
        self.assertEqual(dt.hour, 10)


class TestFmtDt(unittest.TestCase):
    def test_format(self):
        from datetime import datetime, timezone
        dt = datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(ics.fmt_dt(dt), "20260315T103000Z")


class TestFold(unittest.TestCase):
    def test_short_line_unchanged(self):
        line = "SUMMARY:Short meeting"
        self.assertEqual(ics.fold(line), line)

    def test_long_line_folded(self):
        line = "DESCRIPTION:" + "A" * 100
        folded = ics.fold(line)
        parts = folded.split("\r\n ")
        self.assertGreater(len(parts), 1)
        # Each part should be <= 75 bytes (first) or <= 74 bytes (continuation)
        self.assertLessEqual(len(parts[0].encode("utf-8")), 75)
        for part in parts[1:]:
            self.assertLessEqual(len(part.encode("utf-8")), 74)

    def test_utf8_boundary_respected(self):
        # CJK characters are 3 bytes each in UTF-8
        line = "SUMMARY:" + "会" * 30  # ~90+ bytes
        folded = ics.fold(line)
        # Verify no broken UTF-8 by encoding/decoding round-trip
        for part in folded.split("\r\n "):
            part.encode("utf-8").decode("utf-8")  # Should not raise


class TestEscape(unittest.TestCase):
    def test_semicolon(self):
        self.assertEqual(ics.escape("a;b"), "a\\;b")

    def test_comma(self):
        self.assertEqual(ics.escape("a,b"), "a\\,b")

    def test_newline(self):
        self.assertEqual(ics.escape("a\nb"), "a\\nb")

    def test_backslash(self):
        self.assertEqual(ics.escape("a\\b"), "a\\\\b")


class TestIsUtf8Boundary(unittest.TestCase):
    def test_ascii(self):
        data = b"hello"
        self.assertTrue(ics._is_utf8_boundary(data, 0))
        self.assertTrue(ics._is_utf8_boundary(data, 3))

    def test_multibyte(self):
        data = "会".encode("utf-8")  # 3 bytes: 0xE4 0xBC 0x9A
        self.assertTrue(ics._is_utf8_boundary(data, 0))
        self.assertFalse(ics._is_utf8_boundary(data, 1))
        self.assertFalse(ics._is_utf8_boundary(data, 2))

    def test_past_end(self):
        self.assertTrue(ics._is_utf8_boundary(b"x", 5))


class TestMainOutput(unittest.TestCase):
    def test_generates_valid_ics(self):
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            outpath = f.name
        try:
            from unittest.mock import patch
            test_args = [
                "generate_ics.py",
                "--output", outpath,
                "--uid", "test-uid-123",
                "--summary", "Test Meeting",
                "--start", "2026-03-15T10:00:00+08:00",
                "--end", "2026-03-15T11:00:00+08:00",
                "--organizer", "org@example.com",
                "--attendees", "a@example.com,b@example.com",
                "--location", "https://meet.google.com/test",
                "--description", "Test agenda",
            ]
            with patch("sys.argv", test_args):
                ics.main()

            # Read in binary to verify CRLF line endings
            with open(outpath, "rb") as f:
                raw = f.read()
            self.assertIn(b"\r\n", raw)

            content = raw.decode("utf-8")
            self.assertIn("BEGIN:VCALENDAR", content)
            self.assertIn("END:VCALENDAR", content)
            self.assertIn("BEGIN:VEVENT", content)
            self.assertIn("END:VEVENT", content)
            self.assertIn("UID:test-uid-123", content)
            self.assertIn("METHOD:REQUEST", content)
            self.assertIn("STATUS:CONFIRMED", content)
            self.assertIn("SEQUENCE:0", content)
            self.assertIn("PRODID:-//meeting-scheduler//OpenClaw//EN", content)
            # Check attendees
            self.assertIn("mailto:a@example.com", content)
            self.assertIn("mailto:b@example.com", content)
        finally:
            os.unlink(outpath)

    def test_cancel_method(self):
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            outpath = f.name
        try:
            from unittest.mock import patch
            test_args = [
                "generate_ics.py",
                "--output", outpath,
                "--uid", "cancel-uid",
                "--summary", "Cancelled Meeting",
                "--start", "2026-03-15T10:00:00Z",
                "--end", "2026-03-15T11:00:00Z",
                "--organizer", "org@example.com",
                "--attendees", "a@example.com",
                "--cancel",
            ]
            with patch("sys.argv", test_args):
                ics.main()

            with open(outpath, "rb") as f:
                content = f.read().decode("utf-8")

            self.assertIn("METHOD:CANCEL", content)
            self.assertIn("STATUS:CANCELLED", content)
            self.assertIn("SEQUENCE:1", content)
        finally:
            os.unlink(outpath)

    def test_custom_sequence(self):
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            outpath = f.name
        try:
            from unittest.mock import patch
            test_args = [
                "generate_ics.py",
                "--output", outpath,
                "--uid", "seq-uid",
                "--summary", "Meeting",
                "--start", "2026-03-15T10:00:00Z",
                "--end", "2026-03-15T11:00:00Z",
                "--organizer", "org@example.com",
                "--attendees", "a@example.com",
                "--sequence", "5",
            ]
            with patch("sys.argv", test_args):
                ics.main()

            with open(outpath, "rb") as f:
                content = f.read().decode("utf-8")

            self.assertIn("SEQUENCE:5", content)
        finally:
            os.unlink(outpath)


if __name__ == "__main__":
    unittest.main()
