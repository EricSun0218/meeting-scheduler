#!/usr/bin/env python3
"""
Detect available email, calendar, and meeting link tools.
Outputs JSON with discovered capabilities.
"""
import json
import platform
import subprocess
import shutil


def run(cmd, timeout=5):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception:
        return False, "", ""


# ── Caches ────────────────────────────────────────────────────────────────

def _check_gog_calendar():
    """Check gog calendar access (cached)."""
    if not hasattr(_check_gog_calendar, "_result"):
        _check_gog_calendar._result = (
            shutil.which("gog") is not None and run("gog calendar list --limit 1")[0]
        )
    return _check_gog_calendar._result


def _check_gcalcli():
    """Check gcalcli access (cached)."""
    if not hasattr(_check_gcalcli, "_result"):
        _check_gcalcli._result = (
            shutil.which("gcalcli") is not None and run("gcalcli list")[0]
        )
    return _check_gcalcli._result


# ── Email ─────────────────────────────────────────────────────────────────

def detect_email_tools():
    tools = []

    # gog (Google Workspace CLI — Gmail)
    if shutil.which("gog"):
        ok, _, _ = run("gog auth status")
        tools.append({
            "name": "gog",
            "provider": "gmail",
            "auth_ok": ok,
        })

    # himalaya (IMAP/SMTP)
    if shutil.which("himalaya"):
        ok, out, _ = run("himalaya account list")
        if ok:
            accounts = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("#")]
            tools.append({
                "name": "himalaya",
                "provider": "imap_smtp",
                "accounts": accounts,
                "auth_ok": True,
            })

    return tools


# ── Calendar (read-only: used for slot generation) ────────────────────────

def detect_calendar_tools():
    """Detect calendar tools for READ-ONLY use (slot generation only, no event creation)."""
    tools = []

    # gog — Google Calendar
    if _check_gog_calendar():
        tools.append({
            "name": "gog",
            "provider": "google_calendar",
            "use": "read_only",
            "read_cmd": "gog calendar events --from <start> --to <end> --json",
        })

    # gcalcli — Google Calendar (alternative CLI)
    if _check_gcalcli():
        tools.append({
            "name": "gcalcli",
            "provider": "google_calendar",
            "use": "read_only",
            "read_cmd": "gcalcli agenda <start> <end> --nocolor --tsv",
        })

    # icalBuddy — macOS Calendar (reads Apple Calendar / CalDAV accounts)
    if platform.system() == "Darwin" and shutil.which("icalBuddy"):
        ok, _, _ = run("icalBuddy -n eventsToday")
        if ok:
            tools.append({
                "name": "icalBuddy",
                "provider": "apple_calendar",
                "use": "read_only",
                "read_cmd": "icalBuddy -f -nc -nrd -df '%Y-%m-%d' -tf '%H:%M' eventsFrom:<start> to:<end>",
            })

    # khal — CalDAV terminal calendar
    if shutil.which("khal"):
        ok, _, _ = run("khal list today today")
        if ok:
            tools.append({
                "name": "khal",
                "provider": "caldav",
                "use": "read_only",
                "read_cmd": "khal list <start> <end> -df '{start-date}' -f '{start-time} {end-time} {title}'",
            })

    return tools


# ── Meeting link (auto-generation) ────────────────────────────────────────

def detect_meeting_link_tools():
    """Detect tools that can auto-generate a meeting link."""
    tools = []

    # Google Meet via gog (calendar create with --with-meet)
    if _check_gog_calendar():
        tools.append({
            "name": "google_meet",
            "via": "gog",
            "create_cmd": "gog calendar create primary --summary <subject> --from <start> --to <end> --attendees <emails> --with-meet --json",
        })

    # Google Meet via gcalcli (alternative)
    if not _check_gog_calendar() and _check_gcalcli():
        tools.append({
            "name": "google_meet",
            "via": "gcalcli",
            "create_cmd": "gcalcli add --title <subject> --when <start> --duration <minutes> --conference",
        })

    # Zoom via CLI
    if shutil.which("zoom"):
        tools.append({
            "name": "zoom",
            "via": "zoom_cli",
            "create_cmd": "zoom meeting create --topic <subject> --start-time <start> --duration <minutes>",
        })

    # Microsoft Teams via Microsoft Graph CLI
    if shutil.which("mgc"):
        ok, _, _ = run("mgc me get")
        if ok:
            tools.append({
                "name": "teams",
                "via": "mgc",
                "create_cmd": "mgc users online-meetings create --body '{\"subject\": \"<subject>\", \"startDateTime\": \"<start>\", \"endDateTime\": \"<end>\"}'",
            })

    return tools


if __name__ == "__main__":
    result = {
        "email_tools": detect_email_tools(),
        "calendar_tools": detect_calendar_tools(),
        "meeting_link_tools": detect_meeting_link_tools(),
    }
    print(json.dumps(result, indent=2))
