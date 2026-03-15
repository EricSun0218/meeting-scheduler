# Meeting Platform Setup

## google-meet

Google Meet links are generated automatically via the `gog` Google Calendar integration.

**Prerequisite:** `gog` must be authenticated with Google Calendar scope.

**Setup:**
1. Ensure gog is installed and authenticated: `gog auth login`
2. Verify Calendar access: `gog calendar list --limit 1`

**Generate a Meet link:**
```bash
gog calendar create primary \
  --summary "<meeting title>" \
  --from "<ISO datetime start>" \
  --to "<ISO datetime end>" \
  --attendees "<email1>,<email2>" \
  --with-meet --json
```

Output includes `hangoutLink` field with the Google Meet URL.

---

## zoom

**Option 1 — Zoom OAuth App (recommended)**

1. Go to https://marketplace.zoom.us/ → Build App → OAuth
2. Add scopes: `meeting:write`
3. Set `ZOOM_CLIENT_ID` and `ZOOM_CLIENT_SECRET` in environment
4. Authenticate once: follow Zoom OAuth flow

**Create a Zoom meeting via API:**
```bash
curl -s -X POST "https://api.zoom.us/v2/users/me/meetings" \
  -H "Authorization: Bearer $ZOOM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "<title>",
    "type": 2,
    "start_time": "<ISO datetime>",
    "duration": <minutes>,
    "timezone": "<timezone>"
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['join_url'])"
```

**Option 2 — Personal Meeting Room**

If you only use your Personal Meeting Room link, just provide it manually when prompted.

---

## microsoft-teams

No CLI support currently. Use manual link option:
- Schedule in Teams calendar
- Copy the "Join Microsoft Teams Meeting" link
- Paste when prompted by the skill
