from typing import Any, Dict

from piphi_runtime_kit_python import RuntimeContext, RuntimeRegistry

DeviceStore = Dict[str, Dict[str, Any]]

# In-memory runtime state only (integration is intentionally stateless on disk).
registry = RuntimeRegistry[Dict[str, Any], Dict[str, Any], Dict[str, Any]]()
runtime_context = RuntimeContext()


def set_runtime_auth_context(
    *,
    container_id: str | None = None,
    internal_token: str | None = None,
) -> None:
    runtime_context.auth.update(
        container_id=container_id,
        internal_token=internal_token,
    )


def get_runtime_auth_context() -> Dict[str, str]:
    return {
        "container_id": runtime_context.auth.container_id,
        "internal_token": runtime_context.auth.internal_token,
    }


def get_runtime_context() -> RuntimeContext:
    return runtime_context


def set_core_http_client(client) -> None:
    runtime_context.set_core_http_client(client)


def get_core_http_client():
    return runtime_context.process_state.core_http_client


def list_pending_background_tasks() -> list[Any]:
    return [task for task in runtime_context.process_state.background_tasks if not task.done()]


def get_current_generation() -> int | None:
    return runtime_context.process_state.current_generation


def set_current_generation(generation: int | None) -> None:
    runtime_context.set_current_generation(generation)


def update_device_state(device_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    return registry.update_state(device_id, state)


def append_event(event: Dict[str, Any]) -> Dict[str, Any]:
    return registry.append_event(event)


def get_primary_device() -> Dict[str, Any] | None:
    return registry.primary_entry()
