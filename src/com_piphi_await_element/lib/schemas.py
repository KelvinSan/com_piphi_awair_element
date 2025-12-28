

from pydantic import BaseModel, ConfigDict


class AwairElement(BaseModel):
    id: str
    device_ip: str
    model_config = ConfigDict(extra="allow")
    
    
class DeconfigureConfig(BaseModel):
    config: dict