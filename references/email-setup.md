# Email Provider Setup

## Gmail (via gog)

1. Install gog: https://docs.openclaw.ai/skills/gog
2. Run: `gog auth login`
3. Follow OAuth flow in browser
4. Verify: `gog gmail list --limit 1`

## IMAP/SMTP (via himalaya)

1. Install: `cargo install himalaya` or download from https://github.com/soywod/himalaya
2. Configure `~/.config/himalaya/config.toml`:

```toml
[accounts.default]
email = "you@example.com"
display-name = "Your Name"

[accounts.default.folder.aliases]
inbox = "INBOX"
sent = "Sent"

[accounts.default.backend]
type = "imap"
host = "imap.example.com"
port = 993
encryption = "tls"
login = "you@example.com"
auth.type = "password"
auth.raw = "your-password"

[accounts.default.message.send.backend]
type = "smtp"
host = "smtp.example.com"
port = 587
encryption = "start-tls"
login = "you@example.com"
auth.type = "password"
auth.raw = "your-password"
```

3. Verify: `himalaya envelope list`

### Common IMAP/SMTP hosts

| Provider | IMAP host | SMTP host |
|----------|-----------|-----------|
| Gmail | imap.gmail.com:993 | smtp.gmail.com:587 |
| Outlook | outlook.office365.com:993 | smtp.office365.com:587 |
| iCloud | imap.mail.me.com:993 | smtp.mail.me.com:587 |
| 163.com | imap.163.com:993 | smtp.163.com:465 |
| QQ Mail | imap.qq.com:993 | smtp.qq.com:587 |

> For Gmail via himalaya: use an App Password (not your regular password). Generate at: https://myaccount.google.com/apppasswords
