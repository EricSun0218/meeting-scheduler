#!/usr/bin/env python3
"""
Notify the main session user via the local OpenClaw gateway (chat.send RPC).

Sends a structured signal to the main session. The main session reads the
meeting state and outputs the formatted message as an assistant bubble.

Usage:
  notify_user.py --state /path/to/mtg-<id>.json --event consensus
  notify_user.py --state /path/to/mtg-<id>.json --event confirmed
  notify_user.py --state /path/to/mtg-<id>.json --event "escalation:stalled"

Events:
  consensus              All participants agreed on a slot
  confirmed              Final confirmation emails sent
  escalation:<reason>    Negotiation needs organizer intervention

The signal format sent to main session: __MEETING_NOTIFY__:<id>:<event>
The main session handles this signal and outputs the formatted assistant message.
"""

import argparse
import json
import os
import sys
import uuid
import subprocess


def load_config():
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    with open(config_path) as f:
        return json.load(f)


def send_signal(meeting_id: str, event: str, session_key: str = "agent:main:main") -> bool:
    """Send a structured signal to the main session via gateway chat.send."""
    config = load_config()
    gw = config.get("gateway", {})
    token = gw.get("auth", {}).get("token", "")

    signal = f"__MEETING_NOTIFY__:{meeting_id}:{event}"
    idempotency_key = str(uuid.uuid4())

    params = {
        "sessionKey": session_key,
        "message": signal,
        "idempotencyKey": idempotency_key,
    }

    cmd = [
        "openclaw", "gateway", "call", "chat.send",
        "--params", json.dumps(params),
        "--token", token,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print(f"[notify_user] ✅ Signal sent: {signal}", file=sys.stderr)
            return True
        else:
            print(f"[notify_user] ❌ Failed: {result.stderr.strip()}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[notify_user] ❌ Error: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Notify the main session via structured signal.")
    parser.add_argument("--state", required=True, help="Meeting state file path")
    parser.add_argument("--event", required=True,
                        help="Event type: consensus | confirmed | escalation:<reason>")
    parser.add_argument("--session", default="agent:main:main", help="Target session key")
    args = parser.parse_args()

    state_path = os.path.expanduser(args.state)
    try:
        with open(state_path) as f:
            state = json.load(f)
        meeting_id = state.get("id")
        if not meeting_id:
            print("[notify_user] ❌ Could not read meeting id from state file", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[notify_user] ❌ Failed to read state file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[notify_user] Meeting: {meeting_id}, event: {args.event}", file=sys.stderr)
    ok = send_signal(meeting_id, args.event, session_key=args.session)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
