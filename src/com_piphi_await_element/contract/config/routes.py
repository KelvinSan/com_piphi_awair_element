import asyncio
import datetime
import random
import traceback
from typing import Dict
from fastapi import APIRouter, HTTPException
import httpx
from com_piphi_await_element.lib.schemas import AwairElement, DeconfigureConfig
import hmac, hashlib, json
from com_piphi_await_element.lib.store import devices

config_router = APIRouter(tags=['config'])




async def send_telemetry_to_core(telemetry_data: dict, device_id:str,container_id:str):
    """
    Send telemetry data to core application
    """
    try:
        
        payload = {
            "device_id": device_id,
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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"http://127.0.0.1:31419/api/v2/integrations/telemetry",
                json=payload,
                headers={
                    'X-Container-Id': container_id
                }
            )
            response.raise_for_status()
    except httpx.RequestError as e:
        print(f"Request Error: {e} unable to reach core piphi api")
    except httpx.HTTPStatusError as e:
        print(f"HTTP Status Error: {e}")
        print(e.response.text)
    except Exception as e:
        traceback.print_exc()

async def fetch_awair_data(ip_address: str,device_id:str,container_id:str):
    while True:
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
                await send_telemetry_to_core(telemetry_data=payload,device_id=device_id,container_id=container_id)
                print(f"Sent telemetry to core for device {device_id} with ip {ip_address}")
        except httpx.RequestError as e:
            print(f"Request Error: {e} unable to access awair element local api")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Status Error: {e}")
        except Exception as e:
            traceback.print_exc()
        await asyncio.sleep(10)

@config_router.post('/config')
async def config(payload:AwairElement):
    existing_poll = devices.get(payload.id, None)
    if existing_poll and not existing_poll.get("task").done():
        devices[payload.id]["task"].cancel()
        try:
            await existing_poll.get("task")
        except asyncio.CancelledError:
            pass
    task = asyncio.create_task(fetch_awair_data(payload.device_ip,payload.id,payload.container_id))
    devices[payload.id] = {
        "task": task,
        "container_id": payload.container_id
    }
    # devices = asyncio.create_task(send_telemetry_to_core(device_store))
    
    
@config_router.post('/deconfigure')
async def deconfigure_device(payload:DeconfigureConfig):
    if payload.config["id"] is None:
        raise HTTPException(status_code=400, detail="Missing config id")
    existing_poll = devices.get(payload.config["id"])
    if existing_poll and not existing_poll.get("task").done():
        devices[payload.config["id"]]["task"].cancel()
        try:
            await existing_poll.get("task")
        except asyncio.CancelledError:
            pass
    else:
        print("No task found for device", payload.config["id"])
    

