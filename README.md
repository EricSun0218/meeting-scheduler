<div align="center">

# Meeting Scheduler — OpenClaw Skill

**The other side never has to install anything. Email is the protocol.**

An autonomous meeting scheduling skill for [OpenClaw](https://openclaw.ai). Sends invitations, negotiates availability across multiple participants over multi-round email, and delivers calendar invites with `.ics` attachments — all running in the background after just two human approvals.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-skill-blue)](https://openclaw.ai)
[![Multi-provider](https://img.shields.io/badge/email-Gmail%20%2B%20IMAP%2FSMTP-orange)](#requirements)

[简体中文](README.zh-CN.md)

</div>

---

## TL;DR

You: *"Schedule a 30-minute call with Alice and Bob next week, around the new pricing."*

The skill drafts the invitations, you approve once. From that moment, it runs in the background:

- Sends emails to Alice and Bob (in your name, from your inbox).
- Polls every minute for replies.
- Parses their availability — even if they wrote it in prose ("Tuesday afternoon works, but not after 4").
- Negotiates back and forth automatically until everyone converges on a slot.
- Drops a final confirmation in front of you. You approve once more.
- Sends `.ics` files + auto-generates a Google Meet / Zoom / Teams link, calendar invites land in everyone's inbox.

**Two approvals. Zero context-switching. Works with anyone — they just need email.**

---

## The Insight

Every existing scheduler (Calendly, x.ai, Reclaim, Motion) has the same fatal limitation: **the other side has to use your tool**. Send a Calendly link to a senior exec at another company, and half the time you get a reply asking "can you just propose three times?"

> **Email is the only universal scheduling protocol that already exists.**

Meeting Scheduler doesn't try to invent a new protocol or convince anyone to install anything. It speaks email — the way humans already speak email — and uses an LLM to do the parsing, the negotiation, and the slot selection. From the recipient's perspective, they're just answering an unusually polite email about meeting times.

The product isn't *automation*. It's **AI-mediated negotiation** that fits inside the inbox everyone already lives in.

---

## Real-World Scenarios

**1. Cross-company sales calls.**
The buyer won't install your scheduling tool. They reply in prose: "Wednesday morning before 11, or Thursday after lunch." The skill parses, intersects with the seller's calendar, picks a slot, and confirms — without anyone learning a new tool.

**2. Multi-stakeholder internal meetings.**
Five people, four time zones, two of them on PTO next week. Manually doing this Doodle is an hour of work. Here it's a single approval and a 5-minute background poll.

**3. Recruiting coordination at scale.**
A hiring manager runs 10 candidate intros a week. Each is a 4-message email exchange. The skill collapses each one to two clicks.

---

## How It Works

```
1. User: "Schedule a meeting with X and Y."
        │
        ▼
2. Agent gathers context (subject, duration, time range)
   reads organizer's calendar to avoid conflicts
   drafts initial invitations
        │
        ▼
3. ⏸  USER APPROVES — first of two checkpoints
        │
        ▼
4. Sub-agent runs in background:
   ├─ sends emails via gog (Gmail) or himalaya (IMAP/SMTP)
   ├─ polls inbox every minute (concurrency-safe guard)
   ├─ parses replies (LLM, prose-tolerant)
   ├─ runs Borda-cost slot selection across all responses
   └─ sends follow-ups when needed (urgency-tuned reminders)
        │
        ▼
5. Convergence detected → final slot proposed to user
        │
        ▼
6. ⏸  USER APPROVES — second of two checkpoints
        │
        ▼
7. Sub-agent sends .ics confirmations + creates calendar event
   with auto-generated meeting link (Meet / Zoom / Teams)
```

Meeting state lives in `~/.openclaw/workspace/meetings/mtg-<id>.json` so the skill can resume after a restart.

---

## Key Design Decisions

**1. Two-and-only-two human approvals.**
The temptation is to ask the user every time something is uncertain — "Alice replied with two slot options, which one do you prefer?" That defeats the entire purpose. The skill makes those decisions itself using a Borda-cost algorithm and only interrupts the user at the two moments that have *legal* weight: sending email in their name, and committing to a calendar slot. Autonomy is the product.

**2. Multi-provider email abstraction (Gmail + any IMAP/SMTP).**
Many scheduling tools require Google Workspace. Real users have a mix of Gmail, Outlook, custom company SMTP, and even QQ Mail. By abstracting over `gog` (Gmail) and `himalaya` (universal IMAP/SMTP), the skill works with whatever the user already has — no migration required.

**3. `.ics` files, not vendor calendar APIs.**
We could integrate Google Calendar API and skip `.ics` entirely. We don't, because the recipient's calendar is *not* the same as the organizer's. A `.ics` attachment is the only universal calendar invite — Apple Mail, Outlook, QQ Mail, every client renders it natively. Vendor APIs would lock the product into one ecosystem.

**4. Concurrency-safe poll guard.**
`poll_busy` prevents two negotiation runs from racing on the same meeting. This is a small, unsexy detail that comes from real production thinking: when a user has multiple meetings being scheduled in parallel, or when a wake-up timer fires while a previous run is still mid-LLM call, naive polling causes duplicate emails. The guard is one of the boring features that separates a demo from a product.

**5. LLM parses prose replies, not a structured form.**
A scheduling form would force the recipient to fill in slots in a specific format. Instead, the skill expects them to write *however they normally write* ("anytime Tuesday morning, but not before 9, and not the 11–11:30 slot — that one I have a recurring"), and lets the LLM extract structure. Recipient burden = zero.

---

## Get Started

```bash
clawhub install meeting-scheduler
```

Or copy the skill directly into your OpenClaw workspace:

```bash
cp -r meeting-scheduler ~/.openclaw/workspace/skills/
```

Then in any OpenClaw chat:

> *"Schedule a 30-minute call with alice@example.com and bob@example.com next week, around the new pricing proposal."*

---

## Roadmap

The vision: cross-company, multi-party meeting negotiation that feels like having a human EA — but works for everyone, not just executives.

| Status | Feature |
|---|---|
| ✅ shipped | Multi-round email negotiation |
| ✅ shipped | Multi-provider email (Gmail + IMAP/SMTP) |
| ✅ shipped | `.ics` delivery + auto Meet/Zoom/Teams links |
| ✅ shipped | Calendar-aware slot generation |
| ✅ shipped | Concurrency-safe polling |
| 🚧 next | Recurring meetings + reschedules |
| 🚧 next | Group preference learning ("Bob hates Monday mornings") |
| 🔭 future | Voice-driven scheduling ("schedule the QBR") via OpenClaw voice |
| 🔭 future | Negotiation transparency mode — recipients opt in to know they're talking to an AI |

---

## Related Work

| | What it does | How Meeting Scheduler differs |
|---|---|---|
| **Calendly / x.ai / SavvyCal** | Hosted scheduling links | Requires the recipient to use your tool. Meeting Scheduler requires only that they have email. |
| **Google Calendar invite + "find a time"** | Single-shot proposal | No negotiation. If the first slot doesn't work, the user is back to manual coordination. |
| **Asking ChatGPT/Claude to draft an email** | One email at a time | No background polling, no `.ics` generation, no concurrency safety, no calendar integration. |
| **Zapier / Make scheduling automations** | Rule-based pipelines | Can't parse prose replies or negotiate. Falls apart when a recipient writes anything off-script. |

---

## Requirements

**Email (at least one):**
- [`gog`](https://gogcli.sh) — Gmail / Google Workspace
- [`himalaya`](https://github.com/soywod/himalaya) — any IMAP/SMTP mailbox

**Calendar (optional, for smarter slot generation):**
- `gog` (Google Calendar) · `gcalcli` · `icalBuddy` (macOS) · `khal`

**Meeting links (optional):**
- `gog` → Google Meet · `zoom` CLI → Zoom · `mgc` (Microsoft Graph CLI) → Teams

## File Structure

```
meeting-scheduler/
├── SKILL.md                    # Skill definition and instructions
├── scripts/
│   ├── detect_env.py           # Detect available email/calendar tools
│   ├── meeting_state.py        # State file management
│   ├── check_new_replies.py    # Poll for new email replies
│   ├── compute_optimal_slot.py # Borda-cost slot selection
│   └── generate_ics.py         # Generate .ics calendar files
└── references/
    ├── negotiation-logic.md
    ├── email-templates.md
    └── email-setup.md
```

## License

MIT
