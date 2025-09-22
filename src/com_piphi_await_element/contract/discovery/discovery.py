from fastapi import APIRouter, HTTPException
from com_piphi_await_element.lib.lifespan import config

discovery_router = APIRouter(prefix="/discovery",tags=['discovery'])

@discovery_router.get('')
async def get_discovered_devices():
    discovered_devices = []
    for key, item in config.items():
        if "awair".casefold() in str(key).casefold():
            discovered_devices.append({"make":"Awair","model":"Element","name":key,"device_ip":item['addresses'][0],"meta":item['meta'],"port":item['port']})
    return {
        "devices":discovered_devices
        }