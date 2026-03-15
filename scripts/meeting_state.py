#!/usr/bin/env python3
"""
Meeting state management utility.
Usage:
  meeting_state.py create <subject>                  → create new meeting, print id
  meeting_state.py get <id>                          → print full state JSON
  meeting_state.py update <id> <json_patch>          → merge patch into state
  meeting_state.py update_participant <id> <email> <json_patch>
  meeting_state.py list                              → list all meetings
  meeting_state.py list --status negotiating         → filter by status
"""
import json
import sys
import os
import tempfile
import uuid
from pathlib import Path

MEETINGS_DIR = Path.home() / ".openclaw" / "workspace" / "meetings"


def ensure_dir():
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)


def state_path(meeting_id):
    if meeting_id.startswith("mtg-"):
        meeting_id = meeting_id[4:]
    return MEETINGS_DIR / f"mtg-{meeting_id}.json"


def load(meeting_id):
    p = state_path(meeting_id)
    if not p.exists():
        print(f"Error: meeting {meeting_id} not found", file=sys.stderr)
        sys.exit(1)
    with open(p) as f:
        return json.load(f)


def save(meeting_id, state):
    ensure_dir()
    target = state_path(meeting_id)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.rename(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def create(subject):
    ensure_dir()
    meeting_id = uuid.uuid4().hex[:8]
    state = {
        "id": meeting_id,
        "status": "gathering_info",
        "subject": subject,
        "organizer": "",
        "duration_minutes": 60,
        "timezone": "UTC",
        "description": "",
        "email_tool": "",
        "calendar_tool": "",
        "meeting_link_tool": "",
        "meeting_link_via": "",
        "meeting_link": "",
        "poll_task_id": None,
        "poll_busy": False,
        "poll_busy_since": None,
        "time_range_end": "",
        "proposed_slots": [],
        "pending_replies": [],
        "participants": {},
        "final_agreed_slot": None,
        "confirmed_at": None
    }
    save(meeting_id, state)
    print(meeting_id)


def get(meeting_id):
    print(json.dumps(load(meeting_id), indent=2))


def update(meeting_id, patch_json):
    state = load(meeting_id)
    patch = json.loads(patch_json)
    state.update(patch)
    save(meeting_id, state)
    print(json.dumps(state, indent=2))


def update_participant(meeting_id, email, patch_json):
    state = load(meeting_id)
    patch = json.loads(patch_json)
    if email not in state["participants"]:
        state["participants"][email] = {
            "name": "",
            "rounds": 0,
            "status": "waiting_reply",
            "thread_id": "",
            "last_sent_at": "",
            "last_replied_at": None,
            "available_slots": [],
            "maybe_slots": [],
            "soft_no_slots": [],
            "hard_no_slots": [],
            "suggested_slots": [],
            "processed_message_ids": [],
            "conversation_history": []
        }
    state["participants"][email].update(patch)
    save(meeting_id, state)
    print(json.dumps(state["participants"][email], indent=2))


def list_meetings(status_filter=None):
    ensure_dir()
    meetings = []
    for p in sorted(MEETINGS_DIR.glob("mtg-*.json")):
        with open(p) as f:
            state = json.load(f)
        if status_filter and state.get("status") != status_filter:
            continue
        meetings.append({
            "id": state["id"],
            "subject": state.get("subject", ""),
            "status": state.get("status", ""),
            "participants": list(state.get("participants", {}).keys()),
            "final_agreed_slot": state.get("final_agreed_slot")
        })
    print(json.dumps(meetings, indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    if cmd == "create" and len(args) >= 2:
        create(" ".join(args[1:]))
    elif cmd == "get" and len(args) == 2:
        get(args[1])
    elif cmd == "update" and len(args) == 3:
        update(args[1], args[2])
    elif cmd == "update_participant" and len(args) == 4:
        update_participant(args[1], args[2], args[3])
    elif cmd == "list":
        status = None
        if "--status" in args:
            idx = args.index("--status")
            if idx + 1 < len(args):
                status = args[idx + 1]
            else:
                print("Error: --status requires a value", file=sys.stderr)
                sys.exit(1)
        list_meetings(status)
    else:
        print(__doc__)
        sys.exit(1)
