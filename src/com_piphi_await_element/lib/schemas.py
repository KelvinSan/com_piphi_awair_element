from pydantic import BaseModel, ConfigDict, Field


class AwairElement(BaseModel):
    id: str
    device_ip: str
    container_id: str | None = None
    device_mac: str | None = None
    model_config = ConfigDict(extra="allow")


class DeconfigureConfig(BaseModel):
    config: dict


class CommandRequest(BaseModel):
    command: str
    entity_id: str | None = None
    device_id: str | None = None
    args: dict = Field(default_factory=dict)


class EventRequest(BaseModel):
    event_type: str
    source: str | None = None
    payload: dict = Field(default_factory=dict)