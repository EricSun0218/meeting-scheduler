#!/usr/bin/env python3
"""Tests for meeting_state.py"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meeting_state as ms


class TestMeetingState(unittest.TestCase):
    def setUp(self):
        self._orig_dir = ms.MEETINGS_DIR
        self._tmpdir = tempfile.mkdtemp()
        ms.MEETINGS_DIR = type(ms.MEETINGS_DIR)(self._tmpdir)

    def tearDown(self):
        ms.MEETINGS_DIR = self._orig_dir
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_create_meeting(self):
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            ms.create("Test Meeting")
        meeting_id = f.getvalue().strip()
        self.assertTrue(len(meeting_id) > 0)

        state = ms.load(meeting_id)
        self.assertEqual(state["subject"], "Test Meeting")
        self.assertEqual(state["status"], "gathering_info")
        # New schema fields
        self.assertIsNone(state["poll_task_id"])
        self.assertFalse(state["poll_busy"])
        self.assertIsNone(state["poll_busy_since"])
        # Old field should NOT exist
        self.assertNotIn("crontab_installed", state)

    def test_update_meeting(self):
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            ms.create("Test Meeting")
        meeting_id = f.getvalue().strip()

        f2 = io.StringIO()
        with redirect_stdout(f2):
            ms.update(meeting_id, '{"status": "negotiating", "poll_task_id": "mtg-poll-abc"}')
        updated = json.loads(f2.getvalue())
        self.assertEqual(updated["status"], "negotiating")
        self.assertEqual(updated["poll_task_id"], "mtg-poll-abc")
        # Original fields preserved
        self.assertEqual(updated["subject"], "Test Meeting")

    def test_update_participant(self):
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            ms.create("Test Meeting")
        meeting_id = f.getvalue().strip()

        f2 = io.StringIO()
        with redirect_stdout(f2):
            ms.update_participant(meeting_id, "alice@example.com",
                                  '{"status": "negotiating", "thread_id": "t123"}')
        participant = json.loads(f2.getvalue())
        self.assertEqual(participant["status"], "negotiating")
        self.assertEqual(participant["thread_id"], "t123")

        # Verify it's stored in the state
        state = ms.load(meeting_id)
        self.assertIn("alice@example.com", state["participants"])

    def test_list_meetings(self):
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            ms.create("Meeting A")
        id_a = f.getvalue().strip()

        f = io.StringIO()
        with redirect_stdout(f):
            ms.create("Meeting B")

        f = io.StringIO()
        with redirect_stdout(f):
            ms.update(id_a, '{"status": "negotiating"}')

        # List all
        f = io.StringIO()
        with redirect_stdout(f):
            ms.list_meetings()
        meetings = json.loads(f.getvalue())
        self.assertEqual(len(meetings), 2)

        # Filter by status
        f = io.StringIO()
        with redirect_stdout(f):
            ms.list_meetings("negotiating")
        meetings = json.loads(f.getvalue())
        self.assertEqual(len(meetings), 1)
        self.assertEqual(meetings[0]["status"], "negotiating")


if __name__ == "__main__":
    unittest.main()
