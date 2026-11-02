from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from googleapiclient.discovery import build

from app.google_auth import GoogleAuthError, get_credentials


def _require_credentials():
    credentials = get_credentials()
    if not credentials:
        raise GoogleAuthError(
            "Google account is not connected. Ask the user to run: python oracle.py --connect-google"
        )
    return credentials


def _gmail_service():
    return build("gmail", "v1", credentials=_require_credentials(), cache_discovery=False)


def _calendar_service():
    return build("calendar", "v3", credentials=_require_credentials(), cache_discovery=False)


def _decode_body(payload: dict[str, Any]) -> str:
    data = payload.get("body", {}).get("data")
    if data:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")

    for part in payload.get("parts") or []:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain":
            part_data = part.get("body", {}).get("data")
            if part_data:
                return base64.urlsafe_b64decode(part_data.encode("utf-8")).decode(
                    "utf-8", errors="replace"
                )
    return ""


def list_recent_emails(max_results: int = 5, query: str | None = None) -> list[dict[str, Any]]:
    service = _gmail_service()
    response = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max(1, min(max_results, 20)), q=query or "in:inbox")
        .execute()
    )
    messages = response.get("messages", [])
    results: list[dict[str, Any]] = []

    for item in messages:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {
            header["name"].lower(): header["value"]
            for header in message.get("payload", {}).get("headers", [])
        }
        results.append(
            {
                "id": message["id"],
                "from": headers.get("from", "Unknown"),
                "subject": headers.get("subject", "(no subject)"),
                "date": headers.get("date", ""),
                "snippet": message.get("snippet", ""),
            }
        )

    return results


def read_email(message_id: str) -> dict[str, Any]:
    service = _gmail_service()
    message = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {
        header["name"].lower(): header["value"]
        for header in message.get("payload", {}).get("headers", [])
    }
    body = _decode_body(message.get("payload", {}))
    return {
        "id": message["id"],
        "from": headers.get("from", "Unknown"),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", "(no subject)"),
        "date": headers.get("date", ""),
        "snippet": message.get("snippet", ""),
        "body": body[:4000],
    }


def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    service = _gmail_service()
    email = EmailMessage()
    email["To"] = to
    email["Subject"] = subject
    email.set_content(body)
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode("utf-8")
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": sent["id"], "status": "sent", "to": to, "subject": subject}


def list_upcoming_events(max_results: int = 5, days_ahead: int = 7) -> list[dict[str, Any]]:
    service = _calendar_service()
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=max(1, min(days_ahead, 30)))
    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max(1, min(max_results, 20)),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = []
    for event in response.get("items", []):
        start = event.get("start", {})
        end = event.get("end", {})
        events.append(
            {
                "id": event.get("id"),
                "summary": event.get("summary", "(no title)"),
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "location": event.get("location"),
                "description": (event.get("description") or "")[:500],
            }
        )
    return events


def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    service = _calendar_service()
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    created = service.events().insert(calendarId="primary", body=body).execute()
    start = created.get("start", {})
    end = created.get("end", {})
    return {
        "id": created.get("id"),
        "summary": created.get("summary"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "htmlLink": created.get("htmlLink"),
        "status": "created",
    }


def unread_email_digest(max_results: int = 8) -> dict[str, Any]:
    emails = list_recent_emails(max_results=max_results, query="in:inbox is:unread")
    return {
        "unread_count": len(emails),
        "emails": emails,
        "summary_hint": "Summarize these unread emails briefly for a spoken briefing.",
    }


def cancel_calendar_event(event_id: str) -> dict[str, Any]:
    service = _calendar_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return {"id": event_id, "status": "cancelled"}


def update_calendar_event(
    event_id: str,
    summary: str | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    service = _calendar_service()
    existing = service.events().get(calendarId="primary", eventId=event_id).execute()

    if summary is not None:
        existing["summary"] = summary
    if description is not None:
        existing["description"] = description
    if location is not None:
        existing["location"] = location
    if start_iso is not None:
        existing["start"] = {"dateTime": start_iso}
    if end_iso is not None:
        existing["end"] = {"dateTime": end_iso}

    updated = service.events().update(
        calendarId="primary",
        eventId=event_id,
        body=existing,
    ).execute()
    start = updated.get("start", {})
    end = updated.get("end", {})
    return {
        "id": updated.get("id"),
        "summary": updated.get("summary"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "status": "updated",
    }
