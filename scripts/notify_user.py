#!/usr/bin/env python3
"""
Notify the main session user via the local OpenClaw gateway.

Sends a structured signal to the main session via chat.send (webchat).
The signal encodes the meeting id, event type, and optional channel/target
so the main session can route the formatted notification to the correct channel.

Usage:
  notify_user.py --state /path/to/mtg-<id>.json --event consensus

Events:
  consensus              All participants agreed on a slot
  confirmed              Final confirmation emails sent
  escalation:<reason>    Negotiation needs organizer intervention

Signal format sent to main session:
  __MEETING_NOTIFY__:<id>:<event>
  __MEETING_NOTIFY__:<id>:<event>:notify_channel=<channel>:notify_target=<target>

The main session receives the signal, reads the state file, formats the message
per ux-copy.md, and sends it to the user via the appropriate channel.
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


def send_signal(signal: str, session_key: str = "agent:main:main") -> bool:
    """Send signal to main session via gateway chat.send."""
    config = load_config()
    gw = config.get("gateway", {})
    token = gw.get("auth", {}).get("token", "")

    params = {
        "sessionKey": session_key,
        "message": signal,
        "idempotencyKey": str(uuid.uuid4()),
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
            print(f"[notify_user] ❌ chat.send failed: {result.stderr.strip()}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[notify_user] ❌ Error: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Notify the user via structured signal.")
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

    # Build signal — include channel/target from state if available
    notify_channel = state.get("notify_channel", "")
    notify_target = state.get("notify_target", "")

    signal = f"__MEETING_NOTIFY__:{meeting_id}:{args.event}"
    if notify_channel and notify_target:
        signal += f":notify_channel={notify_channel}:notify_target={notify_target}"

    print(f"[notify_user] Meeting: {meeting_id}, event: {args.event}", file=sys.stderr)
    ok = send_signal(signal, session_key=args.session)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
