from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.google_auth import GoogleAuthError, get_credentials


class GoogleServiceError(RuntimeError):
    """Raised when a Gmail or Calendar API call fails."""


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


def get_or_create_gmail_label(name: str) -> str:
    """Return a Gmail label id, creating the user label if necessary."""
    service = _gmail_service()
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label.get("name") == name:
            return str(label["id"])

    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return str(created["id"])


def apply_label_to_thread(thread_id: str, label_id: str) -> None:
    """Apply a user label to every message in a Gmail thread."""
    service = _gmail_service()
    service.users().threads().modify(
        userId="me",
        id=thread_id,
        body={"addLabelIds": [label_id]},
    ).execute()


def _is_rate_limit(error: HttpError) -> bool:
    status = getattr(error.resp, "status", None)
    if status in {429, 503}:
        return True
    if status != 403:
        return False
    details = str(error).lower()
    return "ratelimitexceeded" in details or "quota exceeded" in details or "userRateLimitExceeded".lower() in details


def _execute(make_request: Any, *, what: str = "Gmail request") -> Any:
    """Run a Gmail request, waiting out per-minute quota limits.

    ``make_request`` must return a fresh request each call. Gmail requests
    cannot be executed twice.
    """
    delay = 8.0
    last_error: HttpError | None = None
    for attempt in range(8):
        try:
            return make_request().execute()
        except HttpError as error:
            last_error = error
            if not _is_rate_limit(error) or attempt == 7:
                raise GoogleServiceError(f"{what} failed: {error}") from error
            wait = min(delay, 70.0)
            print(f"Gmail rate limit hit; waiting {int(wait)}s, then retrying…")
            time.sleep(wait)
            delay = min(delay * 2, 70.0)
    raise GoogleServiceError(f"{what} failed after retries: {last_error}")


def set_thread_category_label(
    thread_id: str,
    label_id: str | None,
    category_label_ids: list[str],
) -> None:
    """Replace Oracle's category labels on a Gmail thread."""
    remove_ids = [item for item in category_label_ids if item != label_id]
    body: dict[str, list[str]] = {"removeLabelIds": remove_ids}
    if label_id:
        body["addLabelIds"] = [label_id]
    service = _gmail_service()
    _execute(
        lambda: service.users().threads().modify(userId="me", id=thread_id, body=body),
        what="Updating Gmail label",
    )


def list_email_thread_ids(query: str, max_results: int = 5000) -> list[str]:
    """List matching thread ids without downloading message bodies."""
    service = _gmail_service()
    thread_ids: list[str] = []
    page_token: str | None = None

    while len(thread_ids) < max_results:
        page_size = min(100, max_results - len(thread_ids))
        response = _execute(
            lambda: service.users().threads().list(
                userId="me",
                q=query,
                maxResults=page_size,
                pageToken=page_token,
            ),
            what="Listing Gmail threads",
        )
        thread_ids.extend(item["id"] for item in response.get("threads", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return thread_ids[:max_results]


def get_email_thread(thread_id: str, fmt: str = "metadata") -> dict[str, Any]:
    """Fetch one thread. Metadata is much cheaper than full bodies."""
    service = _gmail_service()
    kwargs: dict[str, Any] = {"userId": "me", "id": thread_id, "format": fmt}
    if fmt == "metadata":
        kwargs["metadataHeaders"] = ["From", "To", "Subject", "Date"]
    return _execute(
        lambda: service.users().threads().get(**kwargs),
        what="Reading Gmail thread",
    )


def list_email_threads(query: str, max_results: int = 5000) -> list[dict[str, Any]]:
    """Fetch matching threads as metadata (headers + snippet), not full bodies."""
    threads: list[dict[str, Any]] = []
    for index, thread_id in enumerate(list_email_thread_ids(query, max_results=max_results), start=1):
        threads.append(get_email_thread(thread_id, fmt="metadata"))
        if index % 25 == 0:
            time.sleep(0.4)
    return threads


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
