# Email Templates

## initial-invite

Subject: `{subject} — 请确认可用时间`

```
Hi,

我是 {organizer_name} 的 AI 助手（OpenClaw），正在帮他协调一次会议。

  主题：{subject}
  时长：{duration_minutes} 分钟
  {description_line}

请从以下时间段中选出您**所有**可以参加的选项，直接回复字母即可：

  A. {slot_A}
  B. {slot_B}
  C. {slot_C}
  ...

例如回复："A C E" 表示这三个时间都可以。

如果以上时间段都不合适，请告知您方便的时间，我来协调。

（所有时间均为 {timezone}）

代 {organizer_name} 发送（OpenClaw AI 助手）
```

**Slot labeling:** use A, B, C, D... for up to 10 slots. Format each slot as:
`周X  YYYY年MM月DD日  HH:MM – HH:MM`

**Parsing replies:**
- Letters selected (e.g. "A C E") → map to slots → mark as `yes`
- Unmentioned slots → mark as `no` (participant saw all options, silence = unavailable)
- Participant suggests own time → extract datetime, add to `proposed_slots`, mark suggested slot as `yes`
- "都不行" / "以上都不合适" with no suggestion → mark all as `hard_no`, set participant `status: "declined"`

`{description_line}` → omit if empty

---

## follow-up-negotiation

Subject: `Re: {subject} — 协调时间`

```
Hi,

感谢您的回复！其他参与者都可以 {best_slot}，请问您能调整到这个时间吗？

  {best_slot}（{timezone}）

请直接回复"可以"或"不行"即可。如果不行，请告知您最近可用的时间段，我来帮您协调。

代 {organizer_name} 发送（OpenClaw AI 助手）
```

**Key:** this is a single targeted ask (yes/no), not a new multi-option poll.
Only send to participants in `unavailable_for_best`. Never re-send to those who already said yes.

---

## reminder

Subject: `Re: {subject} — 请确认可用时间`

```
Hi,

我是 {organizer_name} 的 AI 助手（OpenClaw），想跟进一下之前发送的会议时间协调邮件。

请问您能从之前列出的时间段中选择一个吗？大家都在等待您的回复，希望尽快确定时间。

  {original_slot_list}

如果以上时间均不合适，请告知您方便的时段，我来协调。

代 {organizer_name} 发送（OpenClaw AI 助手）
```

---

## final-confirmation

Subject: `{subject} — 已确认：{datetime}`

```
Hi,

很高兴大家都找到了共同时间！会议详情如下：

  主题：{subject}
  时间：{datetime}（{timezone}）
  时长：{duration_minutes} 分钟
  {meeting_link_line}
  {description_section}

已附上日历邀请文件（.ics），直接打开即可添加到您的日历。

期待与大家的会议！
```

`{meeting_link_line}` → omit if empty, else: `会议链接：{meeting_link}`

`{description_section}` → omit if empty, else:
```
议程：
{description}
```

**Attachment:** always include the generated `/tmp/meeting-<id>.ics` file.
All major calendar clients (Gmail, Outlook, Apple Calendar, QQ Mail) will render it as a one-click calendar invite.
