import datetime
from typing import Dict, List

devices: Dict[str, Dict] = {}
latest_states: Dict[str, Dict] = {}
recent_events: List[Dict] = []


def update_device_state(device_id: str, state: Dict) -> Dict:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    latest_state = {
        "device_id": device_id,
        "state": state,
        "last_updated": timestamp,
    }
    latest_states[device_id] = latest_state
    if device_id in devices:
        devices[device_id]["latest_state"] = state
        devices[device_id]["last_updated"] = timestamp
    return latest_state


def append_event(event: Dict) -> Dict:
    record = {
        "received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **event,
    }
    recent_events.append(record)
    if len(recent_events) > 100:
        del recent_events[:-100]
    return record


def get_primary_device() -> Dict | None:
    if not devices:
        return None
    first_device_id = next(iter(devices))
    return devices[first_device_id]
