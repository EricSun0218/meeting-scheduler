# UX Copy — Standard Messaging Templates

All user-facing messages in the meeting-scheduler skill should follow these templates.
Replace `{placeholders}` with actual values at runtime.

---

## Node 2 — Invite Draft Confirmation

Show this to the user before sending any emails. Wait for explicit approval.

```
以下是会议邀请草稿，确认后将发送给所有参与者：

会议：{subject}
时长：{duration_minutes} 分钟
参与者：
  · {email1}
  · {email2}
  · …

候选时间（共 {N} 个）：
  · {slot1}（{weekday}）
  · {slot2}（{weekday}）
  · …

确认发送？
```

---

## Node 3 — Invites Sent

Show this immediately after all invitation emails are sent successfully.

```
📨 邀请已发送给 {N} 位参与者，后台已启动自动协商，无需任何操作，时间敲定后会第一时间通知你。
```

If any emails failed:
```
📨 邀请已发送给 {sent} / {total} 位参与者（{failed_emails} 发送失败），后台已启动自动协商，时间敲定后会第一时间通知你。
```

---

## Node 5 — Consensus Reached (via notify_user.py)

Triggered by signal `__MEETING_NOTIFY__:<id>:consensus` sent via `notify_user.py --event consensus`.
The main session receives the signal, reads the state file, and outputs this message as an assistant bubble.

```
🗓️ 会议「{subject}」时间已协商完毕！

确认时间：{formatted_datetime}（{timezone}）
参与者：
  · {email1} ✅
  · {email2} ✅

以下是最终确认邮件草稿：

---
主题：{subject} — 已确认：{formatted_datetime}

您好，

会议时间已确定，详情如下：

  会议主题：{subject}
  时间：{formatted_datetime}（{timezone}）
  时长：{duration_minutes} 分钟
  会议链接：{meeting_link}
  日历附件：邮件附有 .ics 文件，可直接导入日历

如有问题请随时联系。

---

确认发送？
```

Note: if `meeting_link` is not yet generated (auto-generate via gog/zoom/teams), show `（发送时自动生成）` as placeholder.

---

## Node 6 — Final Confirmation Sent (via notify_user.py)

Triggered by signal `__MEETING_NOTIFY__:<id>:confirmed` sent via `notify_user.py --event confirmed`.
The main session receives the signal, reads the state file, and outputs this message as an assistant bubble.

```
✅ 会议「{subject}」已确认！

时间：{formatted_datetime}（{timezone}）
会议链接：{meeting_link}
最终邀请（含日历附件）已发送给所有参与者。
```

---

## Escalation — Needs Organizer (via notify_user.py)

Triggered by signal `__MEETING_NOTIFY__:<id>:escalation:<reason>` sent via `notify_user.py --event escalation:<reason>`.
The main session receives the signal, reads the state file, and outputs this message as an assistant bubble.

```
⚠️ 会议「{subject}」协商遇到问题，需要你来决定：

{reason}

当前参与者状态：
  · {email1}：{status1}
  · {email2}：{status2}

建议：{suggestion}
```

---

## Formatting Rules

- Dates: `{year}年{month}月{day}日（{weekday}）{HH}:{MM}`，e.g. `2026年3月17日（周二）14:00`
- Timezone: use friendly name, e.g. `北京时间` for Asia/Shanghai
- Participant list: always use `·` bullet, one per line
- Emoji: use exactly as shown — do not add or remove
