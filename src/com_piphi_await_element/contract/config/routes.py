import asyncio
import datetime
import random
from typing import Dict
from fastapi import APIRouter
import httpx
from com_piphi_await_element.lib.schemas import AwairElement
import hmac, hashlib, json
from com_piphi_await_element.lib.store import device as device_store

config_router = APIRouter(tags=['config'])

polling: Dict[str, asyncio.Task] = {}

def sign_payload(payload:dict, secret:str):
    data = json.dumps(payload,separators=(',', ':'),sort_keys=True)
    return hmac.new(secret.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()
async def send_telemetry_to_core(telemetry_data: dict):
    """
    Send telemetry data to core application
    """
    if device_store is not None:
        try:
            payload = {
                "device_id": device_store.get("id"),
                "metrics": telemetry_data,
                "timestamp": datetime.datetime.now().isoformat(),
                "units": {
                    "pm25": "ug/m3",
                    "score": "%",
                    "co2": "ppm",
                    "voc": "ppb",
                    "humid": "%",
                    "temp": "°C",
                    "dew_pt": "°C",
                    
                }
            }
            payload['metrics']['power_on'] = random.choice(['on', 'off'])
            signature =sign_payload(payload,device_store.get("secret"))
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=f"http://127.0.0.1:31419/api/v2/integrations/telemetry",
                    json=payload,
                    headers={
                        "X-Piphi-Signature": signature,
                        'X-Container-Id': device_store.get("container_id"),
                    }
                )
                response.raise_for_status()
        except httpx.RequestError as e:
            print(f"Request Error: {e}")
        except httpx.HTTPStatusError as e:
            print(e.response.json())
            print(f"HTTP Status Error: {e}")
        except Exception as e:
            print(f"Exception: {e}")

async def fetch_awair_data(ip_address: str):
    while device_store:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://{ip_address}/air-data/latest")
                response.raise_for_status()
                res_json = response.json()
                payload = {
                    "temp": res_json['temp'],
                    "humid": res_json['humid'],
                    "co2": res_json['co2'],
                    "voc": res_json['voc'],
                    "pm25": res_json['pm25'],
                    "score": res_json['score'],
                    "dew_pt": res_json['dew_point']
                }
                await send_telemetry_to_core(telemetry_data=payload)
        except httpx.RequestError as e:
            print(f"Request Error: {e}")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Status Error: {e}")
        except Exception as e:
            print(f"Exception: {e}")
        await asyncio.sleep(10)

@config_router.post('/config')
async def config(payload:AwairElement):
    device_store.update(payload.model_dump())
    existing_poll = polling.get(payload.id)
    if existing_poll and not existing_poll.done():
        polling[payload.id].cancel()
        try:
            await existing_poll
        except asyncio.CancelledError:
            pass
    task = asyncio.create_task(fetch_awair_data(payload.device_ip))
    polling[payload.id] = task
    # polling = asyncio.create_task(send_telemetry_to_core(device_store))
    return device_store


