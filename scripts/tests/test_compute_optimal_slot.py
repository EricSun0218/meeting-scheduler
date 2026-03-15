#!/usr/bin/env python3
"""Tests for compute_optimal_slot.py"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compute_optimal_slot as cos


class TestParseSlot(unittest.TestCase):
    def test_utc_z(self):
        dt = cos._parse_slot("2026-03-15T10:00:00Z")
        self.assertIsNotNone(dt)

    def test_offset(self):
        dt = cos._parse_slot("2026-03-15T10:00:00+08:00")
        self.assertIsNotNone(dt)

    def test_no_seconds(self):
        dt = cos._parse_slot("2026-03-15T10:00+08:00")
        self.assertIsNotNone(dt)

    def test_none(self):
        self.assertIsNone(cos._parse_slot(None))

    def test_empty(self):
        self.assertIsNone(cos._parse_slot(""))


class TestSlotInList(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(cos._slot_in_list(
            "2026-03-15T10:00:00+08:00",
            ["2026-03-15T10:00:00+08:00"]
        ))

    def test_cross_timezone_match(self):
        """Same instant in different timezone formats should match."""
        self.assertTrue(cos._slot_in_list(
            "2026-03-15T02:00:00Z",
            ["2026-03-15T10:00:00+08:00"]
        ))

    def test_no_match(self):
        self.assertFalse(cos._slot_in_list(
            "2026-03-15T11:00:00+08:00",
            ["2026-03-15T10:00:00+08:00"]
        ))

    def test_empty_list(self):
        self.assertFalse(cos._slot_in_list("2026-03-15T10:00:00Z", []))


class TestGetParticipantAvailability(unittest.TestCase):
    def test_basic(self):
        participants = {
            "a@x.com": {"available_slots": ["2026-03-15T10:00+08:00"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
            "b@x.com": {"available_slots": [], "hard_no_slots": ["2026-03-15T10:00+08:00"], "maybe_slots": [], "soft_no_slots": []},
        }
        result = cos.get_participant_availability(participants, "2026-03-15T10:00+08:00")
        self.assertEqual(result["a@x.com"], "yes")
        self.assertEqual(result["b@x.com"], "hard_no")

    def test_cross_timezone_availability(self):
        """Slot stored as +08:00 should match when queried as Z."""
        participants = {
            "a@x.com": {"available_slots": ["2026-03-15T10:00:00+08:00"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
        }
        result = cos.get_participant_availability(participants, "2026-03-15T02:00:00Z")
        self.assertEqual(result["a@x.com"], "yes")

    def test_unknown(self):
        participants = {
            "a@x.com": {"available_slots": [], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
        }
        result = cos.get_participant_availability(participants, "2026-03-15T10:00+08:00")
        self.assertEqual(result["a@x.com"], "unknown")


class TestScoreSlot(unittest.TestCase):
    def test_all_yes(self):
        cost, breakdown = cos.score_slot({"a": "yes", "b": "yes"})
        self.assertEqual(cost, 0.0)

    def test_mixed(self):
        cost, breakdown = cos.score_slot({"a": "yes", "b": "no"})
        self.assertAlmostEqual(cost, 0.8)

    def test_empty(self):
        cost, breakdown = cos.score_slot({})
        self.assertEqual(cost, float("inf"))


class TestCompute(unittest.TestCase):
    def _make_state(self, participants, proposed_slots):
        return {"participants": participants, "proposed_slots": proposed_slots}

    def test_perfect(self):
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
                "b@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "perfect")
        self.assertEqual(result["best_slot"], "S1")

    def test_best_with_unavailable(self):
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
                "b@x.com": {"status": "negotiating", "available_slots": [], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": ["S1"]},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "best")
        self.assertIn("b@x.com", result["unavailable_for_best"])

    def test_all_declined(self):
        state = self._make_state(
            participants={
                "a@x.com": {"status": "declined"},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "deadlock")
        self.assertEqual(result["deadlock_reason"], "all_declined")

    def test_all_have_hard_no(self):
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": [], "hard_no_slots": ["S1"], "maybe_slots": [], "soft_no_slots": []},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "needs_organizer")
        self.assertTrue(result["all_slots_have_hard_no"])

    def test_skipped_excluded(self):
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
                "b@x.com": {"status": "skipped"},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "perfect")
        self.assertEqual(result["total_participants"], 1)

    def test_not_perfect_with_unknown(self):
        """If a participant hasn't replied (unknown), status should be 'best' not 'perfect'."""
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
                "b@x.com": {"status": "waiting_reply", "available_slots": [], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "best")

    def test_deadlock_all_soft_no(self):
        """When all participants have soft_no on all slots, should trigger deadlock."""
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": [], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": ["S1"]},
                "b@x.com": {"status": "negotiating", "available_slots": [], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": ["S1"]},
            },
            proposed_slots=["S1"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "deadlock")

    def test_has_hard_no_conflict_always_false_for_eligible(self):
        """has_hard_no_conflict should be False when best is from eligible_slots."""
        state = self._make_state(
            participants={
                "a@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": ["S2"], "maybe_slots": [], "soft_no_slots": []},
                "b@x.com": {"status": "negotiating", "available_slots": ["S1"], "hard_no_slots": [], "maybe_slots": [], "soft_no_slots": []},
            },
            proposed_slots=["S1", "S2"]
        )
        result = cos.compute(state)
        self.assertFalse(result["has_hard_no_conflict"])

    def test_cross_timezone_hard_no_veto(self):
        """hard_no stored as +08:00 should veto the same slot queried as Z."""
        state = self._make_state(
            participants={
                "a@x.com": {
                    "status": "negotiating",
                    "available_slots": [],
                    "hard_no_slots": ["2026-03-15T10:00:00+08:00"],
                    "maybe_slots": [], "soft_no_slots": [],
                },
            },
            proposed_slots=["2026-03-15T02:00:00Z"]
        )
        result = cos.compute(state)
        self.assertEqual(result["status"], "needs_organizer")
        self.assertTrue(result["all_slots_have_hard_no"])


if __name__ == "__main__":
    unittest.main()
