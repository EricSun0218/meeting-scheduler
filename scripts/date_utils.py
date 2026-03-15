#!/usr/bin/env python3
"""Shared date/time parsing utilities for meeting-scheduler scripts."""
import json
import os
import re
import tempfile
from datetime import datetime, timezone


def parse_iso(s):
    """Parse an ISO 8601 datetime string to an aware datetime, or None on failure.
    Handles formats with/without seconds, Z suffix, and ±HH:MM offsets.
    """
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        # Add :00 seconds if missing (e.g. 2026-03-15T10:00+08:00) for Python < 3.11
        s = re.sub(r'T(\d{2}:\d{2})([+-])', r'T\1:00\2', s)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def parse_date_flexible(s):
    """Try multiple date formats; return aware datetime or None."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M%z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def atomic_write_json(path, data):
    """Write JSON to a file atomically via write-to-temp + rename."""
    parent = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def extract_from_address(from_field):
    """Extract email address from various himalaya/gog from-field formats."""
    if isinstance(from_field, dict):
        return from_field.get("addr", "") or from_field.get("address", "")
    if isinstance(from_field, list) and from_field:
        first = from_field[0]
        if isinstance(first, dict):
            return first.get("addr", "") or first.get("address", "")
        return str(first)
    return str(from_field) if from_field else ""
