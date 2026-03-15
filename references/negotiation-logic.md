# Negotiation Logic (Background Polling Agent)

This file is read by the scheduled-task agent running the background poll loop.

## Entry Point

Load state file:
```bash
python3 <skill_dir>/scripts/meeting_state.py get <meeting_id>
```

Skip (exit silently) if `status` is not `negotiating`.

The pre-check script (`check_new_replies.py`) has already determined the `reason` for this execution. Use the reason from the JSON output to determine which path to follow:

| reason | action |
|--------|--------|
| `new_replies` | Go to Step 2 (use `new_replies` from JSON for message IDs) |
| `all_slots_expired` | Go to [Slot Replenishment](#slot-replenishment) |
| `all_slots_expired_range_ended` | Go to [Escalate to Organizer](#escalate-to-organizer) (reason: 时间范围已过期) |
| `reminders_due` | Go to [No-Reply Reminders](#no-reply-reminders) (send reminders to participants listed in `reminders_due`) |
| `urgency_escalation` | Go to [Escalate to Organizer](#escalate-to-organizer) (reason: 距最近时间段不足6小时，仍有参与者未回复) |

---

## Poll Loop (per execution)

### Step 1 — Expire stale slots

Remove any proposed slot that has already passed current time:
```python
remaining_slots = [s for s in state["proposed_slots"] if s > now_iso]
```
Update `proposed_slots` in state if any were removed.

If `remaining_slots` is empty → go to [Slot Replenishment](#slot-replenishment).

### Step 2 — Fetch full reply content

The pre-check JSON includes `new_replies` with `message_id` for each new message. Use these IDs to fetch full message bodies:

```bash
# gog Gmail — fetch full body by message ID (from pre-check output)
gog gmail messages get <messageId> --json
```

Do NOT re-scan the thread — the pre-check already identified which messages are new.

### Step 3 — Parse the reply

**Structured format (letters: "A C E"):**
- Letters mentioned → map to slot datetimes → mark as `yes` in `available_slots`
- Letters NOT mentioned → mark as `soft_no` in `soft_no_slots`

**Participant suggests own time (all slots rejected):**
- Extract suggested datetime(s), add to `proposed_slots` and `suggested_slots`
- Mark suggested slots as `yes` in `available_slots` for this participant
- Mark all original slots as `hard_no` in `hard_no_slots`

**Natural language fallback:**
- "可以/行/OK" + slot reference → `yes` → add to `available_slots`
- "不行/没空/有事" → `hard_no` → add to `hard_no_slots`
- "应该可以/尽量/勉强" → `maybe` → add to `maybe_slots`

Update participant state:
```bash
python3 <skill_dir>/scripts/meeting_state.py update_participant <id> <email> \
  '{"last_replied_at": "<ISO now>", "status": "negotiating",
    "available_slots": [...], "maybe_slots": [...],
    "soft_no_slots": [...], "hard_no_slots": [...], "suggested_slots": [...],
    "processed_message_ids": [<existing IDs>, <new message IDs>],
    "conversation_history": [<existing entries>, {"timestamp": "<ISO>", "direction": "received", "content": "<reply summary>", "round": <rounds>}]}'
```

If participant declines ALL slots AND suggests no alternative → set `status: "declined"`.

### Step 4 — Run optimal slot computation

```bash
python3 <skill_dir>/scripts/compute_optimal_slot.py \
  --state ~/.openclaw/workspace/meetings/mtg-<id>.json
```

Act on the result per the Decision Tree below.

---

## Decision Tree

### Case A — `status: "perfect"` (cost == 0, all replied yes)

→ **Consensus reached** → go to [Consensus Reached](#consensus-reached).

### Case B — `status: "best"`

Contact `unavailable_for_best` with a **single targeted yes/no ask**:
> "其他参与者都可以 [best_slot]，您方便在这个时间参加吗？
> 如果实在不行，请告知您方便的时间段。"

- Update: `rounds += 1`, `last_sent_at = now`, `status = "waiting_reply"`
- Record the sent message in `conversation_history`: `{"timestamp": "<ISO>", "direction": "sent", "content": "<email summary>", "round": <rounds>}`
- Do NOT re-contact participants who already said yes
- On reply: rerun compute → repeat decision tree

### Case C — `status: "needs_organizer"`

→ Go to [Escalate to Organizer](#escalate-to-organizer).

### Case D — `status: "deadlock"`

→ Go to [Deadlock](#deadlock).

---

## No-Reply Reminders

Compute urgency from the nearest remaining proposed slot:
```python
urgency_hours = (min(remaining_slots) - now).total_seconds() / 3600
```

| urgency | reminder interval | extra action |
|---------|------------------|--------------|
| > 72h   | every 24h        | — |
| 24–72h  | every 12h        | — |
| 6–24h   | every 6h         | notify organizer: "X 尚未回复" |
| < 6h    | stop reminders   | → go to [Escalate to Organizer](#escalate-to-organizer) (reason: 距最近时间段不足6小时) |

**After each reminder:** `rounds += 1`, update `last_sent_at`. Record in `conversation_history`.
**If `rounds >= 5`:** set participant `status: "stalled"`, then → go to [Escalate to Organizer](#escalate-to-organizer) for this participant.

---

## Slot Replenishment

Triggered when `remaining_slots` is empty (all slots have passed) and meeting not yet confirmed.

**First check `time_range_end`:**
If `time_range_end` has passed (i.e. `time_range_end < now`) → skip calendar check, go directly to the "no calendar_tool" path below (ask organizer for new time range).

**If `calendar_tool` in state AND `time_range_end` is still in the future:**
Use the calendar tool's read command (see SKILL.md Phase 1) to fetch organizer's events:
```bash
# gog
gog calendar events --from <now> --to <time_range_end> --json
# gcalcli
gcalcli agenda <now> <time_range_end> --nocolor --tsv
# icalBuddy
icalBuddy -f -nc -nrd -df '%Y-%m-%d' -tf '%H:%M' eventsFrom:<now> to:<time_range_end>
# khal
khal list <now> <time_range_end> -df '{start-date}' -f '{start-time} {end-time} {title}'
```
Parse busy times, compute free gaps, pick 5 new slots.
Add to `proposed_slots`, send new invite round (same structured A/B/C format as initial invite).
Notify organizer: "候选时间已过期，已根据您的日历自动补充新的候选时段，继续协商中。"

**If no `calendar_tool` OR `time_range_end` has passed:**
Disable the polling task (if `poll_task_id` is set) and update state:
```
If state.poll_task_id is not empty:
  Use `update_scheduled_task` tool: taskId = state.poll_task_id, enabled = false
```
```bash
python3 <skill_dir>/scripts/meeting_state.py update <id> \
  '{"status": "needs_organizer", "poll_busy": false, "poll_busy_since": null}'
```
Notify organizer:
```
⚠️ 会议「{subject}」的所有候选时间已过期。
请提供新的时间范围或候选时间段以继续协商。
```

---

## Escalate to Organizer

Triggered when:
- `all_slots_have_hard_no: true` (no slot is free of vetoes)
- A participant's `rounds >= 5` (set that participant `status: "stalled"` first)
- No-reply urgency < 6h
- `time_range_end` has passed with all slots expired
- Pre-check reason is `urgency_escalation` or `all_slots_expired_range_ended`

**Action:**
1. Disable the polling task (if `poll_task_id` is set) and update state:
```
If state.poll_task_id is not empty:
  Use `update_scheduled_task` tool: taskId = state.poll_task_id, enabled = false
```
```bash
python3 <skill_dir>/scripts/meeting_state.py update <id> \
  '{"status": "needs_organizer", "poll_busy": false, "poll_busy_since": null}'
```
2. Notify organizer:

```
⚠️ 会议「{subject}」需要您介入。

原因：{reason}
算法推荐（冲突最少）：{best_slot}（{len(hard_no_for_best)} 人明确拒绝）

各参与者现状：
  • {email}：可接受 {available_slots or "无"}，已拒绝 {hard_no_slots}
  • {email}：尚未回复（已发 {rounds} 次）

请选择：
  A. 强制使用 {best_slot}
  B. 提供新的候选时间段重新协商
  C. 忽略 {stalled_or_unreplied_participants}，按现有回复继续
  D. 取消本次会议
```

**On organizer reply:**
- **A（强制）** → skip negotiation, set `final_agreed_slot = best_slot`, go to pending_final_approval
- **B（新时间段）** → add new slots to `proposed_slots`, re-enable polling task if `poll_task_id` is set via `update_scheduled_task` tool (taskId = state.poll_task_id, enabled = true), update `{"status": "negotiating"}`
- **C（忽略某人）** → set that participant `status: "skipped"`, rerun compute (skipped excluded from scoring), re-enable polling task if result is not perfect via `update_scheduled_task` (taskId = state.poll_task_id, enabled = true)
- **D（取消）** → set `status: "cancelled"`, notify all participants

---

## Skipped Participants

When organizer chooses to ignore a participant:
```bash
python3 <skill_dir>/scripts/meeting_state.py update_participant <id> <email> \
  '{"status": "skipped"}'
```

- Excluded from `compute_optimal_slot` scoring entirely
- Still receive the final confirmation email (they were invited)
- Their non-response is noted in the final email:
  > "（注：{email} 未确认参与）"

---

## Consensus Reached

When `compute_optimal_slot` returns `status: "perfect"` AND all non-skipped, non-declined participants have replied:

1. Set all participants who have `best_slot` in `available_slots` to `status: "agreed"`:
```bash
python3 <skill_dir>/scripts/meeting_state.py update_participant <id> <email> \
  '{"status": "agreed"}'
```

2. Disable the polling task (if `poll_task_id` is set) and update state:
```
If state.poll_task_id is not empty:
  Use `update_scheduled_task` tool: taskId = state.poll_task_id, enabled = false
```
```bash
python3 <skill_dir>/scripts/meeting_state.py update <id> \
  '{"status": "pending_final_approval", "final_agreed_slot": "<best_slot>", "poll_busy": false, "poll_busy_since": null}'
```

3. Notify organizer:
```
🗓️ 会议「{subject}」时间已协商完毕！
所有参与者均可参加：{best_slot}（{timezone}）
请确认后发送最终邀请。
```

---

## Deadlock

Triggered when `deadlock_reason: "all_declined"` or `"all_slots_exhausted"` or `"max_rounds_all"`.

1. Disable the polling task (if `poll_task_id` is set) and update state:
```
If state.poll_task_id is not empty:
  Use `update_scheduled_task` tool: taskId = state.poll_task_id, enabled = false
```
```bash
python3 <skill_dir>/scripts/meeting_state.py update <id> \
  '{"status": "deadlock", "poll_busy": false, "poll_busy_since": null}'
```
2. Notify organizer:
```
⚠️ 会议「{subject}」无法完成协商。
原因：{deadlock_reason}
建议：扩大时间范围 / 强制指定时间 / 取消
```

---

## Notifying the User

Scheduled-task agents notify the user by outputting a clear message as their final response.
The scheduled-task system will deliver this to the user automatically.

Simply output the notification text (e.g. consensus reached, escalation needed) as the agent's response.
Do NOT attempt to use `sessions_send`, `message`, or other tools to notify — just output the message.

---

## Participant Status Values

| Status | Meaning |
|--------|---------|
| `waiting_reply` | Invite/follow-up sent, no reply yet |
| `negotiating` | Reply received, processing availability |
| `agreed` | Confirmed available for the final agreed slot |
| `declined` | Explicitly declined all, no alternative |
| `stalled` | Max rounds (5) exceeded, awaiting organizer decision |
| `skipped` | Organizer chose to proceed without this person |

---

## Logging

All sent/received interactions should be recorded in each participant's `conversation_history`:

```json
{"timestamp": "<ISO>", "direction": "sent|received", "content": "<summary>", "round": 2}
```

Add entries when:
- Sending initial invite, follow-up, or reminder (`direction: "sent"`)
- Processing a reply (`direction: "received"`)
