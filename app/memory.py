from __future__ import annotations

import json
from pathlib import Path

from app.config import DATA_DIR
from app.schemas import ChatMessage


MEMORY_PATH = DATA_DIR / "conversation_memory.json"
MAX_STORED_MESSAGES = 40


def load_history() -> list[ChatMessage]:
    if not MEMORY_PATH.exists():
        return []

    try:
        raw = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    history: list[ChatMessage] = []
    for item in raw.get("messages", []):
        try:
            history.append(ChatMessage.model_validate(item))
        except Exception:
            continue
    return history[-MAX_STORED_MESSAGES:]


def save_history(messages: list[ChatMessage]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "messages": [message.model_dump() for message in messages[-MAX_STORED_MESSAGES:]]
    }
    MEMORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_history() -> None:
    if MEMORY_PATH.exists():
        MEMORY_PATH.unlink()
