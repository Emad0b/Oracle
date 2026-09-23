"""Interactive pie-chart view for job-application triage results."""

from __future__ import annotations

import json
import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

RESULT_PATH = DATA_DIR / "job_triage_latest.json"

CATEGORIES = (
    ("offer", "Offer", "#35b9f0"),
    ("declined", "Declined / Timed out", "#ff8f8f"),
    ("responded", "Responded / In Progress", "#7dffb2"),
    ("awaiting_response", "Awaiting 21-day Window", "#9eb6cc"),
)


def save_triage_result(result: dict[str, Any]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return RESULT_PATH


def load_triage_result() -> dict[str, Any] | None:
    if not RESULT_PATH.exists():
        return None
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def _counts(result: dict[str, Any]) -> list[tuple[str, str, str, int, list[dict[str, str]]]]:
    rows = []
    for key, label, color in CATEGORIES:
        items = list(result.get(key) or [])
        rows.append((key, label, color, len(items), items))
    return rows


class JobTriageChart:
    """Clickable pie chart with a detail list for the selected category."""

    def __init__(self, parent: tk.Misc | None, result: dict[str, Any]) -> None:
        self.result = result
        self.rows = _counts(result)
        self.selected = next((row[0] for row in self.rows if row[3] > 0), self.rows[0][0])
        self._hover: str | None = None
        self._slices: list[tuple[str, float, float]] = []
        self._current_items: list[dict[str, str]] = []
        self._preview_queue: queue.Queue[tuple[str, dict[str, Any] | str]] = queue.Queue()

        self.window = tk.Toplevel(parent) if parent is not None else tk.Tk()
        self.window.title("Oracle — Job Application Breakdown")
        self.window.geometry("940x720+80+60")
        self.window.configure(bg="#05070d")
        self.window.attributes("-topmost", True)

        total = int(result.get("total_applications", sum(row[3] for row in self.rows)))
        period = result.get("period_start", "recent")
        scanned = result.get("scanned_threads", 0)
        scanned_emails = result.get("scanned_emails", 0)

        tk.Label(
            self.window,
            text="Job Application Outcomes",
            font=("Segoe UI", 18, "bold"),
            fg="#7ee0ff",
            bg="#05070d",
        ).pack(pady=(16, 2))
        self.summary_var = tk.StringVar(
            value=(
                f"From {period} · "
                f"{result.get('scan_mode', 'saved')} snapshot · "
                f"{scanned} threads checked · {total} applications · "
                f"click a slice for details"
            )
        )
        tk.Label(
            self.window,
            textvariable=self.summary_var,
            font=("Segoe UI", 9),
            fg="#8fb0c9",
            bg="#05070d",
        ).pack(pady=(0, 8))
        self.refresh_button = tk.Button(
            self.window,
            text="Refresh Gmail",
            command=self._refresh_from_gmail,
            bg="#163047",
            fg="#e8f7ff",
            activebackground="#214864",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
        )
        self.refresh_button.pack(pady=(0, 4))

        body = tk.Frame(self.window, bg="#05070d")
        body.pack(fill="both", expand=True, padx=16, pady=8)

        self.canvas = tk.Canvas(body, width=340, height=340, bg="#05070d", highlightthickness=0)
        self.canvas.pack(side="left", padx=(0, 12))
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)

        right = tk.Frame(body, bg="#05070d")
        right.pack(side="left", fill="both", expand=True)

        self.legend = tk.Frame(right, bg="#05070d")
        self.legend.pack(fill="x", pady=(8, 10))

        self.detail_title = tk.StringVar(value="")
        tk.Label(
            right,
            textvariable=self.detail_title,
            font=("Segoe UI", 11, "bold"),
            fg="#d7f4ff",
            bg="#05070d",
            anchor="w",
        ).pack(fill="x")

        list_frame = tk.Frame(right, bg="#0b1220")
        list_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.listbox = tk.Listbox(
            list_frame,
            bg="#0b1220",
            fg="#e8f1ff",
            selectbackground="#1d6f8a",
            selectforeground="#ffffff",
            activestyle="none",
            highlightthickness=0,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        scroll = tk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_email_select)

        tk.Label(
            right,
            text="EMAIL PREVIEW",
            font=("Segoe UI", 9, "bold"),
            fg="#73d8ff",
            bg="#05070d",
            anchor="w",
        ).pack(fill="x", pady=(10, 4))
        self.preview = tk.Text(
            right,
            height=14,
            wrap="word",
            bg="#0b1220",
            fg="#e8f1ff",
            insertbackground="#73d8ff",
            relief="flat",
            padx=10,
            pady=8,
            state="disabled",
            font=("Segoe UI", 9),
        )
        self.preview.pack(fill="both", expand=True)

        note = result.get("skipped_note") or ""
        if note:
            tk.Label(
                self.window,
                text=note,
                font=("Segoe UI", 8),
                fg="#7f93ad",
                bg="#05070d",
            ).pack(pady=(0, 12))

        self._draw()
        self._refresh_details()
        self._set_preview("Click an email above to preview its contents.")
        self.window.after(100, self._drain_preview_queue)

    def _draw(self) -> None:
        self.canvas.delete("all")
        cx, cy, radius = 170, 170, 120
        total = sum(row[3] for row in self.rows)
        self._slices = []

        if total == 0:
            self.canvas.create_text(
                170,
                170,
                text="No labelled\nthreads yet",
                fill="#8fb0c9",
                font=("Segoe UI", 12),
                justify="center",
            )
        else:
            angle = -90.0
            for key, label, color, count, _items in self.rows:
                extent = 360.0 * (count / total)
                if extent <= 0:
                    continue
                active = key == self.selected or key == self._hover
                draw_radius = radius + (10 if active else 0)
                self.canvas.create_arc(
                    cx - draw_radius,
                    cy - draw_radius,
                    cx + draw_radius,
                    cy + draw_radius,
                    start=angle,
                    extent=extent,
                    fill=color,
                    outline="#05070d",
                    width=2,
                    tags=("slice", key),
                )
                self._slices.append((key, angle, angle + extent))
                mid = math.radians(angle + extent / 2.0)
                lx = cx + math.cos(mid) * (draw_radius * 0.62)
                ly = cy - math.sin(mid) * (draw_radius * 0.62)
                self.canvas.create_text(
                    lx,
                    ly,
                    text=str(count),
                    fill="#04111a",
                    font=("Segoe UI", 11, "bold"),
                )
                angle += extent

            hole = 48
            self.canvas.create_oval(
                cx - hole,
                cy - hole,
                cx + hole,
                cy + hole,
                fill="#05070d",
                outline="#234058",
            )
            self.canvas.create_text(
                cx,
                cy,
                text=str(total),
                fill="#e8f7ff",
                font=("Segoe UI", 16, "bold"),
            )

        for child in self.legend.winfo_children():
            child.destroy()
        for key, label, color, count, _items in self.rows:
            row = tk.Frame(self.legend, bg="#05070d")
            row.pack(fill="x", pady=3)
            swatch = tk.Canvas(row, width=14, height=14, bg="#05070d", highlightthickness=0)
            swatch.create_rectangle(0, 0, 14, 14, fill=color, outline="")
            swatch.pack(side="left", padx=(0, 8))
            weight = "bold" if key == self.selected else "normal"
            btn = tk.Label(
                row,
                text=f"{label}: {count}",
                font=("Segoe UI", 10, weight),
                fg="#e8f1ff" if key == self.selected else "#9eb6cc",
                bg="#05070d",
                cursor="hand2",
            )
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda _e, k=key: self._select(k))

    def _angle_at(self, event: tk.Event) -> float | None:
        cx, cy = 170, 170
        dx = event.x - cx
        dy = cy - event.y
        dist = math.hypot(dx, dy)
        if dist < 48 or dist > 140:
            return None
        # Match Tk arc angles: degrees counter-clockwise from 3 o'clock,
        # remapped into the same [-90, 270) range used while drawing.
        angle = math.degrees(math.atan2(dy, dx))
        if angle < -90:
            angle += 360
        return angle

    def _category_at(self, event: tk.Event) -> str | None:
        angle = self._angle_at(event)
        if angle is None:
            return None
        for key, start, end in self._slices:
            if start <= angle < end:
                return key
        return None

    def _on_motion(self, event: tk.Event) -> None:
        key = self._category_at(event)
        if key != self._hover:
            self._hover = key
            self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        if self._hover is not None:
            self._hover = None
            self._draw()

    def _on_click(self, event: tk.Event) -> None:
        key = self._category_at(event)
        if key:
            self._select(key)

    def _select(self, key: str) -> None:
        self.selected = key
        self._draw()
        self._refresh_details()

    def _refresh_details(self) -> None:
        selected = next(row for row in self.rows if row[0] == self.selected)
        _key, label, _color, count, items = selected
        self._current_items = items
        self.detail_title.set(f"{label} ({count})")
        self.listbox.delete(0, tk.END)
        self._set_preview("Click an email above to preview its contents.")
        if not items:
            self.listbox.insert(tk.END, "No threads in this category.")
            return
        for item in items:
            subject = item.get("subject", "(no subject)")
            sender = item.get("from", "Unknown")
            reason = item.get("reason") or ""
            reason_note = ""
            if reason == "no_reply_after_21_days":
                reason_note = "  [no reply > 21 days]"
            elif reason == "explicit_rejection":
                reason_note = "  [explicit rejection]"
            self.listbox.insert(tk.END, f"{subject}  —  {sender}{reason_note}")

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _on_email_select(self, _event: tk.Event) -> None:
        selection = self.listbox.curselection()
        if not selection or not self._current_items:
            return
        index = int(selection[0])
        if index >= len(self._current_items):
            return
        item = self._current_items[index]
        message_id = item.get("message_id", "")
        if not message_id:
            self._set_preview(
                "This saved result predates email previews. Refresh the chart to load it."
            )
            return
        self._set_preview("Loading email…")
        threading.Thread(
            target=self._load_preview,
            args=(message_id,),
            name="oracle-email-preview",
            daemon=True,
        ).start()

    def _load_preview(self, message_id: str) -> None:
        try:
            from app.google_services import read_email

            self._preview_queue.put(("ok", read_email(message_id)))
        except Exception as exc:  # noqa: BLE001
            self._preview_queue.put(("error", str(exc)))

    def _refresh_from_gmail(self) -> None:
        self.refresh_button.configure(state=tk.DISABLED, text="Refreshing…")
        self.summary_var.set("Refreshing from the last Gmail snapshot…")
        threading.Thread(
            target=self._refresh_worker,
            name="oracle-job-refresh",
            daemon=True,
        ).start()

    def _refresh_worker(self) -> None:
        try:
            from app.job_triage import triage_job_application_emails

            result = triage_job_application_emails(months=2, apply_labels=True)
            save_triage_result(result)
            self._preview_queue.put(("refresh", result))
        except Exception as exc:  # noqa: BLE001
            self._preview_queue.put(("refresh_error", str(exc)))

    def _drain_preview_queue(self) -> None:
        if not self.window.winfo_exists():
            return
        while True:
            try:
                kind, payload = self._preview_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "refresh_error":
                self.refresh_button.configure(state=tk.NORMAL, text="Refresh Gmail")
                self.summary_var.set(f"Refresh failed: {payload}")
                continue
            if kind == "refresh" and isinstance(payload, dict):
                self.result = payload
                self.rows = _counts(payload)
                self.selected = next(
                    (row[0] for row in self.rows if row[3] > 0),
                    self.rows[0][0],
                )
                total = payload.get("total_applications", sum(row[3] for row in self.rows))
                mode = payload.get("scan_mode", "full")
                self.summary_var.set(
                    f"From {payload.get('period_start', 'recent')} · "
                    f"{mode} scan · "
                    f"{payload.get('scanned_threads', 0)} threads checked · "
                    f"{payload.get('new_applications', 0)} new / "
                    f"{payload.get('updated_applications', 0)} updated · "
                    f"{total} applications · click a slice for details"
                )
                self.refresh_button.configure(state=tk.NORMAL, text="Refresh Gmail")
                self._draw()
                self._refresh_details()
                continue
            if kind == "error":
                self._set_preview(f"Could not load email: {payload}")
                continue
            email = payload
            if not isinstance(email, dict):
                continue
            body = email.get("body") or email.get("snippet") or "(No readable body)"
            self._set_preview(
                f"From: {email.get('from', 'Unknown')}\n"
                f"To: {email.get('to', '')}\n"
                f"Date: {email.get('date', '')}\n"
                f"Subject: {email.get('subject', '(no subject)')}\n\n"
                f"{body}"
            )
        self.window.after(100, self._drain_preview_queue)

    def show(self) -> None:
        self.window.lift()
        self.window.focus_force()


def show_job_triage_chart(
    result: dict[str, Any],
    parent: tk.Misc | None = None,
    block: bool = False,
) -> None:
    """Open the interactive pie chart for a triage result."""
    save_triage_result(result)
    chart = JobTriageChart(parent=parent, result=result)
    chart.show()
    if block and parent is None:
        chart.window.mainloop()
