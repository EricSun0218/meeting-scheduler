#!/usr/bin/env python3
"""
Compute the optimal meeting slot using a minimum-cost approach.

Usage:
  compute_optimal_slot.py --state <path/to/mtg-xxx.json>

Output (JSON):
  {
    "status": "perfect" | "best" | "needs_organizer" | "deadlock",
    "best_slot": "2026-03-14T10:00+08:00",
    "best_slot_cost": 0.0,
    "total_participants": 3,
    "unavailable_for_best": ["b@x.com"],
    "next_best_slot": "2026-03-14T14:00+08:00",
    "next_best_cost": 0.5,
    "slot_scores": [
      {"slot": "...", "cost": 0.0, "breakdown": {"a@x.com": 0, "b@x.com": 1}},
      ...
    ],
    "deadlock_reason": null | "all_slots_exhausted" | "all_declined" | "max_rounds_all"
  }
"""
import json
import sys
import argparse
from datetime import datetime, timezone

from date_utils import parse_iso

# Cost values per availability response
COST = {
    "yes":      0.0,   # explicitly available
    "maybe":    0.5,   # available but not ideal
    "unknown":  0.3,   # no reply yet — don't block, but penalise slightly
    "no":       0.8,   # soft no — preference-based, may reconsider
    "hard_no":  2.0,   # definitive rejection — never ask again; high cost excludes slot
}

# A slot is "deadlocked" if its cost per participant averages above this.
# With hard_no slots already filtered, max per-person cost is 0.8 (soft_no).
# Threshold of 0.8 triggers when ALL active participants have soft_no.
DEADLOCK_COST_THRESHOLD = 0.8


def load_state(path):
    with open(path) as f:
        return json.load(f)


def _parse_slot(s):
    """Parse an ISO slot string to a UTC datetime for comparison."""
    dt = parse_iso(s)
    return dt.astimezone(timezone.utc) if dt else None


def _build_slot_set(slot_list):
    """Pre-parse a list of slot strings into a set of UTC datetimes for O(1) lookup.
    Non-parseable slots are stored as their original string.
    """
    result = set()
    for s in slot_list:
        dt = _parse_slot(s)
        result.add(dt if dt is not None else s)
    return result


def _slot_in_list(slot, slot_list):
    """Check if a slot matches any in the list (timezone-aware comparison).
    Falls back to string comparison for non-ISO slot labels.
    """
    target = _parse_slot(slot)
    if target is None:
        return slot in slot_list
    return any(_parse_slot(s) == target for s in slot_list)


def _lookup_slot(slot, slot_set):
    """Check if a slot is in a pre-built set. Handles both parsed and string slots."""
    target = _parse_slot(slot)
    if target is not None:
        return target in slot_set
    return slot in slot_set


def get_participant_availability(participants, slot, participant_sets=None):
    """Return availability label for each participant for a given slot.
    If participant_sets is provided, use pre-parsed sets for O(1) lookup.
    """
    result = {}
    for email, data in participants.items():
        if participant_sets and email in participant_sets:
            sets = participant_sets[email]
            if _lookup_slot(slot, sets["available"]):
                result[email] = "yes"
            elif _lookup_slot(slot, sets["hard_no"]):
                result[email] = "hard_no"
            elif _lookup_slot(slot, sets["maybe"]):
                result[email] = "maybe"
            elif _lookup_slot(slot, sets["soft_no"]):
                result[email] = "no"
            else:
                result[email] = "unknown"
        else:
            # Fallback: parse on the fly
            if _lookup_slot(slot, _build_slot_set(data.get("available_slots", []))):
                result[email] = "yes"
            elif _lookup_slot(slot, _build_slot_set(data.get("hard_no_slots", []))):
                result[email] = "hard_no"
            elif _lookup_slot(slot, _build_slot_set(data.get("maybe_slots", []))):
                result[email] = "maybe"
            elif _lookup_slot(slot, _build_slot_set(data.get("soft_no_slots", []))):
                result[email] = "no"
            else:
                result[email] = "unknown"
    return result


def score_slot(availability_map):
    """Compute total cost for a slot given {email: label} map."""
    if not availability_map:
        return float("inf"), {}
    breakdown = {e: COST.get(v, 0.3) for e, v in availability_map.items()}
    total = sum(breakdown.values())
    return total, breakdown


def compute(state):
    participants = state.get("participants", {})
    proposed_slots = state.get("proposed_slots", [])

    # Filter out declined and skipped participants
    active_participants = {
        e: d for e, d in participants.items()
        if d.get("status") not in ("declined", "skipped")
    }
    n = len(active_participants)

    if n == 0:
        return {
            "status": "deadlock",
            "best_slot": None,
            "best_slot_cost": None,
            "total_participants": 0,
            "unavailable_for_best": [],
            "next_best_slot": None,
            "next_best_cost": None,
            "slot_scores": [],
            "deadlock_reason": "all_declined",
        }

    # Check if all remaining participants are stalled
    stalled = [e for e, d in active_participants.items() if d.get("status") == "stalled"]
    if len(stalled) == n:
        return {
            "status": "deadlock",
            "best_slot": None,
            "best_slot_cost": None,
            "total_participants": n,
            "unavailable_for_best": stalled,
            "next_best_slot": None,
            "next_best_cost": None,
            "slot_scores": [],
            "deadlock_reason": "max_rounds_all",
        }

    if not proposed_slots:
        return {
            "status": "deadlock",
            "best_slot": None,
            "best_slot_cost": None,
            "total_participants": n,
            "unavailable_for_best": [],
            "next_best_slot": None,
            "next_best_cost": None,
            "slot_scores": [],
            "deadlock_reason": "all_slots_exhausted",
        }

    # Pre-parse all participant slot lists once for O(1) lookup
    participant_sets = {}
    for email, data in active_participants.items():
        participant_sets[email] = {
            "available": _build_slot_set(data.get("available_slots", [])),
            "hard_no": _build_slot_set(data.get("hard_no_slots", [])),
            "maybe": _build_slot_set(data.get("maybe_slots", [])),
            "soft_no": _build_slot_set(data.get("soft_no_slots", [])),
        }

    def score_all(slots):
        results = []
        for slot in slots:
            avail_map = get_participant_availability(active_participants, slot, participant_sets)
            cost, breakdown = score_slot(avail_map)
            hard_nos = [e for e, lbl in avail_map.items() if lbl == "hard_no"]
            results.append({
                "slot": slot,
                "cost": cost,
                "breakdown": breakdown,
                "hard_no_count": len(hard_nos),
                "hard_no_participants": hard_nos,
            })
        return results

    # ── Step 1: Veto filter ────────────────────────────────────────────────
    # Exclude any slot that has at least one hard_no
    def has_hard_no(slot):
        return any(
            _lookup_slot(slot, participant_sets[email]["hard_no"])
            for email in active_participants
        )

    eligible_slots = [s for s in proposed_slots if not has_hard_no(s)]
    all_have_hard_no = len(eligible_slots) == 0

    # ── Step 2: Borda Count (cost matrix) on eligible slots ───────────────
    if eligible_slots:
        scored = score_all(eligible_slots)
        scored.sort(key=lambda x: x["cost"])
    else:
        # All slots have hard_no — pick the "easiest" for organizer to decide:
        # rank by (fewest hard_nos, then lowest cost among non-hard_no participants)
        scored = score_all(proposed_slots)
        scored.sort(key=lambda x: (x["hard_no_count"], x["cost"]))

    best = scored[0]
    next_best = scored[1] if len(scored) > 1 else None

    unavailable_for_best = [
        e for e, c in best["breakdown"].items() if c >= 0.8
    ]

    # Perfect: no hard_nos, cost == 0, AND all active participants explicitly replied
    all_replied = all(
        v != "unknown"
        for v in get_participant_availability(active_participants, best["slot"], participant_sets).values()
    )
    perfect = (
        not all_have_hard_no
        and best["hard_no_count"] == 0
        and best["cost"] == 0.0
        and all_replied
    )

    # Deadlock: all eligible slots still have high avg cost (everyone soft_no/unknown)
    avg_cost = best["cost"] / n if n > 0 else 0
    if not all_have_hard_no and avg_cost >= DEADLOCK_COST_THRESHOLD:
        return {
            "status": "deadlock",
            "best_slot": best["slot"],
            "best_slot_cost": best["cost"],
            "total_participants": n,
            "unavailable_for_best": unavailable_for_best,
            "hard_no_for_best": best["hard_no_participants"],
            "has_hard_no_conflict": False,
            "all_slots_have_hard_no": False,
            "next_best_slot": next_best["slot"] if next_best else None,
            "next_best_cost": next_best["cost"] if next_best else None,
            "slot_scores": scored,
            "deadlock_reason": "all_slots_exhausted",
        }

    # All slots have hard_no → needs organizer decision with best recommendation
    if all_have_hard_no:
        return {
            "status": "needs_organizer",
            "best_slot": best["slot"],          # recommended slot (fewest hard_nos)
            "best_slot_cost": best["cost"],
            "total_participants": n,
            "unavailable_for_best": unavailable_for_best,
            "hard_no_for_best": best["hard_no_participants"],
            "has_hard_no_conflict": True,
            "all_slots_have_hard_no": True,
            "next_best_slot": next_best["slot"] if next_best else None,
            "next_best_cost": next_best["cost"] if next_best else None,
            "slot_scores": scored,
            "deadlock_reason": "all_slots_have_hard_no",
        }

    return {
        "status": "perfect" if perfect else "best",
        "best_slot": best["slot"],
        "best_slot_cost": best["cost"],
        "total_participants": n,
        "unavailable_for_best": unavailable_for_best,
        "hard_no_for_best": best["hard_no_participants"],
        "has_hard_no_conflict": False,  # eligible_slots already exclude hard_no slots
        "all_slots_have_hard_no": False,
        "next_best_slot": next_best["slot"] if next_best else None,
        "next_best_cost": next_best["cost"] if next_best else None,
        "slot_scores": scored,
        "deadlock_reason": None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, help="Path to meeting state JSON file")
    args = parser.parse_args()

    state = load_state(args.state)
    result = compute(state)
    print(json.dumps(result, indent=2))
