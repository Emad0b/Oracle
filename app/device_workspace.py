"""Local monitoring cards and sampled device readings."""
import hashlib
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.iot import list_devices


DATABASE = Path(__file__).resolve().parents[1] / ".data" / "devices.sqlite3"


def connection_key(backend: str):
    if backend == "home_assistant":
        url = os.environ.get("HA_URL", "").rstrip("/")
        return backend + ":" + hashlib.sha256(url.encode()).hexdigest()
    return backend


@contextmanager
def connection():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backend TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                title TEXT NOT NULL,
                UNIQUE (backend, entity_id)
            );
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY,
                panel_id INTEGER NOT NULL REFERENCES panels(id) ON DELETE CASCADE,
                captured_at TEXT NOT NULL,
                state TEXT NOT NULL,
                unit TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS samples_by_panel ON samples(panel_id, id);
        """)
        yield db


def save_panel(entity_id: str, title: str):
    snapshot = list_devices()
    key = connection_key(snapshot["backend"])
    if entity_id not in {item["entity_id"] for item in snapshot["devices"]}:
        raise ValueError("Choose a device in the current allowlist.")
    title = title.strip()
    if not title or len(title) > 80:
        raise ValueError("Enter a title of up to 80 characters.")
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM panels WHERE backend = ?", (key,)).fetchone()[0] >= 20:
            exists = db.execute("SELECT 1 FROM panels WHERE backend = ? AND entity_id = ?", (key, entity_id)).fetchone()
            if not exists:
                raise ValueError("Keep at most 20 monitoring cards per connection.")
        db.execute("""
            INSERT INTO panels (backend, entity_id, title) VALUES (?, ?, ?)
            ON CONFLICT (backend, entity_id) DO UPDATE SET title = excluded.title
        """, (key, entity_id, title))


def remove_panel(panel_id: int):
    with connection() as db:
        db.execute("DELETE FROM panels WHERE id = ?", (panel_id,))


def workspace(record: bool = False, entity_id: str | None = None):
    snapshot = list_devices()
    available = {item["entity_id"]: item for item in snapshot["devices"]}
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    panels = []
    with connection() as db:
        rows = db.execute("SELECT * FROM panels WHERE backend = ? ORDER BY id",
                          (connection_key(snapshot["backend"]),)).fetchall()
        for row in rows:
            device = available.get(row["entity_id"])
            if device is None or (entity_id is not None and row["entity_id"] != entity_id):
                continue
            panel_id = row["id"]
            if record and device["state"] not in {"unavailable", "unknown"}:
                db.execute("INSERT INTO samples (panel_id, captured_at, state, unit) VALUES (?, ?, ?, ?)",
                           (panel_id, captured_at, device["state"], device.get("unit", "")))
                db.execute("""
                    DELETE FROM samples WHERE panel_id = ? AND id NOT IN
                        (SELECT id FROM samples WHERE panel_id = ? ORDER BY id DESC LIMIT 100)
                """, (panel_id, panel_id))
            readings = db.execute("""
                SELECT captured_at, state, unit FROM samples
                WHERE panel_id = ? ORDER BY id DESC LIMIT 10
            """, (panel_id,)).fetchall()
            panels.append({"id": panel_id, "title": row["title"], "device": device,
                           "readings": [dict(reading) for reading in readings]})
    return {"backend": snapshot["backend"], "simulated": snapshot["simulated"], "panels": panels}


def device_readings(entity_id: str):
    result = workspace(entity_id=entity_id)
    result["panels"] = [
        {"device": panel["device"], "readings": panel["readings"]}
        for panel in result["panels"]
    ]
    return result
