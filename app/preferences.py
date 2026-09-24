"""Explicit local learning; does not train model weights or change code."""
import json
import threading
from app.config import DATA_DIR

PATH = DATA_DIR / "preferences.json"
_lock = threading.Lock()


def load_preferences():
    with _lock:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
            return [x for x in data if isinstance(x, str)][:30] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []


def learn(text):
    text = text.strip()
    if not text or len(text) > 500:
        raise ValueError("Use a preference between 1 and 500 characters")
    items = load_preferences()
    if text not in items:
        items.append(text)
    with _lock:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(items[-30:], indent=2), encoding="utf-8")
        temporary.replace(PATH)


def forget():
    with _lock:
        PATH.unlink(missing_ok=True)
