#!/usr/bin/env python3
"""Tests for date_utils.py shared utilities."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import date_utils


class TestParseIso(unittest.TestCase):
    def test_with_z(self):
        dt = date_utils.parse_iso("2026-03-15T10:00:00Z")
        self.assertIsNotNone(dt)
        self.assertTrue(dt.tzinfo is not None)

    def test_with_offset(self):
        dt = date_utils.parse_iso("2026-03-15T10:00:00+08:00")
        self.assertIsNotNone(dt)

    def test_no_seconds(self):
        dt = date_utils.parse_iso("2026-03-15T10:00+08:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.second, 0)

    def test_empty(self):
        self.assertIsNone(date_utils.parse_iso(""))

    def test_none(self):
        self.assertIsNone(date_utils.parse_iso(None))

    def test_invalid(self):
        self.assertIsNone(date_utils.parse_iso("not-a-date"))


class TestParseDateFlexible(unittest.TestCase):
    def test_rfc_date(self):
        dt = date_utils.parse_date_flexible("Mon, 15 Mar 2026 10:00:00 +0800")
        self.assertIsNotNone(dt)

    def test_plain_datetime(self):
        dt = date_utils.parse_date_flexible("2026-03-15 10:00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_invalid(self):
        self.assertIsNone(date_utils.parse_date_flexible("garbage"))


class TestAtomicWriteJson(unittest.TestCase):
    def test_writes_valid_json(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            data = {"key": "value", "number": 42}
            date_utils.atomic_write_json(path, data)
            with open(path) as f:
                loaded = json.load(f)
            self.assertEqual(loaded, data)
        finally:
            os.unlink(path)

    def test_overwrites_existing(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            date_utils.atomic_write_json(path, {"old": True})
            date_utils.atomic_write_json(path, {"new": True})
            with open(path) as f:
                loaded = json.load(f)
            self.assertEqual(loaded, {"new": True})
        finally:
            os.unlink(path)


class TestExtractFromAddress(unittest.TestCase):
    def test_dict_with_addr(self):
        self.assertEqual(date_utils.extract_from_address({"addr": "a@b.com"}), "a@b.com")

    def test_dict_with_address(self):
        self.assertEqual(date_utils.extract_from_address({"address": "a@b.com"}), "a@b.com")

    def test_list_of_dicts(self):
        self.assertEqual(date_utils.extract_from_address([{"addr": "a@b.com"}]), "a@b.com")

    def test_string(self):
        self.assertEqual(date_utils.extract_from_address("a@b.com"), "a@b.com")

    def test_empty(self):
        self.assertEqual(date_utils.extract_from_address(""), "")

    def test_none(self):
        self.assertEqual(date_utils.extract_from_address(None), "")


if __name__ == "__main__":
    unittest.main()
