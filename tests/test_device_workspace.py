from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.device_workspace import device_readings, save_panel, remove_panel, workspace
from app.llm import generate_chat_reply
from app.schemas import ChatRequest


class DeviceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch("app.device_workspace.DATABASE", Path(directory) / "devices.sqlite3"))
        self.snapshot = {"backend": "demo", "simulated": True, "devices": [
            {"entity_id": "sensor.room_temperature", "state": "21.5", "unit": "°C"}
        ]}
        self.enterContext(patch("app.device_workspace.list_devices", return_value=self.snapshot))

    def test_samples_survive_rename_and_stop_being_exposed_after_allowlist_removal(self):
        entity = "sensor.room_temperature"
        save_panel(entity, "Room")
        first = workspace(record=True)["panels"][0]
        self.assertEqual(first["readings"][0]["state"], "21.5")
        save_panel(entity, "Study")
        renamed = workspace()["panels"][0]
        self.assertEqual(renamed["id"], first["id"])
        self.assertEqual(renamed["title"], "Study")
        self.assertEqual(len(device_readings(entity)["panels"][0]["readings"]), 1)
        self.snapshot["devices"].clear()
        self.assertEqual(device_readings(entity)["panels"], [])
        with self.assertRaises(ValueError):
            save_panel(entity, "Unlisted")

    def test_removing_a_panel_clears_its_history(self):
        entity = "sensor.room_temperature"
        save_panel(entity, "Room")
        panel_id = workspace(record=True)["panels"][0]["id"]
        remove_panel(panel_id)
        save_panel(entity, "Room again")
        self.assertEqual(workspace()["panels"][0]["readings"], [])


class DeviceChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_opted_in_device_reads_are_executed(self):
        settings = SimpleNamespace(openai_api_key="test", openai_base_url=None, openai_model="test")
        for shared, name, should_run in [
            (False, "list_devices", False),
            (True, "list_devices", True),
            (True, "control_device", False),
            (True, "send_email", False),
        ]:
            call = SimpleNamespace(id="call-1", function=SimpleNamespace(name=name, arguments="{}"))
            client = SimpleNamespace(close=AsyncMock(), chat=SimpleNamespace(completions=SimpleNamespace(
                create=AsyncMock(side_effect=[
                    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))]),
                    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Reply", tool_calls=[]))]),
                ]))))
            with patch("app.llm.AsyncOpenAI", return_value=client), patch("app.llm.execute_tool", return_value="{}") as execute:
                await generate_chat_reply(ChatRequest(message="Read the device", share_devices=shared), settings)
                self.assertEqual(execute.called, should_run, name)
