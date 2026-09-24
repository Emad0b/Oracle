import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.background import BackgroundMonitor
from app import preferences


class FeatureTests(unittest.TestCase):
    def test_monitor_only_notifies_changes_and_stops(self):
        notices = []
        state = ["off"]
        monitor = BackgroundMonitor(lambda: state[0], notices.append)
        monitor.tick()
        monitor.tick()
        state[0] = "on"
        monitor.tick()
        monitor.stop()
        state[0] = "off"
        monitor.tick()
        self.assertEqual(notices, ["off", "on"])

    def test_preferences_saved_deduplicated_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(preferences, "PATH", Path(directory) / "preferences.json"):
                preferences.learn("Use concise answers")
                preferences.learn("Use concise answers")
                self.assertEqual(preferences.load_preferences(), ["Use concise answers"])
                preferences.forget()
                self.assertEqual(preferences.load_preferences(), [])

    def test_preference_bounds(self):
        with self.assertRaises(ValueError):
            preferences.learn("x" * 501)

    def test_monitor_errors_are_not_credentials(self):
        def fail():
            raise RuntimeError("private credential")
        notices = []
        monitor = BackgroundMonitor(fail, notices.append)
        monitor.tick()
        self.assertNotIn("private credential", notices[0])

    @patch("app.perception._client")
    def test_vision_sends_only_supplied_image_without_tools(self, factory):
        from PIL import Image
        from app.perception import describe_screen
        client = factory.return_value.__enter__.return_value
        client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="A blank image"))]
        self.assertEqual(describe_screen(Image.new("RGB", (10, 10))), "A blank image")
        arguments = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("tools", arguments)
        self.assertTrue(arguments["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    @patch("app.perception._client")
    @patch("sounddevice.wait")
    @patch("sounddevice.rec")
    def test_transcription_uses_wav_and_returns_reviewable_text(self, record, wait, factory):
        import numpy as np
        from app.perception import transcribe
        record.return_value = np.zeros((160, 1), dtype="int16")
        client = factory.return_value.__enter__.return_value
        client.audio.transcriptions.create.return_value.text = " hello "
        self.assertEqual(transcribe(), "hello")
        payload = client.audio.transcriptions.create.call_args.kwargs["file"]
        self.assertEqual(payload[1][:4], b"RIFF")


if __name__ == "__main__":
    unittest.main()
