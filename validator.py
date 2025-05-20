from pydantic import BaseModel


class UISchema(BaseModel):
    ip_address:str