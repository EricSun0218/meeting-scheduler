# Meeting Scheduler — OpenClaw Skill

An autonomous meeting scheduling skill for [OpenClaw](https://openclaw.ai). Sends email invitations, negotiates availability across multiple participants via multi-round email exchange, and delivers final calendar invites with `.ics` attachments — all in the background.

## Features

- 📧 **Multi-provider email** — Gmail (via `gog`) and any IMAP/SMTP mailbox (via `himalaya`)
- 🗓️ **Calendar-aware slot generation** — reads organizer's existing events to avoid conflicts
- 🤖 **Autonomous negotiation** — handles multi-round back-and-forth with participants
- 📎 **Universal `.ics` delivery** — works with Gmail, Outlook, Apple Mail, QQ Mail, and any calendar client
- 🔗 **Auto meeting links** — Google Meet, Zoom, or Microsoft Teams
- ⏰ **Smart reminders** — dynamic urgency-based follow-ups
- 🔒 **Concurrency-safe** — poll_busy guard prevents duplicate negotiation runs

## How It Works

1. User says "schedule a meeting with X and Y"
2. Agent collects details (subject, duration, time range) and drafts invitations → **user approves**
3. Sub-agent sends emails in background, starts polling for replies every minute
4. Replies are parsed automatically; agent negotiates until all participants agree on a slot
5. Agent presents final confirmation → **user approves**
6. Sub-agent sends `.ics` confirmation emails and creates calendar event with meeting link

Only **two user approvals** required. Everything else runs autonomously.

## Requirements

**Email (at least one):**
- [`gog`](https://github.com/neilotoole/sq) — Gmail / Google Workspace
- [`himalaya`](https://github.com/soywod/himalaya) — any IMAP/SMTP mailbox

**Calendar (optional, for smarter slot generation):**
- `gog` (Google Calendar)
- `gcalcli`
- `icalBuddy` (macOS)
- `khal`

**Meeting links (optional):**
- `gog` → Google Meet
- `zoom` CLI → Zoom
- `mgc` (Microsoft Graph CLI) → Teams

## Installation

```bash
clawhub install meeting-scheduler
```

Or manually copy this directory into your OpenClaw workspace skills folder:

```bash
cp -r meeting-scheduler ~/.openclaw/workspace/skills/
```

## File Structure

```
meeting-scheduler/
├── SKILL.md                    # Skill definition and instructions
├── scripts/
│   ├── detect_env.py           # Detect available email/calendar tools
│   ├── meeting_state.py        # State file management
│   ├── check_new_replies.py    # Poll for new email replies
│   ├── compute_optimal_slot.py # Borda cost algorithm for slot selection
│   └── generate_ics.py         # Generate .ics calendar files
└── references/
    ├── negotiation-logic.md    # Full negotiation decision tree
    ├── email-templates.md      # Email templates
    └── email-setup.md          # Email tool setup guide
```

## State Files

Meeting state is stored in `~/.openclaw/workspace/meetings/mtg-<id>.json`. Each meeting tracks participants, proposed slots, reply history, and negotiation status.

## License

MIT
