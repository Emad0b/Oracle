from __future__ import annotations

import json
from typing import Any, Callable

from app.google_auth import GoogleAuthError, google_status
from app.google_services import (
    GoogleServiceError,
    cancel_calendar_event,
    create_calendar_event,
    list_recent_emails,
    list_upcoming_events,
    read_email,
    send_email,
    unread_email_digest,
    update_calendar_event,
)
from app.system_skills import open_app, open_url, web_search


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_google_connection_status",
            "description": "Check whether Google Gmail and Calendar are connected.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_emails",
            "description": "List recent Gmail inbox messages, optionally filtered by a Gmail search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Number of emails to return (1-20).",
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional Gmail search query, e.g. 'from:boss is:unread'.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unread_email_digest",
            "description": "Fetch unread inbox emails for a short spoken briefing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Number of unread emails to include (1-20).",
                        "minimum": 1,
                        "maximum": 20,
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read one email by Gmail message id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Gmail message id from list_recent_emails.",
                    }
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": (
                "Send an email through Gmail. Always call once with confirmed=false to "
                "preview the action, then again with confirmed=true only after the user agrees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body text."},
                    "confirmed": {
                        "type": "boolean",
                        "description": "True only after the user explicitly confirms sending.",
                    },
                },
                "required": ["to", "subject", "body", "confirmed"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_upcoming_events",
            "description": "List upcoming Google Calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Number of events to return (1-20).",
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to search (1-30).",
                        "minimum": 1,
                        "maximum": 30,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Create a Google Calendar event. Always call once with confirmed=false to "
                "preview, then again with confirmed=true only after the user agrees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start_iso": {
                        "type": "string",
                        "description": "Start time in ISO 8601 with timezone offset.",
                    },
                    "end_iso": {
                        "type": "string",
                        "description": "End time in ISO 8601 with timezone offset.",
                    },
                    "description": {"type": "string", "description": "Optional event notes."},
                    "location": {"type": "string", "description": "Optional location."},
                    "confirmed": {
                        "type": "boolean",
                        "description": "True only after the user explicitly confirms creation.",
                    },
                },
                "required": ["summary", "start_iso", "end_iso", "confirmed"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_calendar_event",
            "description": (
                "Cancel a Google Calendar event by id. Always call once with confirmed=false "
                "to preview, then confirmed=true after the user agrees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Calendar event id."},
                    "confirmed": {
                        "type": "boolean",
                        "description": "True only after explicit user confirmation.",
                    },
                },
                "required": ["event_id", "confirmed"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": (
                "Move or edit a Google Calendar event. Always call once with confirmed=false "
                "to preview, then confirmed=true after the user agrees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Calendar event id."},
                    "summary": {"type": "string", "description": "Optional new title."},
                    "start_iso": {
                        "type": "string",
                        "description": "Optional new start time in ISO 8601 with timezone offset.",
                    },
                    "end_iso": {
                        "type": "string",
                        "description": "Optional new end time in ISO 8601 with timezone offset.",
                    },
                    "description": {"type": "string", "description": "Optional new notes."},
                    "location": {"type": "string", "description": "Optional new location."},
                    "confirmed": {
                        "type": "boolean",
                        "description": "True only after explicit user confirmation.",
                    },
                },
                "required": ["event_id", "confirmed"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a website in the default browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Website URL to open."}
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open an allowed Windows app by name (notepad, calculator, chrome, edge, explorer, spotify, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "App name from the allow-list."}
                },
                "required": ["app_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Open a Google search for the given query in the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


def _tool_send_email(to: str, subject: str, body: str, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        return {
            "needs_confirmation": True,
            "action": "send_email",
            "preview": {"to": to, "subject": subject, "body": body},
            "message": (
                f"Ready to send email to {to} with subject '{subject}'. "
                "Ask the user to confirm before sending."
            ),
        }
    return send_email(to=to, subject=subject, body=body)


def _tool_create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    confirmed: bool = False,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        return {
            "needs_confirmation": True,
            "action": "create_calendar_event",
            "preview": {
                "summary": summary,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "description": description,
                "location": location,
            },
            "message": (
                f"Ready to create calendar event '{summary}' from {start_iso} to {end_iso}. "
                "Ask the user to confirm before creating it."
            ),
        }
    return create_calendar_event(
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        description=description,
        location=location,
    )


def _tool_cancel_event(event_id: str, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        return {
            "needs_confirmation": True,
            "action": "cancel_calendar_event",
            "preview": {"event_id": event_id},
            "message": f"Ready to cancel calendar event {event_id}. Ask the user to confirm.",
        }
    return cancel_calendar_event(event_id)


def _tool_update_event(
    event_id: str,
    confirmed: bool = False,
    summary: str | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    preview = {
        "event_id": event_id,
        "summary": summary,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "description": description,
        "location": location,
    }
    if not confirmed:
        return {
            "needs_confirmation": True,
            "action": "update_calendar_event",
            "preview": preview,
            "message": f"Ready to update calendar event {event_id}. Ask the user to confirm.",
        }
    return update_calendar_event(
        event_id=event_id,
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        description=description,
        location=location,
    )


TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "get_google_connection_status": lambda: google_status(),
    "list_recent_emails": list_recent_emails,
    "unread_email_digest": unread_email_digest,
    "read_email": read_email,
    "send_email": _tool_send_email,
    "list_upcoming_events": list_upcoming_events,
    "create_calendar_event": _tool_create_event,
    "cancel_calendar_event": _tool_cancel_event,
    "update_calendar_event": _tool_update_event,
    "open_url": open_url,
    "open_app": open_app,
    "web_search": web_search,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = handler(**arguments)
        return json.dumps(result, default=str)
    except (GoogleAuthError, GoogleServiceError, TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - surface unexpected API errors to the model
        return json.dumps({"error": f"Tool failed: {exc}"})
