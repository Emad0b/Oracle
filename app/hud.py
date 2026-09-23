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
    ) -> None:
        self.on_send_text = on_send_text
        self.on_quit = on_quit
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._root: tk.Tk | None = None
        self._status_var: tk.StringVar | None = None
        self._output: tk.Text | None = None
        self._entry: tk.Entry | None = None
        self._send: tk.Button | None = None
        self._busy = False

    def run(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title("Oracle")
        root.geometry("650x580+40+40")
        root.configure(bg="#05070d")

        tk.Label(root, text="ORACLE", font=("Segoe UI", 28, "bold"), fg="#7ee0ff", bg="#05070d").pack(
            pady=(18, 0)
        )
        tk.Label(
            root,
            text="Text-first LLM assistant",
            font=("Segoe UI", 10),
            fg="#8fb0c9",
            bg="#05070d",
        ).pack(pady=(0, 10))

        self._status_var = tk.StringVar(value="ACTIVE — ready")
        tk.Label(
            root,
            textvariable=self._status_var,
            font=("Segoe UI", 10, "bold"),
            fg="#7dffb2",
            bg="#05070d",
        ).pack(pady=(0, 8))

        self._output = tk.Text(
            root,
            height=22,
            wrap="word",
            bg="#0b1220",
            fg="#e8f1ff",
            insertbackground="#73d8ff",
            relief="flat",
            padx=14,
            pady=12,
            state="disabled",
            font=("Segoe UI", 10),
        )
        self._output.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        entry_row = tk.Frame(root, bg="#05070d")
        entry_row.pack(fill="x", padx=18, pady=(0, 18))
        self._entry = tk.Entry(
            entry_row,
            font=("Segoe UI", 11),
            bg="#0b1220",
            fg="#eef4ff",
            insertbackground="#73d8ff",
            relief="flat",
        )
        self._entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        self._entry.bind("<Return>", lambda _event: self._submit())
        self._send = tk.Button(
            entry_row,
            text="Send",
            command=self._submit,
            bg="#35b9f0",
            fg="#04111a",
            relief="flat",
            padx=16,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        self._send.pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self._close)
        self._drain()
        root.mainloop()

    def _submit(self) -> None:
        if self._busy or not self.on_send_text or not self._entry:
            return
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, tk.END)
        self._append(f"You: {text}\n\n")
        import threading

        threading.Thread(target=self.on_send_text, args=(text,), daemon=True).start()

    def _append(self, text: str) -> None:
        if self._output is None:
            return
        self._output.configure(state="normal")
        self._output.insert(tk.END, text)
        self._output.see(tk.END)
        self._output.configure(state="disabled")

    def set_status(self, status: str, detail: str = "") -> None:
        self._queue.put(("status", f"{status} — {detail or status.title()}"))

    def set_transcript(self, text: str) -> None:
        self._queue.put(("output", f"{text}\n\n"))

    def set_busy(self, busy: bool) -> None:
        self._queue.put(("busy", busy))

    def show_job_chart(self, result: dict) -> None:
        self._queue.put(("job_chart", result))

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
                self._busy = bool(payload)
                state = tk.DISABLED if self._busy else tk.NORMAL
                if self._entry:
                    self._entry.configure(state=state)
                if self._send:
                    self._send.configure(state=state)
            elif kind == "job_chart":
                from app.job_chart import show_job_triage_chart

                show_job_triage_chart(payload, parent=self._root)
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
