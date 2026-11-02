from __future__ import annotations

import queue
import tkinter as tk
from typing import Callable


class OracleHUD:
    """Text-only Oracle chat window."""

    def __init__(
        self,
        on_send_text: Callable[[str], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_action: Callable | None = None,
    ) -> None:
        self.on_send_text = on_send_text
        self.on_quit = on_quit
        self.on_action = on_action
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._root: tk.Tk | None = None
        self._status_var: tk.StringVar | None = None
        self._output: tk.Text | None = None
        self._entry: tk.Entry | None = None
        self._send: tk.Button | None = None
        self._busy = False
        self._buttons = []
        self._system_info = {}

    def build(self):
        from app.ui_layout import build
        return build(self)

    def _open_finance(self):
        from app.finance_ui import open_finance
        from tkinter import messagebox
        try:
            existing = getattr(self, '_finance', None)
            if existing and existing.window.winfo_exists():
                existing.refresh()
                existing.window.lift()
            else:
                self._finance = open_finance(self._root)
        except Exception:
            messagebox.showerror('MyMoney', 'Unable to open local finance records. Check that the .data folder is writable.', parent=self._root)

    def run(self) -> None:
        root = self.build()
        self._drain()
        if self._root:
            root.mainloop()

    def _submit(self) -> None:
        if self._busy or not self.on_send_text or not self._entry:
            return
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, tk.END)
        self._set_busy_widgets(True)
        self._status_var.set("Working on your request…")
        import threading

        threading.Thread(target=self._invoke, args=(self.on_send_text, text), daemon=True).start()

    def _invoke(self, callback, *args):
        try:
            callback(*args)
        except Exception:
            self.set_transcript("Oracle: That action could not finish. Please try again.")
        finally:
            self.set_busy(False)

    def _set_busy_widgets(self, busy):
        self._busy = busy
        for widget in self._buttons:
            widget.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self._entry.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self._send.configure(text="Working…" if busy else "Send  ↑")
        if not busy:
            self._entry.focus_set()

    def _draft(self, text):
        if not self._busy:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, text)
            self._entry.focus_set()

    def _clear_chat(self):
        from tkinter import messagebox
        if not self._busy and messagebox.askyesno("Clear conversation", "Delete your saved conversation history? Your preferences will remain.", parent=self._root):
            self._output.configure(state="normal")
            self._output.delete("1.0", tk.END)
            self._output.configure(state="disabled")
            self._quick_prompt("clear memory")

    def set_system_info(self, **info):
        self._queue.put(("system", info))

    def _connections(self):
        from app.ui_layout import BG, MUTED, label
        window = tk.Toplevel(self._root)
        window.title("Connections & privacy")
        window.configure(bg=BG)
        window.geometry("560x490")
        window.transient(self._root)
        label(window, "Your connections", 20, bold=True).pack(anchor="w", padx=26, pady=(24, 14))
        info = self._system_info
        lines = ["LLM: " + info.get("llm", "Not checked"), "Google: " + info.get("google", "Not checked"),
                 "IoT: " + info.get("iot", "Not checked"), "",
                 "Microphone audio and approved screenshots are sent to your configured API provider.",
                 "Screenshots are previewed before upload. Recordings become editable drafts.",
                 "Monitoring starts only when enabled and stops when Oracle closes.",
                 "Connection configuration does not guarantee API quota or device availability."]
        label(window, "\n\n".join(lines), 10, MUTED, justify="left", wraplength=500).pack(anchor="w", padx=26)

    def _quick_prompt(self, prompt: str) -> None:
        if self._busy or not self._entry:
            return
        self._entry.delete(0, tk.END)
        self._entry.insert(0, prompt)
        self._submit()

    def _media_action(self, action):
        if self._busy or not self.on_action:
            return
        from tkinter import messagebox
        if action == "listen" and not messagebox.askokcancel(
                "Voice transcription", "Record 6 seconds and send audio to your configured API provider? The transcript will appear for review before sending.", parent=self._root):
            return
        if action == "screen":
            try:
                from app.perception import capture_screen
                from PIL import ImageTk
                captured = capture_screen()
                preview = tk.Toplevel(self._root)
                preview.title("Screen preview — not uploaded yet")
                from app.ui_layout import BG, MUTED, label as ui_label
                preview.configure(bg=BG)
                preview.transient(self._root)
                thumb = captured.copy()
                thumb.thumbnail((800, 500))
                photo = ImageTk.PhotoImage(thumb)
                label = tk.Label(preview, image=photo, bg=BG)
                label.image = photo
                label.pack()
                ui_label(preview, "Analyze sends this screenshot to your configured LLM provider.", color=MUTED).pack(pady=12)
                def send():
                    preview.destroy()
                    self._dispatch_media("screen", captured)
                tk.Button(preview, text="Analyze this screenshot", command=send).pack(side="left")
                tk.Button(preview, text="Cancel", command=preview.destroy).pack(side="right")
            except Exception:
                messagebox.showerror("Screen capture", "Capture failed. Install Pillow and check desktop permissions.")
            return
        self._dispatch_media(action)

    def _dispatch_media(self, action, payload=None):
        if self._busy:
            return
        import threading
        self._set_busy_widgets(True)
        threading.Thread(target=self._invoke, args=(self.on_action, action, payload), daemon=True).start()

    def _append(self, text: str) -> None:
        if self._output is None:
            return
        self._welcome.grid_remove()
        self._chat.grid(row=0, column=0, sticky="nsew")
        text = text.strip()
        is_user = text.startswith("You:")
        content = text.split(":", 1)[1].strip() if text.startswith(("You:", "Oracle:")) else text
        self._output.configure(state="normal")
        self._output.insert(tk.END, "YOU\n" if is_user else "ORACLE\n", "user" if is_user else "oracle")
        self._output.insert(tk.END, content + "\n\n")
        self._output.see(tk.END)
        self._output.configure(state="disabled")

    def set_status(self, status: str, detail: str = "") -> None:
        self._queue.put(("status", detail or status.title()))

    def set_transcript(self, text: str) -> None:
        self._queue.put(("output", f"{text}\n\n"))

    def set_busy(self, busy: bool) -> None:
        self._queue.put(("busy", busy))

    def stop(self) -> None:
        self._queue.put(("stop", None))

    def _close(self) -> None:
        if self.on_quit:
            self.on_quit()
        if self._root:
            self._root.destroy()
            self._root = None

    def _drain(self) -> None:
        if not self._root:
            return
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "stop":
                self._close()
                return
            if kind == "status" and self._status_var:
                self._status_var.set(str(payload))
            elif kind == "output":
                self._append(str(payload))
            elif kind == "busy":
                self._set_busy_widgets(bool(payload))
            elif kind == "finance":
                self._open_finance()
            elif kind == "system":
                self._system_info.update(payload)
                self._connection_var.set("LLM · " + self._system_info.get("llm", "Not checked") + "\nIoT · " + self._system_info.get("iot", "Not checked"))
            elif kind == "draft" and self._entry:
                self._entry.configure(state=tk.NORMAL)
                self._entry.delete(0, tk.END)
                self._entry.insert(0, str(payload))
        self._root.after(50, self._drain)


_hud: OracleHUD | None = None


def get_hud() -> OracleHUD:
    global _hud
    if _hud is None:
        _hud = OracleHUD()
    return _hud


def reset_hud() -> None:
    global _hud
    _hud = None
