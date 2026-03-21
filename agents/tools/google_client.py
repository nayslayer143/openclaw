"""
Google API client for Clawmpson — Gmail + Calendar
Tokens: ~/.openclaw/google-token.json
Refresh: automatic using stored refresh_token
"""

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

TOKEN_FILE = Path.home() / ".openclaw" / "google-token.json"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _load_tokens() -> dict:
    return json.loads(TOKEN_FILE.read_text())


def _save_tokens(tokens: dict):
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    TOKEN_FILE.chmod(0o600)


def _refresh_access_token(tokens: dict) -> dict:
    data = urllib.parse.urlencode({
        "client_id": tokens["client_id"],
        "client_secret": tokens["client_secret"],
        "refresh_token": tokens["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        new = json.loads(resp.read())
    tokens["access_token"] = new["access_token"]
    tokens["_fetched_at"] = time.time()
    _save_tokens(tokens)
    return tokens


def get_token() -> str:
    """Return a valid access token, refreshing if needed."""
    tokens = _load_tokens()
    fetched_at = tokens.get("_fetched_at", 0)
    if time.time() - fetched_at > 3400:          # refresh ~1 min before expiry
        tokens = _refresh_access_token(tokens)
    return tokens["access_token"]


def _api(method: str, url: str, body: Optional[dict] = None) -> dict:
    token = get_token()
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google API {method} {url} → {e.code}: {e.read().decode()}") from e


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def gmail_list_messages(query: str = "", max_results: int = 10) -> list:
    """List messages matching a query (Gmail search syntax)."""
    params = urllib.parse.urlencode({"q": query, "maxResults": max_results})
    result = _api("GET", f"{GMAIL_BASE}/messages?{params}")
    return result.get("messages", [])


def gmail_get_message(msg_id: str) -> dict:
    """Fetch a full message by ID."""
    return _api("GET", f"{GMAIL_BASE}/messages/{msg_id}?format=full")


def gmail_get_message_text(msg_id: str) -> dict:
    """Return subject + plain-text body for a message."""
    msg = gmail_get_message(msg_id)
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("Subject", "")
    sender = headers.get("From", "")

    # Walk parts for text/plain
    body = ""
    parts = msg["payload"].get("parts", [msg["payload"]])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            import base64
            raw = part["body"].get("data", "")
            body = base64.urlsafe_b64decode(raw + "==").decode(errors="replace")
            break

    return {"id": msg_id, "subject": subject, "from": sender, "body": body}


def gmail_send(to: str, subject: str, body: str, reply_to_id: Optional[str] = None) -> dict:
    """Send an email. Optionally thread it as a reply."""
    import base64
    from email.mime.text import MIMEText

    msg = MIMEText(body)
    msg["to"] = to
    msg["from"] = "clawdiusmaximus69@gmail.com"
    msg["subject"] = subject

    if reply_to_id:
        original = gmail_get_message(reply_to_id)
        headers = {h["name"]: h["value"] for h in original["payload"].get("headers", [])}
        msg["In-Reply-To"] = headers.get("Message-ID", "")
        msg["References"] = headers.get("Message-ID", "")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if reply_to_id:
        payload["threadId"] = original.get("threadId", "")

    return _api("POST", f"{GMAIL_BASE}/messages/send", payload)


def gmail_trash(msg_id: str) -> dict:
    """Move a message to trash."""
    return _api("POST", f"{GMAIL_BASE}/messages/{msg_id}/trash")


def gmail_label(msg_id: str, add: list[str] = None, remove: list[str] = None) -> dict:
    """Add/remove labels on a message."""
    return _api("POST", f"{GMAIL_BASE}/messages/{msg_id}/modify", {
        "addLabelIds": add or [],
        "removeLabelIds": remove or [],
    })


def gmail_mark_read(msg_id: str) -> dict:
    return gmail_label(msg_id, remove=["UNREAD"])


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

CAL_BASE = "https://www.googleapis.com/calendar/v3"


def calendar_list_events(calendar_id: str = "primary", max_results: int = 10,
                         time_min: Optional[str] = None) -> list:
    """List upcoming events. time_min is RFC3339 string e.g. '2026-03-20T00:00:00Z'."""
    if not time_min:
        time_min = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    params = urllib.parse.urlencode({
        "maxResults": max_results,
        "orderBy": "startTime",
        "singleEvents": "true",
        "timeMin": time_min,
    })
    result = _api("GET", f"{CAL_BASE}/calendars/{calendar_id}/events?{params}")
    return result.get("items", [])


def calendar_create_event(summary: str, start: str, end: str,
                          description: str = "", calendar_id: str = "primary") -> dict:
    """
    Create a calendar event.
    start/end: RFC3339 strings e.g. '2026-03-20T14:00:00-07:00'
    """
    return _api("POST", f"{CAL_BASE}/calendars/{calendar_id}/events", {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    })


def calendar_delete_event(event_id: str, calendar_id: str = "primary") -> None:
    """Delete a calendar event by ID."""
    token = get_token()
    url = f"{CAL_BASE}/calendars/{calendar_id}/events/{event_id}"
    req = urllib.request.Request(url,
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE")
    urllib.request.urlopen(req)


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing Gmail...")
    msgs = gmail_list_messages("in:inbox", max_results=3)
    print(f"  Inbox messages: {len(msgs)}")
    if msgs:
        m = gmail_get_message_text(msgs[0]["id"])
        print(f"  Latest: {m['subject']} — from {m['from']}")

    print("Testing Calendar...")
    events = calendar_list_events(max_results=3)
    print(f"  Upcoming events: {len(events)}")
    for e in events:
        start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "?"))
        print(f"  {start}: {e.get('summary', '(no title)')}")

    print("All good.")
