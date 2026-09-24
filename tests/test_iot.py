import os
import unittest
from unittest.mock import patch
from app.iot import list_devices, control_device


class IoTTests(unittest.TestCase):
    @patch.dict(os.environ, {"IOT_BACKEND": "demo"})
    def test_simulation_and_controls(self):
        self.assertTrue(list_devices()["simulated"])
        self.assertEqual(control_device("light.study", "turn_on")["state"], "on")
        self.assertEqual(control_device("light.study", "turn_off")["state"], "off")

    @patch.dict(os.environ, {"IOT_BACKEND": "demo"})
    def test_rejects_unknown_and_unsafe_targets(self):
        for target in ("light.unknown", "lock.front_door", "../services"):
            with self.assertRaises(ValueError):
                control_device(target, "turn_on")

    @patch.dict(os.environ, {"IOT_BACKEND": "home_assistant", "HA_ALLOWED_ENTITIES": "light.study"})
    @patch("app.iot._request")
    def test_real_control_requires_allowlist(self, request):
        with self.assertRaises(ValueError):
            control_device("switch.unknown", "turn_on")
        request.assert_not_called()
        request.side_effect = [[], {"state": "on"}]
        result = control_device("light.study", "turn_on")
        self.assertFalse(result["simulated"])
        self.assertEqual(request.call_args_list[0].args,
                         ("POST", "services/light/turn_on", {"entity_id": "light.study"}))

    @patch.dict(os.environ, {"IOT_BACKEND": "invalid"})
    def test_invalid_mode_never_falls_back_to_demo(self):
        with self.assertRaises(ValueError):
            list_devices()


if __name__ == "__main__":
    unittest.main()
