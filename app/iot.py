"""Simulated devices by default; opt-in Home Assistant REST adapter."""
import os
import re
import threading

import httpx

_lock = threading.Lock()
_demo = {"light.study": "off", "switch.desk_lamp": "off", "sensor.room_temperature": "21.5"}


def _mode():
    mode = os.getenv("IOT_BACKEND", "demo").strip().lower()
    if mode not in {"demo", "home_assistant"}:
        raise ValueError("IOT_BACKEND must be demo or home_assistant")
    return mode


def _allowed():
    return {x.strip() for x in os.getenv("HA_ALLOWED_ENTITIES", "").split(",") if x.strip()}


def _request(method, path, body=None):
    url = os.getenv("HA_URL", "").rstrip("/")
    token = os.getenv("HA_TOKEN", "")
    if not url or not token:
        raise ValueError("Set HA_URL and HA_TOKEN locally before connecting devices")
    try:
        response = httpx.request(method, url + "/api/" + path,
                                 headers={"Authorization": "Bearer " + token},
                                 json=body, timeout=10, follow_redirects=False)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise ValueError("Home Assistant request failed; check connection and credentials") from None


def list_devices():
    mode = _mode()
    if mode == "demo":
        with _lock:
            devices = [{"entity_id": k, "state": v} for k, v in _demo.items()]
    else:
        devices = [{"entity_id": d["entity_id"], "state": d["state"]}
                   for d in _request("GET", "states") if d["entity_id"] in _allowed()]
    return {"backend": mode, "simulated": mode == "demo", "devices": devices}


def control_device(entity_id: str, action: str):
    if not re.fullmatch(r"(?:light|switch)\.[a-z0-9_]+", entity_id):
        raise ValueError("Only explicitly configured lights and switches support control")
    if action not in {"turn_on", "turn_off"}:
        raise ValueError("Action must be turn_on or turn_off")
    mode = _mode()
    if mode == "demo":
        with _lock:
            if entity_id not in _demo:
                raise ValueError("Unknown simulated device; list devices first")
            _demo[entity_id] = "on" if action == "turn_on" else "off"
        return {"simulated": True, "entity_id": entity_id, "state": _demo[entity_id]}
    if entity_id not in _allowed():
        raise ValueError("Device is not in HA_ALLOWED_ENTITIES")
    _request("POST", "services/" + entity_id.split(".")[0] + "/" + action,
             {"entity_id": entity_id})
    state = _request("GET", "states/" + entity_id)
    return {"simulated": False, "entity_id": entity_id, "state": state["state"]}
