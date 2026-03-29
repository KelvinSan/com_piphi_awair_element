import asyncio
import datetime
import os
import random
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from com_piphi_await_element.lib.logging import log_event
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

CORE_BASE_URL = "http://127.0.0.1:31419"
CORE_HEALTH_URL = f"{CORE_BASE_URL}/api/v2/health"
TELEMETRY_URL = "http://127.0.0.1:31419/api/v2/integrations/telemetry"
AWAIR_LATEST_AIR_DATA_PATH = "/air-data/latest"
POLL_INTERVAL_SECONDS = 10
INTERNAL_TOKEN_ENV_NAME = "PIPHI_INTEGRATION_INTERNAL_TOKEN"
TELEMETRY_SEND_TIMEOUT_SECONDS = 4.0
TELEMETRY_HEALTH_TIMEOUT_SECONDS = 10.0
TELEMETRY_MAX_RETRIES = 4
TELEMETRY_RETRY_BASE_SECONDS = 0.5
TELEMETRY_RETRY_MAX_SECONDS = 8.0
HEALTH_CACHE_SECONDS = 3.0
RETRYABLE_TELEMETRY_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}

_last_core_health_check_at = 0.0
_last_core_health_ok = True


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

    log_event(
        "runtime_internal_auth",
        header_container_id=header_container_id or "missing",
        payload_container_id=payload_container_id or "missing",
        token=_mask_token(header_token),
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


def _short_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


class RetryableTelemetryError(Exception):
    pass


@retry(
    reraise=True,
    retry=retry_if_exception_type((httpx.RequestError, RetryableTelemetryError)),
    stop=stop_after_attempt(TELEMETRY_MAX_RETRIES + 1),
    wait=wait_exponential_jitter(
        initial=TELEMETRY_RETRY_BASE_SECONDS,
        max=TELEMETRY_RETRY_MAX_SECONDS,
    ),
)
async def _post_telemetry_with_retry(
    client: httpx.AsyncClient,
    payload: Dict[str, Any],
    headers: Dict[str, str],
) -> httpx.Response:
    response = await client.post(
        url=TELEMETRY_URL,
        json=payload,
        headers=headers,
    )
    if response.status_code in RETRYABLE_TELEMETRY_STATUS_CODES:
        raise RetryableTelemetryError(f"retryable_status={response.status_code}")
    return response


async def _is_core_healthy(client: httpx.AsyncClient) -> bool:
    global _last_core_health_check_at
    global _last_core_health_ok

    now = time.monotonic()
    if now - _last_core_health_check_at <= HEALTH_CACHE_SECONDS:
        return _last_core_health_ok

    try:
        response = await client.get(
            CORE_HEALTH_URL,
            timeout=TELEMETRY_HEALTH_TIMEOUT_SECONDS,
        )
        _last_core_health_ok = response.status_code < 500
    except httpx.RequestError:
        _last_core_health_ok = False

    _last_core_health_check_at = now
    return _last_core_health_ok


async def send_telemetry_to_core(
    telemetry_data: Dict[str, Any],
    device_id: str,
    container_id: str | None,
) -> None:
    try:
        resolved_container_id, resolved_internal_token = _resolve_runtime_auth(container_id)
        if not resolved_container_id:
            log_event("telemetry_send_skipped", level="warning", reason="missing_container_id")
            return

        headers = {"X-Container-Id": resolved_container_id}
        if resolved_internal_token:
            headers["X-PiPhi-Integration-Token"] = resolved_internal_token

        payload = _build_telemetry_payload(telemetry_data, device_id)
        timeout = httpx.Timeout(TELEMETRY_SEND_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            is_healthy = await _is_core_healthy(client)
            if not is_healthy:
                log_event("telemetry_send_deferred", level="warning", reason="core_health_unavailable")
                return

            try:
                response = await _post_telemetry_with_retry(
                    client=client,
                    payload=payload,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                log_event(
                    "telemetry_send_request_error",
                    level="warning",
                    device_id=device_id,
                    error=_short_error_message(exc),
                )
                return
            except RetryableTelemetryError as exc:
                log_event(
                    "telemetry_send_retry_exhausted",
                    level="warning",
                    device_id=device_id,
                    error=_short_error_message(exc),
                )
                return

            if response.status_code >= 400:
                log_event(
                    "telemetry_send_http_error",
                    level="warning",
                    device_id=device_id,
                    status=response.status_code,
                )
            return
    except Exception:
        log_event("telemetry_send_unexpected_error", level="error", exc_info=True)


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
            log_event("telemetry_sent", device_id=device_id, ip=ip_address)
        except httpx.RequestError as exc:
            log_event("awair_poll_request_error", level="warning", device_id=device_id, error=exc)
        except httpx.HTTPStatusError as exc:
            log_event(
                "awair_poll_http_error",
                level="warning",
                device_id=device_id,
                status=exc.response.status_code,
            )
        except Exception:
            log_event("awair_poll_unexpected_error", level="error", device_id=device_id, exc_info=True)

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
        log_event("awair_initial_refresh_failed", level="warning", device_id=payload.id)

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
        log_event("deconfigure_noop", device_id=device_id)

    return {
        "status": "deconfigured",
        "device_id": device_id,
    }


@config_router.post("/refresh")
async def refresh_device(payload: DeconfigureConfig):
    return await trigger_refresh(payload.config["id"])
