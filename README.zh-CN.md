<div align="center">

# Meeting Scheduler — OpenClaw Skill

**对方什么都不用装。邮件就是协议。**

[OpenClaw](https://openclaw.ai) 的自动会议调度 skill。在你说一句话后，它自动发邀请、用多轮邮件协商所有参与者的可用时间、生成 `.ics` 邀请和会议链接——全程后台运行，只需要你两次确认。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-skill-blue)](https://openclaw.ai)
[![Multi-provider](https://img.shields.io/badge/email-Gmail%20%2B%20IMAP%2FSMTP-orange)](#要求)

[English](README.md)

</div>

---

## TL;DR

你说：*"约 Alice 和 Bob 下周开个 30 分钟的会，聊新定价。"*

skill 起草邀请，你确认一次。从这一刻起，全程后台跑：

- 用你的邮箱给 Alice 和 Bob 各发一封邀请。
- 每分钟 poll 一次，等回信。
- 解析他们的可用时间——哪怕他们写的是大白话（"周二下午可以，但 4 点之后不行"）。
- 自动多轮协商，直到所有人都收敛到同一个时间段。
- 把最终结果摆到你面前。你再确认一次。
- 发 `.ics` 文件 + 自动生成 Google Meet / Zoom / Teams 链接。日历邀请落到每个人的邮箱。

**两次确认。零上下文切换。任何人都能用——他们只需要有邮箱。**

---

## 核心洞察

所有现存的调度工具（Calendly、x.ai、Reclaim、Motion）都有同一个致命缺陷：**对方必须用你的工具**。给一个外公司高管发 Calendly 链接，一半的概率你会收到回信"能不能直接发我三个时间？"

> **邮件，是世界上唯一已经存在的、通用的会议调度协议。**

Meeting Scheduler 不打算发明新协议，也不打算说服任何人安装任何东西。它**说邮件**——按人类已经在写邮件的方式——用 LLM 来做解析、谈判、和时间选择。在收件人视角里，他们只是在回一封"措辞特别礼貌"的、问开会时间的邮件而已。

产品的本质不是"自动化"，而是**装在收件箱里的 AI 谈判员**。

---

## 真实使用场景

**1. 跨公司销售会议。**
买方不会装你的调度工具。他们用大白话回："周三上午 11 点前，或周四午饭之后。"skill 解析这段话，与卖方日历求交集，选出一个时间，发出确认——全程没有人需要学新工具。

**2. 多人内部会议。**
五个人、四个时区、两个人下周休假。手动 Doodle 一小时。这里是一次确认 + 5 分钟后台 poll。

**3. 招聘协调。**
HR 一周要约 10 个候选人，每个 4 封邮件来回。skill 把每一个收敛成两次点击。

---

## 工作机制

```
1. 用户："约 X 和 Y 开个会。"
        │
        ▼
2. Agent 收集上下文（主题、时长、时间范围），
   读 organizer 的日历避开冲突，
   起草初版邀请
        │
        ▼
3. ⏸  用户确认 —— 两个 checkpoint 之一
        │
        ▼
4. 子 Agent 后台运行：
   ├─ 通过 gog (Gmail) 或 himalaya (IMAP/SMTP) 发邮件
   ├─ 每分钟 poll 收件箱（带并发安全 guard）
   ├─ 解析回复（LLM，能读懂大白话）
   ├─ 用 Borda 代价算法在所有回复中选最优时间
   └─ 必要时发追问邮件（按紧急度调节频率）
        │
        ▼
5. 检测到收敛 → 把最终时间提给用户
        │
        ▼
6. ⏸  用户确认 —— 两个 checkpoint 之二
        │
        ▼
7. 子 Agent 发 .ics 确认 + 创建带会议链接的日历事件
   （Meet / Zoom / Teams）
```

会议状态存在 `~/.openclaw/workspace/meetings/mtg-<id>.json`，重启后能恢复。

---

## 关键产品决策

**1. 严格只有两次人工确认。**
最容易掉进去的坑：每当不确定就问用户——"Alice 给了两个时间，你想选哪个？"这就把整个产品的意义打没了。skill 自己用 Borda 代价算法做这些决策，**只在两个有"法律意义"的时刻打断用户**：以你的名义发邮件、和承诺一个日历时间。"自动到什么程度"本身就是产品。

**2. 多 provider 邮件抽象（Gmail + 任意 IMAP/SMTP）。**
很多调度工具强制要 Google Workspace。真实用户用的是 Gmail / Outlook / 公司自建 SMTP / QQ 邮箱混搭。通过在 `gog` (Gmail) 和 `himalaya` (通用 IMAP/SMTP) 之上做一层抽象，skill 适配用户已经在用的东西——不需要迁移。

**3. `.ics` 文件，而不是某家厂商的 Calendar API。**
也可以集成 Google Calendar API，跳过 `.ics`。我们没这么做，因为**收件人的日历跟 organizer 的不是同一个生态**。`.ics` 附件是唯一通用的日历邀请——Apple Mail / Outlook / QQ Mail 等所有客户端都原生识别。绑死某家 API 会把产品锁死在一个生态里。

**4. 并发安全的 poll guard。**
`poll_busy` 防止同一个会议被两个协商进程同时跑。这是个不性感的细节，但来自真实生产思维：当用户同时调度多个会议，或当一个 wake-up timer 在前一次 LLM 调用还没结束时触发，朴素 poll 会导致重复邮件。**这种"无聊的功能"是 demo 和产品的分水岭。**

**5. LLM 解析大白话回复，不要求填表。**
让用户填一个结构化的"可用时间表"，对收件人来说是负担。skill 的设计是对方**怎么写邮件就怎么写**（"周二上午都可以，但 9 点之前不行，11–11:30 那段我有个固定会"），让 LLM 抽结构。**收件人负担 = 0。**

---

## 开始使用

```bash
clawhub install meeting-scheduler
```

或者直接把 skill 复制到 OpenClaw workspace：

```bash
cp -r meeting-scheduler ~/.openclaw/workspace/skills/
```

然后在任意 OpenClaw 对话里：

> *"约 alice@example.com 和 bob@example.com 下周开个 30 分钟的会，聊新定价方案。"*

---

## 路线图

终极愿景：跨公司、多方的会议谈判，体验上像有一个人类 EA——但所有人都能用，不是只有 executives。

| 状态 | 特性 |
|---|---|
| ✅ 已完成 | 多轮邮件协商 |
| ✅ 已完成 | 多 provider 邮件（Gmail + IMAP/SMTP）|
| ✅ 已完成 | `.ics` 投递 + 自动 Meet/Zoom/Teams 链接 |
| ✅ 已完成 | 日历感知的时间生成 |
| ✅ 已完成 | 并发安全的 polling |
| 🚧 下一版 | 周期性会议 + 改期 |
| 🚧 下一版 | 群体偏好学习（"Bob 讨厌周一早上"）|
| 🔭 远期 | 语音调度（"约一下 QBR"）通过 OpenClaw 语音入口 |
| 🔭 远期 | 谈判透明模式 —— 收件人可以选择性知道对方是 AI |

---

## 同类工作对比

| | 它做什么 | Meeting Scheduler 的差异 |
|---|---|---|
| **Calendly / x.ai / SavvyCal** | 托管的调度链接 | 要求收件人用你的工具。Meeting Scheduler 只要求对方有邮箱。 |
| **Google Calendar 邀请 + "查找时间"** | 一次性提议时间 | 没有协商。如果第一个时间不行，用户就回到手动协调了。 |
| **直接让 ChatGPT/Claude 帮你写邮件** | 一次写一封 | 没有后台 poll、没有 `.ics` 生成、没有并发安全、没有日历集成。 |
| **Zapier / Make 调度自动化** | 规则驱动 | 解析不了大白话，无法谈判。一旦对方写得不在剧本里就崩。 |

---

## 要求

**邮件（至少一个）：**
- [`gog`](https://gogcli.sh) —— Gmail / Google Workspace
- [`himalaya`](https://github.com/soywod/himalaya) —— 任意 IMAP/SMTP 邮箱

**日历（可选，用于更聪明的时间生成）：**
- `gog` (Google Calendar) · `gcalcli` · `icalBuddy` (macOS) · `khal`

**会议链接（可选）：**
- `gog` → Google Meet · `zoom` CLI → Zoom · `mgc` (Microsoft Graph CLI) → Teams

## 文件结构

```
meeting-scheduler/
├── SKILL.md
├── scripts/
│   ├── detect_env.py
│   ├── meeting_state.py
│   ├── check_new_replies.py
│   ├── compute_optimal_slot.py    # Borda 代价时间选择算法
│   └── generate_ics.py
└── references/
    ├── negotiation-logic.md
    ├── email-templates.md
    └── email-setup.md
```

## License

MIT
