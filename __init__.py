from getmac import get_mac_address
from lib.sensors.integrations.discovery.zeroconf.zeroconf_discovery import config

context:dict = {}

def hello_world():
    return "Hello PiPhi Network"

async def discover():
    filtered = {}
    payload = []
    for key,value in config.items():
        if "awair".casefold() in str(key).casefold():
            filtered[key] = value
            break
    for key,value in filtered.items():
        payload.append(dict(hostname=key,ip_address=value,mac_address=get_mac_address(ip=value),make="Awair"))
    return payload