#!/usr/bin/env python3
"""
Lightweight pre-check: scan email threads for new replies since last_sent_at.
Outputs structured JSON to stdout for the scheduled-task agent to act on.

Usage:
  check_new_replies.py --state <path/to/mtg-xxx.json>

Output (stdout):
  Human-readable log lines followed by a JSON result after ---JSON--- separator.
  Agent should parse the JSON after ---JSON--- to determine action.

Exit codes:
  0 = normal (check output JSON for action)
  1 = error (file not found, parse failure, etc.)
"""
import json
import subprocess
import sys
import argparse
from datetime import datetime, timezone, timedelta

from date_utils import parse_iso, parse_date_flexible, atomic_write_json, extract_from_address


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def run(cmd):
    """Run a command given as a list of arguments (no shell interpretation)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def check_thread_gog(thread_id, last_sent_at_str, organizer, processed_ids=None, participant_email="", subject=""):
    """Check Gmail for replies via search (handles broken thread chains from non-Gmail clients).
    Falls back gracefully when thread get returns 0 messages (e.g. QQ Mail breaks thread association).
    Strategy: search by sender + subject keywords, filter by date > last_sent_at.
    """
    last_sent = parse_iso(last_sent_at_str)
    last_utc = last_sent.astimezone(timezone.utc) if last_sent else None
    processed_ids = processed_ids or []

    # Build search query: sender + subject (strip common prefixes for broader match)
    subject_kw = subject.replace("会议邀请：", "").replace("Re: ", "").strip()
    query = f'from:{participant_email} subject:"{subject_kw}"'
    cmd = ["gog", "gmail", "messages", "search", "--account", organizer, query, "--json"]
    log(f"  gog command: {' '.join(cmd)}")
    ok, out, err = run(cmd)
    if not ok:
        log(f"  gog command FAILED: {err or 'no output'}")
        return []
    if not out:
        log(f"  gog command returned empty output")
        return []
    try:
        data = json.loads(out)
    except Exception as e:
        log(f"  gog JSON parse error: {e}, raw output: {out[:200]}")
        return []

    messages = data.get("messages") or (data if isinstance(data, list) else [])
    log(f"  gog returned {len(messages)} message(s) from search")
    new_messages = []
    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id and msg_id in processed_ids:
            log(f"  msg id={msg_id} → SKIP (already processed)")
            continue
        from_field = extract_from_address(msg.get("from", ""))
        if organizer and organizer in from_field:
            log(f"  msg from={from_field} → SKIP (organizer)")
            continue
        msg_date = parse_date_flexible(msg.get("date", ""))
        if msg_date is None:
            log(f"  msg from={from_field}, date={msg.get('date', '')} → SKIP (date parse failed)")
            continue
        msg_utc = msg_date.astimezone(timezone.utc)
        if last_utc and msg_utc <= last_utc:
            log(f"  msg from={from_field}, msg_utc={msg_utc.isoformat()} <= last_utc={last_utc.isoformat()} → SKIP (old)")
            continue
        log(f"  msg from={from_field}, msg_utc={msg_utc.isoformat()} → NEW")
        new_messages.append({
            "message_id": msg_id,
            "date": msg.get("date", ""),
            "from": from_field,
            "snippet": msg.get("snippet", "") or msg.get("subject", ""),
        })
    log(f"  result: {len(new_messages)} new reply(s)")
    return new_messages


def check_thread_himalaya(participant_email, subject, last_sent_at_str, organizer, processed_ids=None):
    """Check inbox via himalaya CLI (no thread-id; match by sender + subject)."""
    last_sent = parse_iso(last_sent_at_str)
    cmd = ["himalaya", "envelope", "list", "--query", f"FROM {participant_email}", "--output", "json"]
    log(f"  himalaya command: {' '.join(cmd)}")
    ok, out, err = run(cmd)
    if not ok:
        log(f"  himalaya command FAILED: {err or 'no output'}")
        return []
    if not out:
        log(f"  himalaya command returned empty output")
        return []
    try:
        envelopes = json.loads(out)
        if isinstance(envelopes, dict):
            envelopes = envelopes.get("response", [])
    except Exception as e:
        log(f"  himalaya JSON parse error: {e}, raw output: {out[:200]}")
        return []

    log(f"  himalaya returned {len(envelopes)} envelope(s)")
    new_messages = []
    last_utc = last_sent.astimezone(timezone.utc) if last_sent else None
    processed_ids = processed_ids or []
    for env in envelopes:
        env_id = str(env.get("id", ""))
        if env_id and env_id in processed_ids:
            log(f"  env id={env_id} → SKIP (already processed)")
            continue
        from_field = extract_from_address(env.get("from", ""))
        if organizer and organizer in from_field:
            log(f"  env from={from_field} → SKIP (organizer)")
            continue
        env_subject = env.get("subject", "")
        if subject and subject not in env_subject:
            log(f"  env from={from_field}, subject={env_subject} → SKIP (subject mismatch)")
            continue
        msg_date = parse_date_flexible(env.get("date", ""))
        if msg_date is None:
            log(f"  env from={from_field}, date={env.get('date', '')} → SKIP (date parse failed)")
            continue
        msg_utc = msg_date.astimezone(timezone.utc)
        if last_utc and msg_utc <= last_utc:
            log(f"  env from={from_field}, msg_utc={msg_utc.isoformat()} <= last_utc={last_utc.isoformat()} → SKIP (old)")
            continue
        log(f"  env from={from_field}, msg_utc={msg_utc.isoformat()} > last_utc={last_utc.isoformat() if last_utc else 'None'} → NEW")
        new_messages.append({
            "message_id": str(env.get("id", "")),
            "date": env.get("date", ""),
            "from": from_field,
            "snippet": env_subject,
        })
    log(f"  result: {len(new_messages)} new reply(s)")
    return new_messages


def check_thread(thread_id, last_sent_at_str, organizer, email_tool, participant_email="", subject="", processed_ids=None):
    """Dispatch to the right email tool."""
    if email_tool == "himalaya":
        return check_thread_himalaya(participant_email, subject, last_sent_at_str, organizer, processed_ids)
    return check_thread_gog(thread_id, last_sent_at_str, organizer, processed_ids, participant_email=participant_email, subject=subject)


def get_future_slots(proposed_slots, now):
    """Filter proposed_slots to only those in the future."""
    future = []
    for s in proposed_slots:
        dt = parse_iso(s)
        if dt and dt.astimezone(timezone.utc) > now:
            future.append(s)
    return future


def reminder_due(data, future_slots, now):
    """Return True if this participant is overdue for a no-reply reminder."""
    if data.get("status") not in ("waiting_reply",):
        return False
    last_sent = parse_iso(data.get("last_sent_at", ""))
    if last_sent is None:
        return False
    if not future_slots:
        return False
    nearest = min(parse_iso(s) for s in future_slots if parse_iso(s))
    if nearest is None:
        return False
    urgency_hours = (nearest.astimezone(timezone.utc) - now).total_seconds() / 3600
    elapsed_hours = (now - last_sent.astimezone(timezone.utc)).total_seconds() / 3600
    if urgency_hours > 72:
        return elapsed_hours >= 24
    elif urgency_hours > 24:
        return elapsed_hours >= 12
    elif urgency_hours > 6:
        return elapsed_hours >= 6
    return False  # < 6h: stop automated reminders, handled by escalation


def _set_poll_busy(state_path):
    """Set poll_busy=true in the state file before handing off to agent.
    Uses atomic write to prevent corruption on crash."""
    try:
        with open(state_path) as f:
            state = json.load(f)
        state["poll_busy"] = True
        state["poll_busy_since"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(state_path, state)
    except Exception as e:
        log(f"  warning: failed to set poll_busy: {e}")


def _clear_poll_busy(state_path):
    """Clear poll_busy flag when no action is needed.
    Uses atomic write to prevent corruption on crash."""
    try:
        with open(state_path) as f:
            state = json.load(f)
        state["poll_busy"] = False
        state["poll_busy_since"] = None
        atomic_write_json(state_path, state)
    except Exception as e:
        log(f"  warning: failed to clear poll_busy: {e}")


def output_result(meeting_id, action, reason, new_replies=None, reminders_due=None,
                   state_path=None, pending_replies=None):
    """Print the JSON result separator and structured output.
    poll_busy is set early (before email checks). If action is 'none',
    release the lock so the next tick can proceed.

    pending_replies: list of emails still awaiting reply in this round.
    all_pending_replied: True when pending_replies is empty (safe to compute).
    """
    if action == "none" and state_path:
        _clear_poll_busy(state_path)
    pending = pending_replies if pending_replies is not None else []
    result = {
        "action": action,
        "meeting_id": meeting_id,
        "reason": reason,
        "new_replies": new_replies or [],
        "reminders_due": reminders_due or [],
        "pending_replies": pending,
        "all_pending_replied": len(pending) == 0,
    }
    print("---JSON---")
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    with open(args.state) as f:
        state = json.load(f)

    meeting_id = state.get("id", "unknown")

    if state.get("status") != "negotiating":
        log(f"[{meeting_id}] status={state.get('status')}, skipping poll")
        output_result(meeting_id, "none", "not_negotiating")
        sys.exit(0)

    # Concurrency guard: check if another agent is mid-negotiation
    if state.get("poll_busy"):
        busy_since = parse_iso(state.get("poll_busy_since", ""))
        now_check = datetime.now(timezone.utc)
        if busy_since and (now_check - busy_since.astimezone(timezone.utc)) < timedelta(minutes=10):
            log(f"[{meeting_id}] poll_busy=true since {state.get('poll_busy_since')}, skipping (agent running)")
            output_result(meeting_id, "none", "agent_busy")
            sys.exit(0)
        else:
            log(f"[{meeting_id}] poll_busy=true but stale (>10min), proceeding")

    # Acquire lock IMMEDIATELY — before any email checks — to prevent
    # the next cron tick from also passing the poll_busy guard.
    _set_poll_busy(args.state)

    organizer = state.get("organizer", "")
    email_tool = state.get("email_tool", "gog")
    subject = state.get("subject", "")
    proposed_slots = state.get("proposed_slots", [])
    pending_replies = list(state.get("pending_replies", []))
    now_utc = datetime.now(timezone.utc)

    log(f"[{meeting_id}] starting poll check (email_tool={email_tool}, organizer={organizer})")
    log(f"[{meeting_id}] proposed_slots: {proposed_slots}")

    future_slots = get_future_slots(proposed_slots, now_utc)
    log(f"[{meeting_id}] future_slots: {future_slots} ({len(future_slots)}/{len(proposed_slots)})")

    # Check participants for new replies FIRST (before slot expiry — reply may contain suggested times)
    new_replies = []
    reminders_due_list = []

    for email, data in state.get("participants", {}).items():
        p_status = data.get("status", "")
        thread_id = data.get("thread_id", "")
        last_sent_at = data.get("last_sent_at", "")
        processed_ids = data.get("processed_message_ids", [])
        log(f"[{meeting_id}] checking participant {email} (status={p_status}, thread={thread_id}, last_sent={last_sent_at})")

        if p_status not in ("waiting_reply", "negotiating"):
            log(f"[{meeting_id}]   skipping: status={p_status}")
            continue

        msgs = check_thread(
            thread_id=thread_id,
            last_sent_at_str=last_sent_at,
            organizer=organizer,
            email_tool=email_tool,
            participant_email=email,
            subject=subject,
            processed_ids=processed_ids,
        )
        if msgs:
            new_replies.append({"email": email, "thread_id": thread_id, "messages": msgs})
            log(f"[{meeting_id}]   → {len(msgs)} new reply(s) found")
        elif reminder_due(data, future_slots, now_utc):
            reminders_due_list.append(email)
            last_sent_dt = parse_iso(last_sent_at)
            elapsed = (now_utc - last_sent_dt.astimezone(timezone.utc)).total_seconds() / 3600 if last_sent_dt else 0
            log(f"[{meeting_id}]   → reminder due (elapsed={elapsed:.1f}h)")
        else:
            log(f"[{meeting_id}]   → no new replies, no reminder due")

    # New replies take priority — process them even if all slots expired (reply may add new slots)
    if new_replies:
        # Compute remaining pending_replies after these replies
        replied_emails = {r["email"] for r in new_replies}
        remaining_pending = [e for e in pending_replies if e not in replied_emails]
        log(f"[{meeting_id}] action needed: reason=new_replies, count={len(new_replies)}, "
            f"pending_remaining={len(remaining_pending)}/{len(pending_replies)}")
        output_result(meeting_id, "process", "new_replies", new_replies=new_replies,
                      reminders_due=reminders_due_list, state_path=args.state,
                      pending_replies=remaining_pending)
        sys.exit(0)

    # All slots expired (only checked after confirming no new replies)
    if proposed_slots and not future_slots:
        time_range_end = parse_iso(state.get("time_range_end", ""))
        range_ended = time_range_end and time_range_end.astimezone(timezone.utc) <= now_utc
        reason = "all_slots_expired_range_ended" if range_ended else "all_slots_expired"
        log(f"[{meeting_id}] all proposed slots have expired (range_ended={range_ended})")
        output_result(meeting_id, "process", reason, state_path=args.state,
                      pending_replies=pending_replies)
        sys.exit(0)

    # Reminders due
    if reminders_due_list:
        log(f"[{meeting_id}] action needed: reason=reminders_due, count={len(reminders_due_list)}")
        output_result(meeting_id, "process", "reminders_due", reminders_due=reminders_due_list,
                      state_path=args.state, pending_replies=pending_replies)
        sys.exit(0)

    # Urgency escalation: < 6h to nearest slot with participants still waiting
    waiting_participants = [
        email for email, data in state.get("participants", {}).items()
        if data.get("status") == "waiting_reply"
    ]
    if waiting_participants and future_slots:
        nearest = min(
            (parse_iso(s) for s in future_slots if parse_iso(s)),
            default=None
        )
        if nearest:
            urgency_hours = (nearest.astimezone(timezone.utc) - now_utc).total_seconds() / 3600
            if urgency_hours < 6:
                log(f"[{meeting_id}] urgency escalation: {len(waiting_participants)} waiting, nearest slot in {urgency_hours:.1f}h")
                output_result(meeting_id, "process", "urgency_escalation", reminders_due=waiting_participants,
                              state_path=args.state, pending_replies=pending_replies)
                sys.exit(0)

    log(f"[{meeting_id}] no action needed")
    output_result(meeting_id, "none", "no_new_replies", state_path=args.state,
                  pending_replies=pending_replies)
    sys.exit(0)


if __name__ == "__main__":
    main()
