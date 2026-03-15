#!/usr/bin/env python3
"""
Notify the main session user via the local OpenClaw gateway (chat.send RPC).

Usage:
  notify_user.py --message "text"
  notify_user.py --state /path/to/mtg-<id>.json --message "text"

Reads gateway port and auth token from ~/.openclaw/openclaw.json.
Sends the message to sessionKey="agent:main:main" so it reaches the user
on whatever channel they are currently on (webchat, telegram, etc.).
"""

import argparse
import json
import os
import sys
import uuid
import urllib.request
import urllib.error


def load_config():
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    with open(config_path) as f:
        return json.load(f)


def send_notification(message: str, session_key: str = "agent:main:main") -> bool:
    """Send a chat message to the main session via gateway HTTP API."""
    config = load_config()
    gw = config.get("gateway", {})
    port = gw.get("port", 18789)
    token = gw.get("auth", {}).get("token", "")

    idempotency_key = str(uuid.uuid4())
    payload = {
        "method": "chat.send",
        "params": {
            "sessionKey": session_key,
            "message": message,
            "idempotencyKey": idempotency_key,
        },
    }

    # Gateway accepts HTTP POST to /rpc as well as WebSocket.
    # Fall back to WebSocket-over-HTTP if direct HTTP isn't available.
    # Use the openclaw CLI as the most reliable path.
    import subprocess
    params_json = json.dumps(payload["params"])
    cmd = [
        "openclaw", "gateway", "call", "chat.send",
        "--params", params_json,
        "--token", token,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print(f"[notify_user] ✅ Notification sent to {session_key}", file=sys.stderr)
            return True
        else:
            print(f"[notify_user] ❌ Failed: {result.stderr.strip()}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[notify_user] ❌ Error: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Notify the main session user.")
    parser.add_argument("--message", required=True, help="Message to send to the user")
    parser.add_argument("--state", help="Meeting state file (optional, for logging)")
    parser.add_argument("--session", default="agent:main:main", help="Target session key")
    args = parser.parse_args()

    if args.state:
        try:
            with open(os.path.expanduser(args.state)) as f:
                state = json.load(f)
            meeting_id = state.get("id", "?")
            print(f"[notify_user] Meeting: {meeting_id}", file=sys.stderr)
        except Exception:
            pass

    ok = send_notification(args.message, session_key=args.session)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
