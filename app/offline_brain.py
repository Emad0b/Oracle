from __future__ import annotations

import re
from datetime import datetime

from app.google_auth import google_status
from app.system_skills import open_app, open_url, web_search


def offline_reply(message: str) -> str:
    """Simple local brain used when cloud APIs are disabled or unavailable."""
    text = " ".join(str(message or "").split())
    lowered = text.lower()

    if not text:
        return "I am Oracle. Give me a command when you are ready."

    if any(word in lowered for word in ("who are you", "your name", "what are you")):
        return (
            "I am Oracle, your operational assistant for analysis, communication, "
            "and logical execution."
        )

    if "time" in lowered:
        return f"The local time is {datetime.now().strftime('%I:%M %p')}."

    if "date" in lowered or "day is it" in lowered:
        return f"Today is {datetime.now().strftime('%A, %d %B %Y')}."

    if "google" in lowered and any(word in lowered for word in ("status", "connected", "account")):
        status = google_status()
        if status.get("connected"):
            return f"Google is connected as {status.get('email') or 'your account'}."
        return "Google is not connected. Run python oracle.py --connect-google when you are ready."

    if lowered.startswith("open "):
        target = text[5:].strip()
        if target.startswith("http") or "." in target and " " not in target:
            result = open_url(target)
            return f"Opening {result.get('url', target)}."
        result = open_app(target)
        if result.get("error"):
            return str(result["error"])
        return f"Opening {result.get('app', target)}."

    if lowered.startswith("search ") or lowered.startswith("google "):
        query = re.sub(r"^(search|google)\s+", "", text, flags=re.I).strip()
        if query:
            web_search(query)
            return f"Searching the web for {query}."

    if any(word in lowered for word in ("hello", "hi oracle", "hey oracle", "good morning", "good evening")):
        return "Hello. Oracle is active and listening."

    if any(word in lowered for word in ("help", "what can you do")):
        return (
            "I am Oracle. In offline mode I can tell the time, open apps or websites, "
            "run a web search, check Google connection status, and keep this console active. "
            "Cloud AI replies will return once API quota is available."
        )

    if any(word in lowered for word in ("email", "calendar", "meeting", "inbox")):
        return (
            "Email and calendar tools need cloud AI routing right now. "
            "Oracle is in offline mode because the OpenAI quota was exceeded. "
            "You can still open apps, search the web, and use this active display."
        )

    return (
        "Oracle received that. Cloud AI is offline due to API quota, so I can only handle "
        "basic local commands for now. Try asking for the time, opening an app, "
        "or saying help."
    )
