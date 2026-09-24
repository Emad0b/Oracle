from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.google_auth import google_status
from app.hud import OracleHUD, reset_hud
from app.job_triage import triage_job_application_emails
from app.llm import LLMServiceError, MissingApiKeyError, generate_chat_reply
from app.memory import clear_history, load_history, save_history
from app.nlp import is_job_triage_request, is_show_job_chart_request
from app.schemas import ChatMessage, ChatRequest


@dataclass
class OracleAssistant:
    """Text-first LLM assistant with Gmail and Calendar capabilities."""

    settings: Settings = field(default_factory=get_settings)
    history: list[ChatMessage] = field(default_factory=list)
    hud: OracleHUD | None = field(default=None, init=False)
    _busy_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _monitor: object = field(default=None, init=False)
    _last_reply: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.history = load_history()

    def _persist(self) -> None:
        save_history(self.history)

    def _set_status(self, status: str, detail: str = "") -> None:
        if self.hud:
            self.hud.set_status(status, detail)

    def _set_output(self, text: str) -> None:
        if self.hud:
            self.hud.set_transcript(text)

    async def think(self, message: str) -> str:
        request = ChatRequest(message=message, history=self.history[-20:])
        reply, _ = await generate_chat_reply(request, self.settings)
        return reply

    def _show_saved_chart(self) -> str:
        from app.job_chart import load_triage_result, show_job_triage_chart

        self._set_status("THINKING", "Refreshing job applications from Gmail")
        try:
            result = triage_job_application_emails(months=2, apply_labels=True)
        except Exception:
            result = load_triage_result()
        if not result:
            return (
                "No saved job-triage chart yet. Ask me to "
                '"label my job application emails from the past two months" first.'
            )
        if self.hud:
            self.hud.show_job_chart(result)
        else:
            show_job_triage_chart(result, parent=None, block=False)
        return (
            f"Chart refreshed: {result.get('total_applications', 0)} application records "
            f"across {result.get('scanned_emails', 0)} emails."
        )

    def _triage_jobs(self) -> str:
        self._set_status("THINKING", "Scanning recent job-application threads")
        result = triage_job_application_emails(months=2, apply_labels=True)
        if self.hud:
            self.hud.show_job_chart(result)
        else:
            from app.job_chart import show_job_triage_chart

            show_job_triage_chart(result, parent=None, block=False)
        summary = (
            f"{result.get('scan_mode', 'full').title()} snapshot refresh: "
            f"checked {result['scanned_emails']} emails in {result['scanned_threads']} threads "
            f"({result.get('new_applications', 0)} new, {result.get('updated_applications', 0)} updated) "
            f"and found {result['total_applications']} job-application records: "
            f"{len(result['offer'])} offer, {len(result['declined'])} declined "
            f"({sum(1 for item in result['declined'] if item.get('reason') == 'explicit_rejection')} explicit, "
            f"{sum(1 for item in result['declined'] if item.get('reason') == 'no_reply_after_21_days')} timed out after "
            f"{result['no_response_after_days']} days), "
            f"{len(result['responded'])} responded/in progress, and "
            f"{len(result['awaiting_response'])} still inside the 3-week window. "
            "Indeed receipts were treated as applications, not offers or employer replies. "
            "Opening the interactive pie chart."
        )
        return summary

    def handle(self, message: str) -> str:
        cleaned = " ".join(str(message or "").split())
        if not cleaned:
            return ""

        self._set_status("THINKING", "Understanding request")
        self._set_output(f"You: {cleaned}")
        lowered = cleaned.lower()

        if lowered.startswith("learn: "):
            from app.preferences import learn
            try:
                learn(cleaned[7:])
                reply = "Preference saved locally for future replies. This does not train model weights."
            except ValueError as exc:
                reply = str(exc)
        elif lowered == "show preferences":
            from app.preferences import load_preferences
            reply = "\n".join(load_preferences()) or "No saved preferences."
        elif lowered == "forget preferences":
            from app.preferences import forget
            forget()
            reply = "Saved preferences removed."
        elif lowered == "start monitoring":
            from app.background import BackgroundMonitor
            from app.iot import list_devices
            if self._monitor is None:
                self._monitor = BackgroundMonitor(list_devices, lambda result: self._set_output(f"Device monitor: {result}"))
            started = self._monitor.start()
            reply = ("Device monitor started: read-only checks every 5 minutes while Oracle runs. "
                     "Use 'stop monitoring' to stop.") if started else "Device monitor is already running."
        elif lowered == "stop monitoring":
            if self._monitor:
                self._monitor.stop()
            reply = "Device monitoring stopped."
        elif lowered in {"help", "capabilities", "what can you do"}:
            reply = ("I am Oracle. I can reason and plan using your configured LLM, use Gmail and Calendar tools, "
                     "open supported apps and websites, and control configured IoT lights and switches. "
                     "Try 'system status', 'list devices', or 'turn on the study light'. "
                     "IoT defaults to simulated devices. Use the Record, Speak and Preview screen buttons for voice/vision. "
                     "Use 'start monitoring' for background device checks; 'learn: prefer concise answers' saves a preference.")
        elif lowered in {"system status", "integration status"}:
            import os
            reply = (f"LLM: {self.settings.openai_model}; "
                     f"key {'configured (connection not tested)' if self.settings.openai_api_key else 'missing'}. "
                     f"IoT backend: {os.getenv('IOT_BACKEND', 'demo')}. "
                     "Gmail requires a valid OAuth connection. Memory is stored locally.")
        elif lowered in {"list devices", "show devices"}:
            from app.iot import list_devices
            try:
                result = list_devices()
                reply = ("Simulated devices:\n" if result['simulated'] else "Connected devices:\n") + "\n".join(
                    f"{item['entity_id']}: {item['state']}" for item in result['devices'])
            except ValueError as exc:
                reply = str(exc)
        elif lowered in {"forget everything", "clear memory", "reset memory"}:
            clear_history()
            self.history = []
            reply = "Memory cleared. We're starting fresh."
        elif is_show_job_chart_request(cleaned):
            reply = self._show_saved_chart()
        elif is_job_triage_request(cleaned):
            try:
                reply = self._triage_jobs()
            except Exception as exc:  # noqa: BLE001
                reply = f"Job-email triage could not complete: {exc}"
                self._set_status("ERROR", "Job triage failed")
        else:
            try:
                reply = asyncio.run(self.think(cleaned))
            except MissingApiKeyError as exc:
                reply = f"Oracle needs an LLM API key to answer general requests. {exc}"
                self._set_status("ERROR", "LLM key missing")
            except LLMServiceError as exc:
                reply = f"Oracle's LLM request failed: {exc}"
                self._set_status("ERROR", "LLM unavailable")
            except Exception as exc:  # noqa: BLE001
                reply = f"Oracle hit an unexpected fault: {exc}"
                self._set_status("ERROR", "Fault")

        self.history.extend(
            [
                ChatMessage(role="user", content=cleaned),
                ChatMessage(role="assistant", content=reply),
            ]
        )
        self.history = self.history[-40:]
        self._persist()
        self._last_reply = reply
        self._set_output(f"Oracle: {reply}")
        self._set_status("ACTIVE", "Ready")
        return reply

    def _ui_send(self, text: str) -> None:
        if text.lower() in {"exit", "quit", "goodbye", "good bye"}:
            self._persist()
            if self.hud:
                self.hud.stop()
            return
        if not self._busy_lock.acquire(blocking=False):
            return
        if self.hud:
            self.hud.set_busy(True)
        try:
            self.handle(text)
        finally:
            if self.hud:
                self.hud.set_busy(False)
            self._busy_lock.release()

    def run_ui(self) -> None:
        reset_hud()
        self.hud = OracleHUD(on_send_text=self._ui_send, on_quit=self.close, on_action=self._media_action)
        try:
            status = google_status(self.settings)
        except Exception:
            status = {"connected": False}
        connection = (
            f"Google connected as {status['email']}."
            if status.get("connected")
            else "Google is not connected. Run python oracle.py --connect-google."
        )
        self._set_status("ACTIVE", "Oracle ready")
        self._set_output(
            "I am Oracle, your assistant for analysis, planning, communication and connected devices. "
            f"{connection}\nTry 'help', 'system status', or 'list devices'. "
            "General conversation uses your configured LLM API."
        )
        self.hud.run()

    def close(self):
        if self._monitor:
            self._monitor.stop()
        self._persist()

    def _media_action(self, action, payload=None):
        if not self._busy_lock.acquire(blocking=False):
            return
        self.hud.set_busy(True)
        try:
            from app.perception import transcribe, speak, describe_screen
            if action == "listen":
                self._set_status("RECORDING", "Recording 6 seconds, then transcribing")
                text = transcribe()
                self.hud._queue.put(("draft", text))
                self._set_output(f"Heard: {text or '[no clear speech]'}. Review the input before pressing Send.")
            elif action == "speak":
                if not self._last_reply:
                    self._set_output("No reply to speak yet.")
                else:
                    self._set_status("SPEAKING", "AI-generated voice")
                    speak(self._last_reply)
            elif action == "screen" and payload is not None:
                self._set_status("ANALYZING", "Analyzing the approved screenshot")
                self._last_reply = describe_screen(payload)
                self._set_output("Screen analysis: " + self._last_reply)
        except Exception:
            self._set_output("Voice/vision unavailable. Check API credit, model support, dependencies and microphone permissions.")
        finally:
            self.hud.set_busy(False)
            self._set_status("ACTIVE", "Ready")
            self._busy_lock.release()

    def run_terminal(self) -> None:
        print("Oracle text LLM. Type 'exit' to quit.")
        while True:
            try:
                message = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if message.lower() in {"exit", "quit"}:
                break
            if message:
                print(f"Oracle: {self.handle(message)}")
        self.close()
