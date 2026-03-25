import datetime
from typing import Any, Dict, List

DeviceStore = Dict[str, Dict[str, Any]]
StateStore = Dict[str, Dict[str, Any]]

# In-memory runtime state only (integration is intentionally stateless on disk).
devices: DeviceStore = {}
latest_states: StateStore = {}
recent_events: List[Dict[str, Any]] = []

runtime_auth_context: Dict[str, str] = {
    "container_id": "",
    "internal_token": "",
}


def set_runtime_auth_context(
    *,
    container_id: str | None = None,
    internal_token: str | None = None,
) -> None:
    if container_id is not None:
        resolved_container_id = str(container_id).strip()
        if resolved_container_id:
            runtime_auth_context["container_id"] = resolved_container_id

    if internal_token is not None:
        resolved_internal_token = str(internal_token).strip()
        if resolved_internal_token:
            runtime_auth_context["internal_token"] = resolved_internal_token


def get_runtime_auth_context() -> Dict[str, str]:
    return {
        "container_id": runtime_auth_context.get("container_id", ""),
        "internal_token": runtime_auth_context.get("internal_token", ""),
    }


def update_device_state(device_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
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


def append_event(event: Dict[str, Any]) -> Dict[str, Any]:
    record = {
        "received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **event,
    }
    recent_events.append(record)
    if len(recent_events) > 100:
        del recent_events[:-100]
    return record


def get_primary_device() -> Dict[str, Any] | None:
    if not devices:
        return None
    first_device_id = next(iter(devices))
    return devices[first_device_id]
