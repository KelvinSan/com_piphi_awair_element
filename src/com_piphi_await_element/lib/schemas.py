from pydantic import BaseModel, ConfigDict, Field
from piphi_runtime_kit_python import RuntimeConfig
from typing import Any


class AwairElement(RuntimeConfig):
    config_id: str | None = None
    device_ip: str
    container_id: str | None = None
    integration_id: str | None = None
    device_mac: str | None = None
    model_config = ConfigDict(extra="allow")


class DeconfigureConfig(BaseModel):
    config: dict


class RuntimeConfigSnapshot(BaseModel):
    container_id: str
    integration_id: str | None = None
    driver_pid: int | None = None
    reason: str | None = None
    generation: int | None = None
    configs: list[AwairElement] = Field(default_factory=list)


class RuntimeConfigSyncResponse(BaseModel):
    status: str
    container_id: str
    reason: str | None = None
    generation: int | None = None
    applied: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    active_config_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommandRequest(BaseModel):
    command: str
    entity_id: str | None = None
    device_id: str | None = None
    args: dict = Field(default_factory=dict)


class EventRequest(BaseModel):
    event_type: str
    source: str | None = None
    payload: dict = Field(default_factory=dict)
