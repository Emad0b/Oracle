import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from app.hud import OracleHUD


class HUDTests(unittest.TestCase):
    def setUp(self):
        self.callback = Mock()
        self.hud = OracleHUD(on_send_text=self.callback)
        try:
            self.root = self.hud.build()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()

    def tearDown(self):
        if getattr(self, "root", None):
            self.root.destroy()

    def test_starter_card_only_fills_draft(self):
        self.hud._draft("list devices")
        self.assertEqual(self.hud._entry.get(), "list devices")
        self.callback.assert_not_called()

    def test_busy_controls_disable_and_preserve_input(self):
        self.hud._draft("keep this")
        self.hud._set_busy_widgets(True)
        self.hud._quick_prompt("replace")
        self.assertEqual(self.hud._entry.get(), "keep this")
        self.assertTrue(all(str(w.cget("state")) == "disabled" for w in self.hud._buttons))
        self.hud._set_busy_widgets(False)
        self.assertEqual(str(self.hud._entry.cget("state")), "normal")

    def test_transcript_roles_and_voice_draft(self):
        self.hud.set_transcript("You: hello")
        self.hud.set_transcript("Oracle: Welcome back")
        self.hud._queue.put(("draft", "review before send"))
        self.hud._drain()
        text = self.hud._output.get("1.0", tk.END)
        self.assertIn("YOU\nhello", text)
        self.assertIn("ORACLE\nWelcome back", text)
        self.assertEqual(self.hud._entry.get(), "review before send")
        self.callback.assert_not_called()

    def test_callback_failure_unlocks_ui(self):
        self.hud._set_busy_widgets(True)
        self.hud._invoke(Mock(side_effect=RuntimeError("internal")), "test")
        self.hud._drain()
        self.assertFalse(self.hud._busy)
        self.assertNotIn("internal", self.hud._output.get("1.0", tk.END))

    def test_clear_memory_requires_confirmation(self):
        with patch("tkinter.messagebox.askyesno", return_value=False):
            self.hud._clear_chat()
        self.callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
