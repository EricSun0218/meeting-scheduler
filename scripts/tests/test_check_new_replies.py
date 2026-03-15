#!/usr/bin/env python3
"""Tests for check_new_replies.py"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Add parent dir to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_new_replies as cnr


class TestParseIso(unittest.TestCase):
    def test_iso_with_z(self):
        dt = cnr.parse_iso("2026-03-15T10:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo is not None, True)

    def test_iso_with_offset(self):
        dt = cnr.parse_iso("2026-03-15T10:00:00+08:00")
        self.assertIsNotNone(dt)

    def test_empty_string(self):
        self.assertIsNone(cnr.parse_iso(""))

    def test_none(self):
        self.assertIsNone(cnr.parse_iso(None))

    def test_invalid(self):
        self.assertIsNone(cnr.parse_iso("not-a-date"))

    def test_no_seconds_format(self):
        """parse_iso should handle formats without seconds (e.g. 2026-03-15T10:00+08:00)."""
        dt = cnr.parse_iso("2026-03-15T10:00+08:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.minute, 0)
        self.assertEqual(dt.second, 0)

    def test_no_seconds_with_z(self):
        dt = cnr.parse_iso("2026-03-15T10:00Z")
        # Z → +00:00, then T10:00+00:00 → T10:00:00+00:00
        self.assertIsNotNone(dt)


class TestParseDateFlexible(unittest.TestCase):
    def test_rfc_date(self):
        dt = cnr.parse_date_flexible("Mon, 15 Mar 2026 10:00:00 +0800")
        self.assertIsNotNone(dt)

    def test_plain_datetime(self):
        dt = cnr.parse_date_flexible("2026-03-15 10:00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)  # assumed UTC when no tz

    def test_invalid(self):
        self.assertIsNone(cnr.parse_date_flexible("garbage"))


class TestCheckThreadGog(unittest.TestCase):
    @patch("check_new_replies.run")
    def test_new_reply_found(self, mock_run):
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "2026-03-15 12:00:00", "snippet": "Looks good"},
            ]
        }), "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "organizer@example.com")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["from"], "alice@example.com")
        # Verify gog gmail thread get command (now called with list args)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        self.assertEqual(cmd_args[:4], ["gog", "gmail", "thread", "get"])

    @patch("check_new_replies.run")
    def test_no_new_reply(self, mock_run):
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "2026-03-15 09:00:00", "subject": "Re: Meeting"},
            ]
        }), "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "organizer@example.com")
        self.assertEqual(len(result), 0)

    @patch("check_new_replies.run")
    def test_skip_organizer_message(self, mock_run):
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "organizer@example.com", "date": "2026-03-15 12:00:00", "subject": "Follow up"},
            ]
        }), "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "organizer@example.com")
        self.assertEqual(len(result), 0)

    @patch("check_new_replies.run")
    def test_command_fails(self, mock_run):
        mock_run.return_value = (False, "", "auth error")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(result, [])

    @patch("check_new_replies.run")
    def test_invalid_json(self, mock_run):
        mock_run.return_value = (True, "not json at all", "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(result, [])

    @patch("check_new_replies.run")
    def test_date_parse_failure(self, mock_run):
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "unparseable-date", "subject": "Re: Meeting"},
            ]
        }), "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(len(result), 0)

    @patch("check_new_replies.run")
    def test_processed_ids_skipped(self, mock_run):
        """Messages with IDs in processed_ids should be skipped."""
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "2026-03-15 12:00:00", "snippet": "Reply 1"},
                {"id": "msg2", "from": "alice@example.com", "date": "2026-03-15 13:00:00", "snippet": "Reply 2"},
            ]
        }), "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "org@example.com",
                                       processed_ids=["msg1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["message_id"], "msg2")

    @patch("check_new_replies.run")
    def test_snippet_priority(self, mock_run):
        """snippet field should be preferred over subject."""
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "2026-03-15 12:00:00",
                 "snippet": "I can do slot C", "subject": "Re: Meeting"},
            ]
        }), "")
        result = cnr.check_thread_gog("thread123", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(result[0]["snippet"], "I can do slot C")


class TestCheckThreadHimalaya(unittest.TestCase):
    @patch("check_new_replies.run")
    def test_new_reply_found(self, mock_run):
        mock_run.return_value = (True, json.dumps([
            {"id": "1", "from": {"addr": "alice@example.com"}, "subject": "Re: Meeting", "date": "2026-03-15 12:00:00"},
        ]), "")
        result = cnr.check_thread_himalaya("alice@example.com", "Meeting", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(len(result), 1)

    @patch("check_new_replies.run")
    def test_subject_mismatch(self, mock_run):
        mock_run.return_value = (True, json.dumps([
            {"id": "1", "from": {"addr": "alice@example.com"}, "subject": "Other topic", "date": "2026-03-15 12:00:00"},
        ]), "")
        result = cnr.check_thread_himalaya("alice@example.com", "Meeting", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(len(result), 0)

    @patch("check_new_replies.run")
    def test_command_fails(self, mock_run):
        mock_run.return_value = (False, "", "connection refused")
        result = cnr.check_thread_himalaya("alice@example.com", "Meeting", "2026-03-15T10:00:00Z", "org@example.com")
        self.assertEqual(result, [])

    @patch("check_new_replies.run")
    def test_processed_ids_skipped(self, mock_run):
        """Envelopes with IDs in processed_ids should be skipped."""
        mock_run.return_value = (True, json.dumps([
            {"id": "1", "from": {"addr": "alice@example.com"}, "subject": "Re: Meeting", "date": "2026-03-15 12:00:00"},
            {"id": "2", "from": {"addr": "alice@example.com"}, "subject": "Re: Meeting", "date": "2026-03-15 13:00:00"},
        ]), "")
        result = cnr.check_thread_himalaya("alice@example.com", "Meeting", "2026-03-15T10:00:00Z", "org@example.com",
                                            processed_ids=["1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["message_id"], "2")


class TestGetFutureSlots(unittest.TestCase):
    def test_filters_past(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        slots = ["2026-03-15T10:00:00Z", "2026-03-15T14:00:00Z", "2026-03-16T10:00:00Z"]
        result = cnr.get_future_slots(slots, now)
        self.assertEqual(len(result), 2)
        self.assertIn("2026-03-15T14:00:00Z", result)
        self.assertIn("2026-03-16T10:00:00Z", result)

    def test_keeps_future(self):
        now = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)
        slots = ["2026-03-15T10:00:00Z"]
        result = cnr.get_future_slots(slots, now)
        self.assertEqual(len(result), 1)

    def test_all_expired(self):
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        slots = ["2026-03-15T10:00:00Z", "2026-03-16T10:00:00Z"]
        result = cnr.get_future_slots(slots, now)
        self.assertEqual(len(result), 0)

    def test_empty_input(self):
        now = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        result = cnr.get_future_slots([], now)
        self.assertEqual(result, [])


class TestReminderDue(unittest.TestCase):
    def test_high_urgency_24h_elapsed(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        future_slots = ["2026-03-20T10:00:00Z"]  # >72h away
        data = {"status": "waiting_reply", "last_sent_at": "2026-03-14T10:00:00Z"}  # 26h ago
        self.assertTrue(cnr.reminder_due(data, future_slots, now))

    def test_high_urgency_not_enough_elapsed(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        future_slots = ["2026-03-20T10:00:00Z"]
        data = {"status": "waiting_reply", "last_sent_at": "2026-03-15T00:00:00Z"}  # 12h ago
        self.assertFalse(cnr.reminder_due(data, future_slots, now))

    def test_medium_urgency(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        future_slots = ["2026-03-17T00:00:00Z"]  # 36h away
        data = {"status": "waiting_reply", "last_sent_at": "2026-03-14T22:00:00Z"}  # 14h ago
        self.assertTrue(cnr.reminder_due(data, future_slots, now))

    def test_less_than_6h(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        future_slots = ["2026-03-15T15:00:00Z"]  # 3h away
        data = {"status": "waiting_reply", "last_sent_at": "2026-03-14T00:00:00Z"}  # 36h ago
        self.assertFalse(cnr.reminder_due(data, future_slots, now))

    def test_not_waiting_reply(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        future_slots = ["2026-03-20T10:00:00Z"]
        data = {"status": "negotiating", "last_sent_at": "2026-03-14T10:00:00Z"}
        self.assertFalse(cnr.reminder_due(data, future_slots, now))

    def test_no_future_slots(self):
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        data = {"status": "waiting_reply", "last_sent_at": "2026-03-14T10:00:00Z"}
        self.assertFalse(cnr.reminder_due(data, [], now))


class TestOutputResult(unittest.TestCase):
    def test_output_format(self):
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            cnr.output_result("abc123", "process", "new_replies",
                              new_replies=[{"email": "a@b.com"}], reminders_due=["c@d.com"],
                              pending_replies=["x@y.com"])
        output = f.getvalue()
        self.assertIn("---JSON---", output)
        lines = output.strip().split("\n")
        json_line = lines[-1]
        data = json.loads(json_line)
        self.assertEqual(data["action"], "process")
        self.assertEqual(data["meeting_id"], "abc123")
        self.assertEqual(data["reason"], "new_replies")
        self.assertEqual(len(data["new_replies"]), 1)
        self.assertEqual(len(data["reminders_due"]), 1)
        self.assertEqual(data["pending_replies"], ["x@y.com"])
        self.assertFalse(data["all_pending_replied"])

    def test_output_all_pending_replied_true(self):
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            cnr.output_result("abc123", "process", "new_replies",
                              pending_replies=[])
        output = f.getvalue()
        json_str = output.split("---JSON---\n", 1)[1].strip()
        data = json.loads(json_str)
        self.assertEqual(data["pending_replies"], [])
        self.assertTrue(data["all_pending_replied"])

    def test_output_pending_replies_default_empty(self):
        """When pending_replies is not provided, defaults to empty list."""
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            cnr.output_result("abc123", "none", "no_new_replies")
        output = f.getvalue()
        json_str = output.split("---JSON---\n", 1)[1].strip()
        data = json.loads(json_str)
        self.assertEqual(data["pending_replies"], [])
        self.assertTrue(data["all_pending_replied"])

    def test_process_does_not_change_poll_busy(self):
        """When action is 'process', output_result should NOT touch poll_busy
        (it's already set early in main(), before email checks)."""
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump({"id": "abc", "status": "negotiating", "poll_busy": True,
                        "poll_busy_since": "2026-03-15T10:00:00+00:00"}, tf)
            tf_path = tf.name
        try:
            f = io.StringIO()
            with redirect_stdout(f):
                cnr.output_result("abc", "process", "new_replies", state_path=tf_path)
            with open(tf_path) as fh:
                state = json.load(fh)
            # poll_busy stays true — agent is responsible for clearing it
            self.assertTrue(state["poll_busy"])
        finally:
            os.unlink(tf_path)

    def test_none_action_clears_poll_busy(self):
        """When action is 'none' with state_path, poll_busy should be cleared
        (lock was acquired early but no work needed)."""
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump({"id": "abc", "status": "negotiating", "poll_busy": True,
                        "poll_busy_since": "2026-03-15T10:00:00+00:00"}, tf)
            tf_path = tf.name
        try:
            f = io.StringIO()
            with redirect_stdout(f):
                cnr.output_result("abc", "none", "no_new_replies", state_path=tf_path)
            with open(tf_path) as fh:
                state = json.load(fh)
            self.assertFalse(state["poll_busy"])
            self.assertIsNone(state.get("poll_busy_since"))
        finally:
            os.unlink(tf_path)

    def test_set_poll_busy_function(self):
        """_set_poll_busy should set poll_busy=true and poll_busy_since."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump({"id": "abc", "poll_busy": False}, tf)
            tf_path = tf.name
        try:
            cnr._set_poll_busy(tf_path)
            with open(tf_path) as fh:
                state = json.load(fh)
            self.assertTrue(state["poll_busy"])
            self.assertIsNotNone(state.get("poll_busy_since"))
        finally:
            os.unlink(tf_path)


def _make_state(meeting_id="test123", status="negotiating", proposed_slots=None,
                participants=None, poll_busy=False, poll_busy_since=None,
                pending_replies=None, **kwargs):
    """Helper to create a state dict and write it to a temp file."""
    state = {
        "id": meeting_id,
        "status": status,
        "organizer": "org@example.com",
        "email_tool": "gog",
        "subject": "Test Meeting",
        "proposed_slots": proposed_slots or [],
        "pending_replies": pending_replies if pending_replies is not None else [],
        "participants": participants or {},
        "poll_task_id": "mtg-poll-test123",
        "poll_busy": poll_busy,
        "poll_busy_since": poll_busy_since,
    }
    state.update(kwargs)
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    return path


def _make_participant(status="waiting_reply", thread_id="t1", last_sent_at="2026-03-15T10:00:00Z",
                      processed_message_ids=None, **kwargs):
    """Helper to create a participant dict with defaults."""
    p = {
        "status": status,
        "thread_id": thread_id,
        "last_sent_at": last_sent_at,
        "processed_message_ids": processed_message_ids or [],
    }
    p.update(kwargs)
    return p


def _run_main(state_path):
    """Run main() with the given state file and capture stdout."""
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    test_args = ["check_new_replies.py", "--state", state_path]
    with patch("sys.argv", test_args), redirect_stdout(f):
        try:
            cnr.main()
        except SystemExit:
            pass
    output = f.getvalue()
    # Extract JSON from after ---JSON---
    if "---JSON---" in output:
        json_str = output.split("---JSON---\n", 1)[1].strip()
        return json.loads(json_str), output
    return None, output


class TestMainIntegration(unittest.TestCase):
    def test_not_negotiating(self):
        path = _make_state(status="confirmed")
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "not_negotiating")
        finally:
            os.unlink(path)

    def test_all_slots_expired(self):
        path = _make_state(
            proposed_slots=["2020-01-01T10:00:00Z", "2020-01-02T10:00:00Z"],
            participants={"alice@example.com": _make_participant(
                last_sent_at="2020-01-01T08:00:00Z"
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "all_slots_expired")
        finally:
            os.unlink(path)

    def test_all_slots_expired_range_ended(self):
        """When all slots expired AND time_range_end has passed, reason should be all_slots_expired_range_ended."""
        path = _make_state(
            proposed_slots=["2020-01-01T10:00:00Z", "2020-01-02T10:00:00Z"],
            time_range_end="2020-01-03T18:00:00Z",
            participants={"alice@example.com": _make_participant(
                last_sent_at="2020-01-01T08:00:00Z"
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "all_slots_expired_range_ended")
        finally:
            os.unlink(path)

    def test_all_slots_expired_range_not_ended(self):
        """When all slots expired but time_range_end is still in the future, reason should be all_slots_expired."""
        path = _make_state(
            proposed_slots=["2020-01-01T10:00:00Z", "2020-01-02T10:00:00Z"],
            time_range_end="2099-12-31T18:00:00Z",
            participants={"alice@example.com": _make_participant(
                last_sent_at="2020-01-01T08:00:00Z"
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "all_slots_expired")
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_new_replies(self, mock_run):
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "2026-03-15 12:00:00", "snippet": "C E"},
            ]
        }), "")
        path = _make_state(
            proposed_slots=["2026-03-20T10:00:00Z"],
            participants={"alice@example.com": _make_participant()},
            pending_replies=["alice@example.com", "bob@example.com"]
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "new_replies")
            self.assertEqual(len(result["new_replies"]), 1)
            # alice replied → removed from pending, bob still pending
            self.assertEqual(result["pending_replies"], ["bob@example.com"])
            self.assertFalse(result["all_pending_replied"])
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_new_replies_all_pending_replied(self, mock_run):
        """When the last pending participant replies, all_pending_replied should be true."""
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg1", "from": "alice@example.com", "date": "2026-03-15 12:00:00", "snippet": "OK"},
            ]
        }), "")
        path = _make_state(
            proposed_slots=["2026-03-20T10:00:00Z"],
            participants={"alice@example.com": _make_participant()},
            pending_replies=["alice@example.com"]
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["pending_replies"], [])
            self.assertTrue(result["all_pending_replied"])
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_no_pending_replies_field_defaults_empty(self, mock_run):
        """State without pending_replies field should default to empty list."""
        mock_run.return_value = (True, json.dumps({"messages": []}), "")
        path = _make_state(
            proposed_slots=["2026-03-25T10:00:00Z"],
            participants={"alice@example.com": _make_participant(
                last_sent_at="2026-03-15T11:00:00Z"
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["pending_replies"], [])
            self.assertTrue(result["all_pending_replied"])
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_new_replies_priority_over_expired_slots(self, mock_run):
        """New replies should take priority even when all slots are expired."""
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "msg_new", "from": "alice@example.com", "date": "2026-03-15 12:00:00", "snippet": "How about Friday?"},
            ]
        }), "")
        path = _make_state(
            proposed_slots=["2020-01-01T10:00:00Z"],  # all expired
            participants={"alice@example.com": _make_participant(
                last_sent_at="2026-03-15T10:00:00Z"
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "new_replies")
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_processed_message_ids_filtering(self, mock_run):
        """Messages already in processed_message_ids should not trigger new_replies."""
        mock_run.return_value = (True, json.dumps({
            "messages": [
                {"id": "already_seen", "from": "alice@example.com", "date": "2026-03-15 12:00:00", "snippet": "Old reply"},
            ]
        }), "")
        path = _make_state(
            proposed_slots=["2026-03-20T10:00:00Z"],
            participants={"alice@example.com": _make_participant(
                processed_message_ids=["already_seen"]
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "no_new_replies")
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_reminders_due(self, mock_run):
        mock_run.return_value = (True, json.dumps({"messages": []}), "")
        # Slot >72h away, last_sent >24h ago
        path = _make_state(
            proposed_slots=["2026-03-25T10:00:00Z"],
            participants={"alice@example.com": _make_participant(
                last_sent_at="2026-03-13T10:00:00Z"
            )}
        )
        try:
            with patch("check_new_replies.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
                mock_dt.strptime = datetime.strptime
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "reminders_due")
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_no_activity(self, mock_run):
        mock_run.return_value = (True, json.dumps({"messages": []}), "")
        # Last sent 1h ago, slot >72h away → not due yet
        path = _make_state(
            proposed_slots=["2026-03-25T10:00:00Z"],
            participants={"alice@example.com": _make_participant(
                last_sent_at="2026-03-15T11:00:00Z"
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "no_new_replies")
        finally:
            os.unlink(path)

    def test_poll_busy(self):
        busy_since = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        path = _make_state(poll_busy=True, poll_busy_since=busy_since)
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "agent_busy")
        finally:
            os.unlink(path)

    def test_poll_busy_stale(self):
        busy_since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        path = _make_state(
            poll_busy=True, poll_busy_since=busy_since,
            proposed_slots=["2026-03-25T10:00:00Z"],
            participants={}
        )
        try:
            result, output = _run_main(path)
            # Stale busy → proceeds normally, no participants → no_new_replies
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "no_new_replies")
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_urgency_escalation(self, mock_run):
        """When nearest slot is < 6h away and participants are still waiting, trigger urgency_escalation."""
        mock_run.return_value = (True, json.dumps({"messages": []}), "")
        # Slot 3h from now, participant still waiting, last sent 1h ago (no reminder due since < 6h)
        now = datetime.now(timezone.utc)
        slot_3h = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        last_sent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        path = _make_state(
            proposed_slots=[slot_3h],
            participants={"alice@example.com": _make_participant(
                last_sent_at=last_sent
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "process")
            self.assertEqual(result["reason"], "urgency_escalation")
            self.assertIn("alice@example.com", result["reminders_due"])
        finally:
            os.unlink(path)

    @patch("check_new_replies.run")
    def test_no_urgency_escalation_if_replied(self, mock_run):
        """Urgency escalation should not trigger for participants who already replied (status=negotiating)."""
        mock_run.return_value = (True, json.dumps({"messages": []}), "")
        now = datetime.now(timezone.utc)
        slot_3h = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        last_sent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        path = _make_state(
            proposed_slots=[slot_3h],
            participants={"alice@example.com": _make_participant(
                status="negotiating",
                last_sent_at=last_sent
            )}
        )
        try:
            result, output = _run_main(path)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "no_new_replies")
        finally:
            os.unlink(path)


class TestOutputJsonFormat(unittest.TestCase):
    def test_json_separator_present(self):
        import io
        from contextlib import redirect_stdout
        path = _make_state(status="confirmed")
        try:
            f = io.StringIO()
            test_args = ["check_new_replies.py", "--state", path]
            with patch("sys.argv", test_args), redirect_stdout(f):
                try:
                    cnr.main()
                except SystemExit:
                    pass
            output = f.getvalue()
            self.assertIn("---JSON---", output)
            # Last non-empty line after separator should be valid JSON
            parts = output.split("---JSON---\n")
            self.assertEqual(len(parts), 2)
            json_data = json.loads(parts[1].strip())
            self.assertIn("action", json_data)
            self.assertIn("meeting_id", json_data)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
