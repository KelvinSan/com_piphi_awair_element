import asyncio
import datetime
import random
import traceback
from fastapi import APIRouter, HTTPException
import httpx
from com_piphi_await_element.lib.schemas import (
    AwairElement,
    DeconfigureConfig,
    RuntimeConfigSnapshot,
    RuntimeConfigSyncResponse,
)
from com_piphi_await_element.lib.store import devices, latest_states, update_device_state

config_router = APIRouter(tags=['config'])

async def send_telemetry_to_core(telemetry_data: dict, device_id: str, container_id: str):
    try:
        payload = {
            "device_id": device_id,
            "metrics": telemetry_data,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "units": {
                "pm25": "ug/m3",
                "score": "%",
                "co2": "ppm",
                "voc": "ppb",
                "humid": "%",
                "temp": "°C",
                "dew_pt": "°C",
            },
        }
        payload["metrics"]["power_on"] = random.choice(["on", "off"])
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url="http://127.0.0.1:31419/api/v2/integrations/telemetry",
                json=payload,
                headers={"X-Container-Id": container_id},
            )
            response.raise_for_status()
    except httpx.RequestError as e:
        print(f"Request Error: {e} unable to reach core piphi api")
    except httpx.HTTPStatusError as e:
        print(f"HTTP Status Error: {e}")
        print(e.response.text)
    except Exception:
        traceback.print_exc()

async def fetch_awair_state(ip_address: str, device_id: str, container_id: str | None = None):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{ip_address}/air-data/latest")
        response.raise_for_status()
        res_json = response.json()
        payload = {
            "temp": res_json["temp"],
            "humid": res_json["humid"],
            "co2": res_json["co2"],
            "voc": res_json["voc"],
            "pm25": res_json["pm25"],
            "score": res_json["score"],
            "dew_pt": res_json["dew_point"],
        }
        latest_state = update_device_state(device_id=device_id, state=payload)
        if container_id:
            await send_telemetry_to_core(
                telemetry_data=payload,
                device_id=device_id,
                container_id=container_id,
            )
        return latest_state

async def trigger_refresh(device_id: str):
    device = devices.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' is not configured")
    return await fetch_awair_state(
        ip_address=device["device_ip"],
        device_id=device_id,
        container_id=device.get("container_id"),
    )

async def fetch_awair_data(ip_address: str, device_id: str, container_id: str | None = None):
    while True:
        try:
            await fetch_awair_state(
                ip_address=ip_address,
                device_id=device_id,
                container_id=container_id,
            )
            print(f"Sent telemetry to core for device {device_id} with ip {ip_address}")
        except httpx.RequestError as e:
            print(f"Request Error: {e} unable to access awair element local api")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Status Error: {e}")
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(10)


async def remove_device_config(device_id: str) -> bool:
    existing_poll = devices.get(device_id)
    if existing_poll and existing_poll.get("task") and not existing_poll["task"].done():
        existing_poll["task"].cancel()
        try:
            await existing_poll["task"]
        except asyncio.CancelledError:
            pass
    removed = device_id in devices
    devices.pop(device_id, None)
    latest_states.pop(device_id, None)
    return removed


async def apply_device_config(payload: AwairElement) -> dict:
    await remove_device_config(payload.id)
    task = asyncio.create_task(fetch_awair_data(payload.device_ip, payload.id, payload.container_id))
    devices[payload.id] = {
        "task": task,
        "container_id": payload.container_id,
        "device_id": payload.id,
        "device_ip": payload.device_ip,
        "device_mac": payload.device_mac,
    }
    try:
        await trigger_refresh(payload.id)
    except httpx.HTTPError:
        pass
    return {
        "status": "configured",
        "device_id": payload.id,
        "device_ip": payload.device_ip,
    }


async def apply_runtime_config_snapshot(
    payload: RuntimeConfigSnapshot,
) -> RuntimeConfigSyncResponse:
    incoming_ids = {config.id for config in payload.configs}
    active_ids = list(devices.keys())
    removed_ids: list[str] = []
    applied_ids: list[str] = []

    for device_id in active_ids:
        if device_id not in incoming_ids:
            removed = await remove_device_config(device_id)
            if removed:
                removed_ids.append(device_id)

    for config in payload.configs:
        await apply_device_config(config)
        applied_ids.append(config.id)

    return RuntimeConfigSyncResponse(
        status="synced",
        container_id=payload.container_id,
        reason=payload.reason,
        generation=payload.generation,
        applied=applied_ids,
        removed=removed_ids,
        active_config_ids=list(devices.keys()),
        metadata={
            "applied_count": len(applied_ids),
            "removed_count": len(removed_ids),
        },
    )

@config_router.post('/config')
async def config(payload: AwairElement):
    return await apply_device_config(payload)


@config_router.post('/configs/sync', response_model=RuntimeConfigSyncResponse)
async def sync_configs(payload: RuntimeConfigSnapshot):
    return await apply_runtime_config_snapshot(payload)


@config_router.post('/config/sync', response_model=RuntimeConfigSyncResponse)
async def sync_config(payload: RuntimeConfigSnapshot):
    return await apply_runtime_config_snapshot(payload)

@config_router.post('/deconfigure')
async def deconfigure_device(payload: DeconfigureConfig):
    device_id = payload.config.get("id")
    if device_id is None:
        raise HTTPException(status_code=400, detail="Missing config id")
    removed = await remove_device_config(device_id)
    if not removed:
        print("No task found for device", device_id)
    return {
        "status": "deconfigured",
        "device_id": device_id,
    }

@config_router.post('/refresh')
async def refresh_device(payload: DeconfigureConfig):
    return await trigger_refresh(payload.config["id"])
