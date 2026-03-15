#!/usr/bin/env python3
"""
Generate an iCalendar (.ics) file for a meeting.
Usage:
  generate_ics.py --output <path> \
    --uid <uid> \
    --summary <title> \
    --start <ISO8601 datetime> \
    --end <ISO8601 datetime> \
    --organizer <email> \
    --attendees <email1,email2,...> \
    [--location <url_or_text>] \
    [--description <text>] \
    [--cancel]
"""
import argparse
import sys
import re
from datetime import datetime, timezone, timedelta


def parse_dt(s):
    """Parse ISO8601 datetime (with or without seconds, with or without offset) to UTC."""
    s = s.strip()
    # Normalise: add :00 seconds if missing (e.g. 2026-03-14T10:00+08:00)
    m_no_sec = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})([+-]\d{2}:\d{2}|Z)?$', s)
    if m_no_sec:
        s = m_no_sec.group(1) + ':00' + (m_no_sec.group(2) or '')
    # Handle Z suffix
    if s.endswith('Z'):
        return datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
    # Python 3.7+ fromisoformat handles ±HH:MM offsets in 3.11+; use manual parse for compat
    m = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-])(\d{2}):(\d{2})$', s)
    if m:
        dt_str, sign, hh, mm = m.groups()
        dt = datetime.fromisoformat(dt_str)
        offset = timedelta(hours=int(hh), minutes=int(mm))
        if sign == '-':
            offset = -offset
        return (dt - offset).replace(tzinfo=timezone.utc)
    # Fallback: assume UTC
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def fmt_dt(dt):
    """Format datetime to iCalendar UTC string."""
    return dt.strftime('%Y%m%dT%H%M%SZ')


def fold(line):
    """Apply iCalendar line folding (max 75 octets per line, per RFC 5545)."""
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return line
    result = []
    first = True
    while encoded:
        limit = 75 if first else 74  # continuation lines have ' ' prefix = 1 byte
        if len(encoded) <= limit:
            result.append(encoded.decode('utf-8'))
            break
        cut = limit
        while cut > 0 and not _is_utf8_boundary(encoded, cut):
            cut -= 1
        result.append(encoded[:cut].decode('utf-8'))
        encoded = encoded[cut:]
        first = False
    return '\r\n '.join(result)


def _is_utf8_boundary(data, pos):
    """Check if pos is at a UTF-8 character boundary (not a continuation byte)."""
    if pos >= len(data):
        return True
    # UTF-8 continuation bytes start with 0b10xxxxxx
    return (data[pos] & 0xC0) != 0x80


def escape(s):
    return s.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--summary', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--organizer', required=True)
    parser.add_argument('--attendees', required=True)
    parser.add_argument('--location', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--cancel', action='store_true')
    parser.add_argument('--sequence', type=int, default=None,
                        help='SEQUENCE number (default: 0 for new, 1 for cancel)')
    args = parser.parse_args()

    start_dt = parse_dt(args.start)
    end_dt = parse_dt(args.end)
    now = datetime.now(timezone.utc)
    method = 'CANCEL' if args.cancel else 'REQUEST'
    status = 'CANCELLED' if args.cancel else 'CONFIRMED'
    seq = args.sequence if args.sequence is not None else (1 if args.cancel else 0)

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//meeting-scheduler//OpenClaw//EN',
        f'METHOD:{method}',
        'BEGIN:VEVENT',
        f'UID:{args.uid}',
        fold(f'SUMMARY:{escape(args.summary)}'),
        f'DTSTART:{fmt_dt(start_dt)}',
        f'DTEND:{fmt_dt(end_dt)}',
        f'DTSTAMP:{fmt_dt(now)}',
        fold(f'ORGANIZER;CN=Organizer:mailto:{args.organizer}'),
        f'STATUS:{status}',
        f'SEQUENCE:{seq}',
    ]

    for email in args.attendees.split(','):
        email = email.strip()
        if email:
            lines.append(fold(f'ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}'))

    if args.location:
        lines.append(fold(f'LOCATION:{escape(args.location)}'))
    if args.description:
        lines.append(fold(f'DESCRIPTION:{escape(args.description)}'))

    lines += ['END:VEVENT', 'END:VCALENDAR', '']

    with open(args.output, 'w', newline='') as f:
        f.write('\r\n'.join(lines))

    print(f'Generated: {args.output}')


if __name__ == '__main__':
    main()
