import asyncio
import datetime
import os
import random
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
import httpx

from com_piphi_await_element.lib.logging import logger
from com_piphi_await_element.lib.schemas import (
    AwairElement,
    DeconfigureConfig,
    RuntimeConfigSnapshot,
    RuntimeConfigSyncResponse,
)
from com_piphi_await_element.lib.store import (
    devices,
    get_runtime_auth_context,
    latest_states,
    set_runtime_auth_context,
    update_device_state,
)

config_router = APIRouter(tags=["config"])
current_generation: int | None = None

TELEMETRY_URL = "http://127.0.0.1:31419/api/v2/integrations/telemetry"
AWAIR_LATEST_AIR_DATA_PATH = "/air-data/latest"
POLL_INTERVAL_SECONDS = 10
INTERNAL_TOKEN_ENV_NAME = "PIPHI_INTEGRATION_INTERNAL_TOKEN"


def _mask_token(token: str | None) -> str:
    token = (token or "").strip()
    if not token:
        return "missing"
    if len(token) <= 10:
        return "present"
    return f"{token[:6]}...{token[-4:]}"


def _sync_runtime_auth_from_request(
    request: Request,
    payload_container_id: str | None = None,
) -> None:
    header_container_id = (request.headers.get("X-Container-Id") or "").strip()
    header_token = (request.headers.get("X-PiPhi-Integration-Token") or "").strip()

    set_runtime_auth_context(
        container_id=header_container_id or payload_container_id,
        internal_token=header_token,
    )

    logger.info(
        "runtime_internal_auth "
        f"header_container_id={header_container_id or 'missing'} "
        f"payload_container_id={payload_container_id or 'missing'} "
        f"token={_mask_token(header_token)}"
    )


def _resolve_runtime_auth(
    container_id: str | None,
) -> tuple[str, str]:
    runtime_auth = get_runtime_auth_context()
    resolved_container_id = (
        (container_id or "").strip()
        or runtime_auth.get("container_id", "").strip()
    )
    resolved_internal_token = (
        runtime_auth.get("internal_token", "").strip()
        or (os.getenv(INTERNAL_TOKEN_ENV_NAME) or "").strip()
    )
    return resolved_container_id, resolved_internal_token


def _build_telemetry_payload(
    telemetry_data: Dict[str, Any],
    device_id: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
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
    return payload


def _extract_awair_metrics(awair_response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temp": awair_response["temp"],
        "humid": awair_response["humid"],
        "co2": awair_response["co2"],
        "voc": awair_response["voc"],
        "pm25": awair_response["pm25"],
        "score": awair_response["score"],
        "dew_pt": awair_response["dew_point"],
    }


async def send_telemetry_to_core(
    telemetry_data: Dict[str, Any],
    device_id: str,
    container_id: str | None,
) -> None:
    try:
        resolved_container_id, resolved_internal_token = _resolve_runtime_auth(container_id)
        if not resolved_container_id:
            logger.warning("telemetry_send_skipped reason=missing_container_id")
            return

        headers = {"X-Container-Id": resolved_container_id}
        if resolved_internal_token:
            headers["X-PiPhi-Integration-Token"] = resolved_internal_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=TELEMETRY_URL,
                json=_build_telemetry_payload(telemetry_data, device_id),
                headers=headers,
            )
            response.raise_for_status()
    except httpx.RequestError as exc:
        logger.error(f"telemetry_send_request_error error={exc}")
    except httpx.HTTPStatusError as exc:
        logger.error(
            "telemetry_send_http_error "
            f"status={exc.response.status_code} body={exc.response.text}"
        )
    except Exception:
        logger.exception("telemetry_send_unexpected_error")


async def fetch_awair_state(
    ip_address: str,
    device_id: str,
    container_id: str | None = None,
) -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{ip_address}{AWAIR_LATEST_AIR_DATA_PATH}")
        response.raise_for_status()

    payload = _extract_awair_metrics(response.json())
    latest_state = update_device_state(device_id=device_id, state=payload)

    if container_id:
        await send_telemetry_to_core(
            telemetry_data=payload,
            device_id=device_id,
            container_id=container_id,
        )

    return latest_state


async def trigger_refresh(device_id: str) -> Dict[str, Any]:
    device = devices.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' is not configured")

    return await fetch_awair_state(
        ip_address=device["device_ip"],
        device_id=device_id,
        container_id=device.get("container_id"),
    )


async def fetch_awair_data(
    ip_address: str,
    device_id: str,
    container_id: str | None = None,
) -> None:
    while True:
        try:
            await fetch_awair_state(
                ip_address=ip_address,
                device_id=device_id,
                container_id=container_id,
            )
            logger.info(f"telemetry_sent device_id={device_id} ip={ip_address}")
        except httpx.RequestError as exc:
            logger.warning(f"awair_poll_request_error device_id={device_id} error={exc}")
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"awair_poll_http_error device_id={device_id} status={exc.response.status_code}"
            )
        except Exception:
            logger.exception(f"awair_poll_unexpected_error device_id={device_id}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


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


async def apply_device_config(payload: AwairElement) -> Dict[str, Any]:
    runtime_auth = get_runtime_auth_context()
    resolved_container_id = payload.container_id or runtime_auth.get("container_id") or None

    if resolved_container_id:
        set_runtime_auth_context(container_id=resolved_container_id)

    await remove_device_config(payload.id)
    task = asyncio.create_task(
        fetch_awair_data(payload.device_ip, payload.id, resolved_container_id)
    )
    devices[payload.id] = {
        "task": task,
        "container_id": resolved_container_id,
        "device_id": payload.id,
        "device_ip": payload.device_ip,
        "device_mac": payload.device_mac,
    }

    try:
        await trigger_refresh(payload.id)
    except httpx.HTTPError:
        logger.warning(f"awair_initial_refresh_failed device_id={payload.id}")

    return {
        "status": "configured",
        "device_id": payload.id,
        "device_ip": payload.device_ip,
    }


async def apply_runtime_config_snapshot(
    payload: RuntimeConfigSnapshot,
) -> RuntimeConfigSyncResponse:
    global current_generation

    incoming_generation = payload.generation
    if (
        incoming_generation is not None
        and current_generation is not None
        and int(incoming_generation) < int(current_generation)
    ):
        return RuntimeConfigSyncResponse(
            status="stale_ignored",
            container_id=payload.container_id,
            reason=payload.reason,
            generation=current_generation,
            applied=[],
            removed=[],
            active_config_ids=list(devices.keys()),
            metadata={
                "stale_generation_ignored": True,
                "incoming_generation": incoming_generation,
                "current_generation": current_generation,
            },
        )

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

    if incoming_generation is not None:
        current_generation = int(incoming_generation)

    return RuntimeConfigSyncResponse(
        status="synced",
        container_id=payload.container_id,
        reason=payload.reason,
        generation=current_generation,
        applied=applied_ids,
        removed=removed_ids,
        active_config_ids=list(devices.keys()),
        metadata={
            "applied_count": len(applied_ids),
            "removed_count": len(removed_ids),
            "current_generation": current_generation,
        },
    )


@config_router.post("/config")
async def config(payload: AwairElement, request: Request):
    _sync_runtime_auth_from_request(request, payload.container_id)
    return await apply_device_config(payload)


@config_router.post("/configs/sync", response_model=RuntimeConfigSyncResponse)
async def sync_configs(payload: RuntimeConfigSnapshot, request: Request):
    _sync_runtime_auth_from_request(request, payload.container_id)
    return await apply_runtime_config_snapshot(payload)


@config_router.post("/config/sync", response_model=RuntimeConfigSyncResponse)
async def sync_config(payload: RuntimeConfigSnapshot, request: Request):
    _sync_runtime_auth_from_request(request, payload.container_id)
    return await apply_runtime_config_snapshot(payload)


@config_router.post("/deconfigure")
async def deconfigure_device(payload: DeconfigureConfig):
    device_id = payload.config.get("id")
    if device_id is None:
        raise HTTPException(status_code=400, detail="Missing config id")

    removed = await remove_device_config(device_id)
    if not removed:
        logger.info(f"deconfigure_noop device_id={device_id}")

    return {
        "status": "deconfigured",
        "device_id": device_id,
    }


@config_router.post("/refresh")
async def refresh_device(payload: DeconfigureConfig):
    return await trigger_refresh(payload.config["id"])
