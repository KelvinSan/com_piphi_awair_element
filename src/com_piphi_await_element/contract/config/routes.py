
from fastapi import APIRouter
from com_piphi_await_element.lib.schemas import AwairElement
from com_piphi_await_element.lib.store import device as device_store
config_router = APIRouter(tags=['config'])

@config_router.post('/config')
async def config(requestbody:AwairElement):
    device_store.update(requestbody.model_dump())
    return device_store


