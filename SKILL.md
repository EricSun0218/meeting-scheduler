---
name: meeting-scheduler
description: Schedule multi-person meetings via email with automated negotiation. Detects available email tools, collects meeting details from user, sends invites, and autonomously handles multi-round per-participant time negotiation via background scheduled task. Final confirmation is sent as an email with a .ics (iCalendar) attachment — works universally across Gmail, Outlook, Apple Mail, QQ Mail, and any calendar client. Only pauses for user approval twice: before sending first invites, and before sending final confirmation. Use when user says things like "help me schedule a meeting", "约个会议", "help me find a time with multiple people", "coordinate a meeting", "set up a call with", "安排一个会议".
---

# Meeting Scheduler

## Overview

Two user-facing pauses only:
1. **Approve first invite batch** → hand off to background scheduled task
2. **Approve final confirmation email** (with .ics attachment) → done

Everything in between runs autonomously in background. Final invite uses .ics for universal calendar compatibility — no platform-specific setup needed.

---

## Phase 0 — Environment Detection

Run `scripts/detect_env.py` to discover available email tools:

```bash
python3 <skill_dir>/scripts/detect_env.py
```

**Email — no tool found:**
> No email provider detected. Please install `gog` (Google Workspace CLI) or `himalaya` (IMAP/SMTP) and configure authentication.

**Multiple email tools:** ask user to pick one.

**Calendar — used for slot generation** (read-only, avoids organizer's busy times):
- `gog` (Google Calendar)
- `gcalcli` (Google Calendar, alternative CLI)
- `icalBuddy` (macOS Apple Calendar / CalDAV)
- `khal` (CalDAV terminal calendar)

If multiple found, prefer `gog` > `gcalcli` > `icalBuddy` > `khal`. Store chosen tool name as `calendar_tool` in state. Use the `read_cmd` from detection output.

**Meeting link:** do NOT ask upfront. Detect auto-generation capability and store in state:
- `google_meet` (via `gog` or `gcalcli`) → can auto-generate
- `zoom` (via `zoom` CLI) → can auto-generate
- `teams` (via `mgc` Microsoft Graph CLI) → can auto-generate
- none → will ask user in Phase 4

Store as `meeting_link_tool` in state. Also store `meeting_link_via` (e.g. `"gog"`, `"gcalcli"`, `"mgc"`) for Phase 4.

---

## Phase 1 — Gather Meeting Info

Collect all required fields before drafting anything. Ask only for what's missing.

| Field | Required | Notes |
|-------|----------|-------|
| `participants` | ✅ | List of email addresses |
| `subject` | ✅ | Meeting title |
| `duration_minutes` | ✅ | e.g. 60 |
| `time_range` | ✅ | e.g. "next week", "within 2 weeks"; derive and store `time_range_end` as ISO date |
| `timezone` | ✅ | Detect from user profile; confirm if cross-timezone |
| `description` | ❌ | Optional agenda |
| `proposed_slots` | auto | Generated based on time range (see rules below) |

**Slot generation rules:**
```
time_range covers 1–2 days  → generate 5 slots
time_range covers 3–7 days  → generate 7 slots
time_range covers > 7 days  → generate 10 slots
```

Spread slots across different days AND different times of day (morning / early afternoon / late afternoon). Avoid weekends unless the time_range is short or user explicitly requests.

**If `calendar_tool` detected** — read organizer's existing events first, generate slots only in free gaps. Use the `read_cmd` from detection output:
```bash
# gog
gog calendar events --from <range_start> --to <range_end> --json

# gcalcli
gcalcli agenda <range_start> <range_end> --nocolor --tsv

# icalBuddy
icalBuddy -f -nc -nrd -df '%Y-%m-%d' -tf '%H:%M' eventsFrom:<range_start> to:<range_end>

# khal
khal list <range_start> <range_end> -df '{start-date}' -f '{start-time} {end-time} {title}'
```
Parse each tool's output to extract busy time ranges, then generate slots in the gaps.

**If no calendar** — generate slots based on typical business hours (09:00–18:00) spread across the range.

---

## Phase 2 — Draft & Send First Invites

Update state: `{"status": "pending_approval"}`

Draft plain-text invitation email for user review (see [references/email-templates.md](references/email-templates.md#initial-invite)). After user approves:

**Main session:**
1. **Spawn a sub-agent** with the task below → **immediately return control to main session**
   Tell user: "邀请邮件正在后台发送，发送完毕后将自动开始轮询回复。"
   (Sub-agent result will auto-announce back to this session when done.)

**Sub-agent task (send invites & start polling, runs in background):**

```
You are the meeting-scheduler invite-sender agent for meeting <id>.

State file: ~/.openclaw/workspace/meetings/mtg-<id>.json
Skill dir: <skill_dir>

Steps:
1. Read state file to get: participants, subject, email_tool, organizer, proposed_slots, duration_minutes, timezone, description

2. Send invitation email to EACH participant individually via detected email tool.
   Use `email_tool` from state to pick the right command:

   **gog:**
   gog gmail send --to "<email>" --subject "<subject>" --body "<invite_body>" --json

   **himalaya:**
   himalaya message write --to "<email>" --subject "<subject>" -- "<invite_body>"

   After each send, record `thread_id` / `message_id` per participant in state:
   python3 <skill_dir>/scripts/meeting_state.py update_participant <id> <email> \
     '{"thread_id": "<thread_id>", "last_sent_at": "<ISO now>", "status": "waiting_reply",
       "conversation_history": [{"timestamp": "<ISO>", "direction": "sent", "content": "初始邀请", "round": 1}],
       "rounds": 1}'

3. Update state:
   python3 <skill_dir>/scripts/meeting_state.py update <id> '{"status": "negotiating"}'

4. Create scheduled polling task via `create_scheduled_task` tool:
   - `taskId`: `mtg-poll-<id>`
   - `cronExpression`: `* * * * *`
   - `description`: `Poll email replies for meeting <subject>`
   - `prompt`:
     Step 1 — Run pre-check:
     python3 <skill_dir>/scripts/check_new_replies.py --state ~/.openclaw/workspace/meetings/mtg-<id>.json

     Step 2 — Parse the output. Find the line after "---JSON---" and parse as JSON.
     - If "action" is "none": respond with NO_REPLY. Stop immediately.
     - If "action" is "process": continue to Step 3.
     Note: the pre-check script has already set poll_busy=true in the state file.

     Step 3 — Execute negotiation for reason "<reason from JSON>":
     Read <skill_dir>/references/negotiation-logic.md and execute the negotiation logic.
     Use the reason from the JSON to determine which path to follow (see Entry Point table in negotiation-logic.md).
     For "new_replies": use the message_ids from the JSON output to fetch full message bodies — do NOT re-scan threads.
     State file: ~/.openclaw/workspace/meetings/mtg-<id>.json

     Step 4 — Clear busy flag when done:
     python3 <skill_dir>/scripts/meeting_state.py update <id> '{"poll_busy": false, "poll_busy_since": null}'

   Then update state: `{"poll_task_id": "mtg-poll-<id>"}`

5. Output final summary (auto-announced to main session):
   "📨 会议「<subject>」的邀请邮件已全部发送（共 <N> 人），开始等待回复。"
   If ANY email failed to send: include which participants failed, so user can retry manually.
```

---

## Phase 3 — Background Polling (Autonomous)

Managed by OpenClaw scheduled-task created in Phase 2. Each minute:
- `check_new_replies.py` runs as pre-check — if no new replies, agent replies NO_REPLY (minimal cost)
- On new reply → agent reads negotiation-logic.md and executes negotiation inline
- On all slots expired → triggers slot replenishment or escalates to organizer
- On consensus → disables scheduled-task, sets `status: "pending_final_approval"`

---

## Phase 4 — Final Confirmation

When user responds to the consensus notification:

**Main session:**
1. If `state.meeting_link` is empty:
   - `meeting_link_tool` is `"google_meet"`, `"zoom"`, or `"teams"` → skip asking; show in draft as "(会议链接将在发送前自动生成)"
   - `meeting_link_tool` is none → ask user:
     > "时间已确定（{final_agreed_slot}）。请提供会议链接（Zoom、腾讯会议、飞书、Teams 等），或回复'不需要'跳过。"
     Store reply in `state.meeting_link`.
2. Show final email draft to user for approval (see [references/email-templates.md](references/email-templates.md#final-confirmation))
3. On user approval → **spawn a sub-agent** with the task below → **immediately return control to main session**

**Sub-agent task (final confirmation, runs in background):**

```
You are the meeting-scheduler final-confirmation agent for meeting <id>.

State file: ~/.openclaw/workspace/meetings/mtg-<id>.json
Skill dir: <skill_dir>

Steps:
1. Read state file to get: organizer, participants, final_agreed_slot, duration_minutes, subject, description, email_tool, meeting_link, meeting_link_tool

2. Auto-generate meeting link if not already set. Check `meeting_link_tool` and `meeting_link_via`:
   - `meeting_link_tool == "google_meet"` and `meeting_link_via == "gog"`:
     ```
     gog calendar create primary \
       --summary "<subject>" \
       --from "<final_agreed_slot>" --to "<end_time>" \
       --attendees "<all_emails_comma_separated>" \
       --with-meet --json
     ```
     Extract `hangoutLink` → store in `state.meeting_link`
   - `meeting_link_tool == "google_meet"` and `meeting_link_via == "gcalcli"`:
     ```
     gcalcli add --title "<subject>" --when "<final_agreed_slot>" \
       --duration <duration_minutes> --conference
     ```
     Extract the Meet link from output → store in `state.meeting_link`
   - `meeting_link_tool == "zoom"`:
     ```
     zoom meeting create --topic "<subject>" --start-time "<final_agreed_slot>" --duration <duration_minutes>
     ```
     Extract join URL → store in `state.meeting_link`
   - `meeting_link_tool == "teams"` and `meeting_link_via == "mgc"`:
     ```
     mgc users online-meetings create --body '{"subject": "<subject>", "startDateTime": "<final_agreed_slot>", "endDateTime": "<end_time>"}'
     ```
     Extract `joinWebUrl` from JSON output → store in `state.meeting_link`
   - Otherwise: use `state.meeting_link` as-is (user-provided or empty)

3. Generate .ics file:
   python3 <skill_dir>/scripts/generate_ics.py \
     --output /tmp/meeting-<id>.ics \
     --uid "<id>@meeting-scheduler.openclaw" \
     --summary "<subject>" \
     --start "<final_agreed_slot>" \
     --end "<end_time>" \
     --organizer "<organizer>" \
     --attendees "<all_emails_comma_separated>" \
     --location "<meeting_link>" \
     --description "<description>"

4. Send final confirmation email to EACH participant individually (with .ics attached).
   Use `email_tool` from state to pick the right command:

   **gog:**
   ```
   gog gmail send \
     --to "<email>" \
     --subject "<subject> — 已确认：<formatted_datetime>" \
     --body "<final_confirmation_body>" \
     --attach /tmp/meeting-<id>.ics \
     --json
   ```
   **himalaya:**
   ```
   himalaya message write --to "<email>" --subject "<subject> — 已确认：<formatted_datetime>" \
     --attach /tmp/meeting-<id>.ics -- "<final_confirmation_body>"
   ```

5. Update state:
   - If ALL emails sent successfully:
     python3 <skill_dir>/scripts/meeting_state.py update <id> \
       '{"status": "confirmed", "confirmed_at": "<ISO now>"}'
   - If ANY email failed: do NOT set status to "confirmed". Instead:
     python3 <skill_dir>/scripts/meeting_state.py update <id> \
       '{"status": "needs_organizer"}'

6. Output final summary (auto-announced to main session):
   "✅ 会议「<subject>」最终邀请已发送！
   时间：<datetime>（<timezone>）
   参与者：<email list>
   会议链接：<meeting_link>"
   If ANY email failed: include which participants failed and which succeeded.
```

---

## State File

Location: `~/.openclaw/workspace/meetings/mtg-<id>.json`

```json
{
  "id": "mtg-001",
  "status": "negotiating",
  "subject": "...",
  "organizer": "...",
  "duration_minutes": 60,
  "timezone": "Asia/Shanghai",
  "description": "",
  "email_tool": "gog",
  "calendar_tool": "gog",
  "meeting_link_tool": "google_meet",
  "meeting_link_via": "gog",
  "meeting_link": "",
  "time_range_end": "2026-03-25T18:00+08:00",
  "proposed_slots": ["2026-03-18T10:00+08:00", "..."],
  "poll_task_id": "mtg-poll-abc123",
  "poll_busy": false,
  "poll_busy_since": null,
  "participants": {
    "a@example.com": {
      "name": "",
      "rounds": 1,
      "status": "waiting_reply",
      "thread_id": "...",
      "last_sent_at": "...",
      "last_replied_at": null,
      "available_slots": [],
      "maybe_slots": [],
      "soft_no_slots": [],
      "hard_no_slots": [],
      "suggested_slots": [],
      "processed_message_ids": [],
      "conversation_history": []
    }
  },
  "final_agreed_slot": null,
  "confirmed_at": null
}
```

**Status values:** `gathering_info` → `pending_approval` → `negotiating` → `pending_final_approval` → `confirmed` | `needs_organizer` | `deadlock` | `cancelled`

**Participant status values:** `waiting_reply` | `negotiating` | `agreed` | `declined` | `stalled` | `skipped`

Manage state: `python3 <skill_dir>/scripts/meeting_state.py`

---

## Sending Emails

```bash
# gog Gmail
gog gmail send --to "<email>" --subject "<subject>" --body "<body>" --json
gog gmail send --to "<email>" --subject "<subject>" --body "<body>" --attach <file> --json

# himalaya
himalaya message write --to "<email>" --subject "<subject>" -- "<body>"
```

## Reading Replies

```bash
# gog — search by thread
gog gmail thread get <thread_id> --json

# himalaya
himalaya envelope list --query "FROM <email> SUBJECT <subject>"
```

---

## Key Rules

- **Never send targeted yes/no asks to participants who haven't replied yet** — only send reminders to re-ask for initial availability
- **Immediate conflict check** among replied participants only — do not wait for others
- **Final confirmation only** when ALL participants have a common agreed slot
- **Always attach .ics** to final confirmation email — never skip this step
- **Max 5 rounds per participant** — if exceeded, escalate to organizer
- **No-reply reminders** use dynamic urgency based on nearest remaining slot (see negotiation-logic.md)
