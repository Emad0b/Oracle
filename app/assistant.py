from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.google_auth import google_status
from app.hud import OracleHUD, reset_hud
from app.llm import LLMServiceError, MissingApiKeyError, generate_chat_reply
from app.memory import clear_history, load_history, save_history
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

    def handle(self, message: str) -> str:
        cleaned = " ".join(str(message or "").split())
        if not cleaned:
            return ""

        self._set_status("THINKING", "Understanding request")
        self._set_output(f"You: {cleaned}")
        lowered = cleaned.lower()

        if lowered in {"mymoney", "my money", "open finance", "open mymoney", "open budget"}:
            if self.hud:
                self.hud._queue.put(("finance", None))
                reply = "Opening MyMoney. Your financial records stay local and are not sent to the LLM."
            else:
                reply = "Open the local finance window with: python oracle.py --money"
        elif lowered.startswith("learn: "):
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
                     "Try 'open mymoney' for local budgeting, 'system status', 'list devices', or 'turn on the study light'. "
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
        import os
        self.hud.set_system_info(
            llm=f"{self.settings.openai_model} · key configured" if self.settings.openai_api_key else "API key needed",
            google="Checking connection…",
            iot="Simulated devices" if os.getenv("IOT_BACKEND", "demo") == "demo" else "Home Assistant configured",
        )
        def check_google():
            try:
                status = google_status(self.settings)
                message = "Connected" if status.get("connected") else "Not connected. Run oracle.py --connect-google"
            except Exception:
                message = "Connection unavailable"
            self.hud.set_system_info(google=message)
        threading.Thread(target=check_google, daemon=True, name="oracle-connection-check").start()
        self._set_status("ACTIVE", "Oracle ready")
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
